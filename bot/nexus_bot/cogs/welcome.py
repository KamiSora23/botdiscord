"""Welcome & Goodbye (docs/NEXUS_API_SPEC.md §8)."""

from __future__ import annotations

import io
import json
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.dialects.postgresql import insert

from nexus_core import media as M
from nexus_core.db import sessionmaker
from nexus_core.db.models import ScheduledJob
from nexus_core.db.repo import utcnow
from nexus_core.i18n import t
from nexus_core.messages import MessageTemplate, RenderContext, render_payload
from nexus_core.modules import parse_config
from nexus_core.modules.welcome import WelcomeConfig
from nexus_core.sync import guild_alerts_key

from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.welcome")


def context_for(member: discord.Member | discord.User, guild: discord.Guild, channel_id: int | None,
                locale: str, tz: str, member_count: int | None = None) -> RenderContext:
    joined = getattr(member, "joined_at", None)
    return RenderContext(
        user_id=member.id, user_name=member.name, user_display_name=member.display_name,
        user_avatar_url=member.display_avatar.replace(size=256).url, user_created_at=member.created_at,
        user_joined_at=joined, server_id=guild.id, server_name=guild.name,
        server_icon_url=guild.icon.url if guild.icon else None,
        member_count=member_count if member_count is not None else (guild.member_count or 0),
        channel_id=channel_id, locale=locale, timezone=tz,
    )


def to_discord(payload: dict[str, Any]) -> dict[str, Any]:
    """Convierte el payload REST en argumentos de discord.py."""
    kwargs: dict[str, Any] = {}
    if "content" in payload:
        kwargs["content"] = payload["content"]
    if payload.get("embeds"):
        kwargs["embeds"] = [discord.Embed.from_dict(e) for e in payload["embeds"]]
    users = [discord.Object(id=int(u)) for u in payload.get("allowed_mentions", {}).get("users", [])]
    kwargs["allowed_mentions"] = discord.AllowedMentions(everyone=False, roles=False, users=users or False)
    return kwargs


async def with_media(guild_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Como to_discord, pero adjunta las imágenes subidas (media://) y las enlaza dentro del embed."""
    files: list[M.Loaded] = []
    if ids := M.referenced(payload):
        async with sessionmaker()() as db:
            files = await M.load(db, guild_id, ids)
    M.attach(payload, {f.id: f.name for f in files})
    kwargs = to_discord(payload)
    if files:
        kwargs["files"] = [discord.File(io.BytesIO(f.data), filename=f.name) for f in files]
    return kwargs


def for_edit(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Al editar, los adjuntos se reemplazan (attachments=) en vez de añadirse (files=)."""
    out = dict(kwargs)
    out["attachments"] = out.pop("files", [])
    return out


class Welcome(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot

    def _config(self, guild_id: int) -> WelcomeConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("welcome")
        if mod is None:
            return None
        try:
            return parse_config("welcome", mod.config, state.locale)  # type: ignore[return-value]
        except Exception:
            log.exception("Configuración de welcome inválida en %s", guild_id)
            return None

    async def _alert(self, guild_id: int, code: str, channel_id: int | None) -> None:
        data = json.dumps({"code": code, "module": "welcome", "channel_id": str(channel_id) if channel_id else None,
                           "severity": "warning"})
        k = guild_alerts_key(guild_id)
        try:
            await self.bot.redis.lrem(k, 0, data)
            await self.bot.redis.lpush(k, data)
            await self.bot.redis.ltrim(k, 0, 9)
            await self.bot.redis.expire(k, 86400)
        except Exception:
            pass

    async def _clear_alerts(self, guild_id: int) -> None:
        try:
            await self.bot.redis.delete(guild_alerts_key(guild_id))
        except Exception:
            pass

    async def send_template(self, guild: discord.Guild, channel_id: int, tmpl: MessageTemplate,
                            member: discord.Member | discord.User, *, member_count: int | None = None,
                            delete_after: int | None = None) -> discord.Message | None:
        state = self.bot.cache.get(guild.id)
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            await self._alert(guild.id, "channel_not_found", channel_id)
            return None
        ctx = context_for(member, guild, channel_id, state.locale, state.timezone, member_count)
        payload = render_payload(tmpl, ctx, state.embed_color)
        try:
            msg = await channel.send(**await with_media(guild.id, payload))
        except discord.Forbidden:
            await self._alert(guild.id, "bot_cannot_send", channel_id)
            return None
        except discord.HTTPException:
            log.exception("No se pudo enviar el mensaje de welcome en %s", guild.id)
            return None
        if delete_after:
            await self._schedule_delete(guild.id, msg, delete_after)
        return msg

    async def _schedule_delete(self, guild_id: int, msg: discord.Message, seconds: int) -> None:
        if seconds <= 60:
            await msg.delete(delay=seconds)
            return
        async with sessionmaker()() as db:
            await db.execute(insert(ScheduledJob).values(
                guild_id=guild_id, job_type="message.delete", run_at=utcnow() + timedelta(seconds=seconds),
                payload={"channel_id": str(msg.channel.id), "message_id": str(msg.id)},
            ))
            await db.commit()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = self._config(member.guild.id)
        if cfg is None or (member.bot and cfg.join.ignore_bots):
            return
        if cfg.join.enabled and cfg.join.channel_id:
            msg = await self.send_template(member.guild, cfg.join.channel_id, cfg.join.message, member,
                                           delete_after=cfg.join.delete_after_seconds)
            if msg:
                self.bot.stats.incr(member.guild.id, "welcome_sent")
        if cfg.join.dm.enabled and cfg.join.dm.message:
            state = self.bot.cache.get(member.guild.id)
            ctx = context_for(member, member.guild, None, state.locale, state.timezone)
            try:
                await member.send(**await with_media(member.guild.id, render_payload(cfg.join.dm.message, ctx,
                                                                                     state.embed_color)))
            except discord.HTTPException:
                pass  # MDs cerrados: no es un error del servidor

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = self._config(member.guild.id)
        if cfg is None or not cfg.leave.enabled or not cfg.leave.channel_id:
            return
        if member.bot and cfg.leave.ignore_bots:
            return
        await self.send_template(member.guild, cfg.leave.channel_id, cfg.leave.message, member)

    # --- comandos ---------------------------------------------------------
    group = app_commands.Group(name=key("cmd.welcome.name"), description=key("cmd.welcome.description"),
                               guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    @group.command(name=key("cmd.welcome_test.name"), description=key("cmd.welcome_test.description"))
    async def test(self, interaction: discord.Interaction) -> None:
        assert interaction.guild and isinstance(interaction.user, discord.Member)
        loc = self.bot.cache.get(interaction.guild.id).locale
        cfg = self._config(interaction.guild.id)
        if cfg is None or not cfg.join.channel_id:
            await interaction.response.send_message(t(loc, "welcome.not_configured"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        msg = await self.send_template(interaction.guild, cfg.join.channel_id, cfg.join.message, interaction.user)
        if msg:
            await self._clear_alerts(interaction.guild.id)
            await interaction.followup.send(t(loc, "welcome.test_sent", channel=f"<#{cfg.join.channel_id}>"),
                                            ephemeral=True)
        else:
            await interaction.followup.send(t(loc, "welcome.test_failed"), ephemeral=True)

    @group.command(name=key("cmd.welcome_status.name"), description=key("cmd.welcome_status.description"))
    async def status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        state = self.bot.cache.get(interaction.guild.id)
        loc = state.locale
        mod = state.modules.get("welcome")
        if mod is None or not mod.enabled:
            await interaction.response.send_message(t(loc, "welcome.status_off"), ephemeral=True)
            return
        cfg = self._config(interaction.guild.id)
        assert cfg is not None
        def ch(c: int | None) -> str:
            return f"<#{c}>" if c else "—"
        lines = [
            t(loc, "welcome.status_join", state=t(loc, "on" if cfg.join.enabled else "off"), channel=ch(cfg.join.channel_id)),
            t(loc, "welcome.status_leave", state=t(loc, "on" if cfg.leave.enabled else "off"), channel=ch(cfg.leave.channel_id)),
            t(loc, "welcome.status_dm", state=t(loc, "on" if cfg.join.dm.enabled else "off")),
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def delete_message_job(bot: NexusBot, job: ScheduledJob) -> None:
    channel = bot.get_channel(int(job.payload["channel_id"]))
    if channel is None or not hasattr(channel, "get_partial_message"):
        return
    try:
        await channel.get_partial_message(int(job.payload["message_id"])).delete()  # type: ignore[union-attr]
    except discord.NotFound:
        pass


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Welcome(bot))
