"""Canal trampa (honeypot): sanciona a quien escribe en él y borra lo que envió en otros canales."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands
from sqlalchemy import func, select, update

from nexus_core.db import sessionmaker
from nexus_core.db.models import HoneypotStrike, ModuleConfig
from nexus_core.db.repo import utcnow
from nexus_core.i18n import t
from nexus_core.messages import render_payload
from nexus_core.modules import parse_config
from nexus_core.modules.honeypot import HoneypotConfig, is_exempt, pick_action

from nexus_bot.cogs.welcome import context_for, for_edit, with_media

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.honeypot")


class Honeypot(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self._busy: set[tuple[int, int]] = set()  # (servidor, usuario) en proceso: un bot de spam manda ráfagas
        bot.rpc_handlers["honeypot.setup"] = self.rpc_setup
        bot.rpc_handlers["honeypot.publish"] = self.rpc_publish

    def cfg(self, guild_id: int) -> HoneypotConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("honeypot")
        return parse_config("honeypot", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    def loc(self, guild_id: int) -> str:
        return self.bot.cache.get(guild_id).locale

    # --- Detección -----------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or not isinstance(message.author, discord.Member):
            return
        cfg = self.cfg(message.guild.id)
        if cfg is None or not cfg.channel_id or message.channel.id != cfg.channel_id:
            return
        m = message.author
        perms = m.guild_permissions
        if is_exempt(is_owner=m.id == message.guild.owner_id, is_bot=m.bot,
                     is_staff=perms.administrator or perms.manage_guild or perms.manage_messages,
                     role_ids={r.id for r in m.roles}, exempt=cfg.exempt_role_ids):
            return
        key = (message.guild.id, m.id)
        if key in self._busy:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            return
        self._busy.add(key)
        try:
            await self._handle(message, m, cfg)
        finally:
            self._busy.discard(key)

    async def _handle(self, message: discord.Message, member: discord.Member, cfg: HoneypotConfig) -> None:
        guild = message.guild
        assert guild
        loc = self.loc(guild.id)
        excerpt = (message.content or "")[:500]
        # Reincidencia: veces que esta cuenta cayó en la ventana configurada (contando esta).
        async with sessionmaker()() as db:
            q = select(func.count()).select_from(HoneypotStrike).where(
                HoneypotStrike.guild_id == guild.id, HoneypotStrike.user_id == member.id)
            if cfg.strike_window_days:
                q = q.where(HoneypotStrike.created_at >= utcnow() - timedelta(days=cfg.strike_window_days))
            strikes = (await db.scalar(q) or 0) + 1
            action, timeout_minutes, step = pick_action(cfg, strikes)
            db.add(HoneypotStrike(guild_id=guild.id, user_id=member.id, action=action))
            await db.commit()
        log.warning("Honeypot: %s escribió en el canal trampa de %s (vez %s, sanción %s)", member.id, guild.id,
                    strikes, action)
        deleted, where = 0, []
        try:
            await message.delete()
            deleted += 1
        except discord.HTTPException:
            pass
        # Ban y softban ya borran los mensajes recientes (1 día) en Discord; en el resto los buscamos nosotros.
        if cfg.purge_minutes and action not in ("ban", "softban"):
            after = discord.utils.utcnow() - timedelta(minutes=cfg.purge_minutes)
            for ch in guild.text_channels:
                if ch.id == message.channel.id:
                    continue
                p = ch.permissions_for(guild.me)
                if not (p.view_channel and p.read_message_history and p.manage_messages):
                    continue
                try:
                    gone = await ch.purge(limit=200, after=after, check=lambda x: x.author.id == member.id,
                                          reason=t(loc, "hp.reason"))
                except discord.HTTPException:
                    continue
                if gone:
                    deleted += len(gone)
                    where.append(ch.mention)
        # Sanción
        action_text = t(loc, "hp.act_delete")
        if action != "delete":
            mod = self.bot.get_cog("Moderation")
            try:
                from nexus_bot.modservice import ModError

                svc = mod.svc  # type: ignore[union-attr]
                duration = timeout_minutes * 60 if action == "timeout" else None
                reason = t(loc, "hp.reason") + (f" · {t(loc, 'hp.strike', n=strikes)}" if strikes > 1 else "")
                await svc.apply(guild, member, action, moderator=None, reason=reason,
                                duration=duration, source="system",
                                delete_message_days=1 if action in ("ban", "softban") else None)
                action_text = t(loc, f"hp.act_{action}", minutes=timeout_minutes)
            except ModError as exc:
                action_text = t(loc, "hp.act_failed", error=t(loc, exc.key, **exc.params))
            except Exception:  # noqa: BLE001 — la alerta al staff debe salir igualmente
                log.exception("Honeypot: no se pudo sancionar a %s", member.id)
                action_text = t(loc, "hp.act_failed", error="?")
        if step is not None:
            action_text += f" · {t(loc, 'hp.escalated', n=step.count)}"
        await self._alert(guild, cfg, member, action_text, deleted, where, excerpt, strikes)

    async def _alert(self, guild: discord.Guild, cfg: HoneypotConfig, member: discord.Member, action: str,
                     deleted: int, where: list[str], excerpt: str, strikes: int = 1) -> None:
        loc = self.loc(guild.id)
        channel_id = cfg.alert_channel_id
        if not channel_id:
            mod = self.bot.get_cog("Moderation")
            channel_id = mod.svc.config(guild.id).log_channel_id if mod else None  # type: ignore[union-attr]
        channel = guild.get_channel(channel_id or 0)
        if not isinstance(channel, discord.abc.Messageable):
            return
        e = discord.Embed(title=t(loc, "hp.alert_title"), color=0xF59E0B, timestamp=discord.utils.utcnow())
        e.add_field(name=t(loc, "hp.user"), value=f"{member.mention} (`{member.id}`)")
        e.add_field(name=t(loc, "hp.action"), value=action)
        e.add_field(name=t(loc, "hp.deleted"), value=str(deleted))
        e.add_field(name=t(loc, "hp.times"), value=t(loc, "hp.strike", n=strikes))
        if where:
            e.add_field(name=t(loc, "hp.where"), value=" ".join(where)[:1000], inline=False)
        if excerpt:
            e.add_field(name=t(loc, "hp.message"), value=f"```{discord.utils.escape_markdown(excerpt)[:900]}```",
                        inline=False)
        e.set_thumbnail(url=member.display_avatar.url)
        try:
            await channel.send(embed=e, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    # --- Panel: crear el canal y publicar el aviso -------------------------------------------
    async def _publish(self, guild: discord.Guild, channel: discord.TextChannel, cfg: HoneypotConfig) -> discord.Message:
        state = self.bot.cache.get(guild.id)
        kwargs = await with_media(guild.id, render_payload(cfg.message, context_for(guild.me, guild, channel.id, state.locale,
                                                                    state.timezone), state.embed_color))
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
        if cfg.message_id:
            try:
                msg = await channel.fetch_message(cfg.message_id)
                await msg.edit(**for_edit(kwargs))
                return msg
            except discord.HTTPException:
                pass
        msg = await channel.send(**kwargs)
        for emoji in ("🍯", "🤖", "🚫"):  # se puede reaccionar, pero no escribir
            try:
                await msg.add_reaction(emoji)
            except discord.HTTPException:
                break
        return msg

    async def _save(self, guild_id: int, cfg: HoneypotConfig) -> None:
        async with sessionmaker()() as db:
            await db.execute(update(ModuleConfig).where(ModuleConfig.guild_id == guild_id,
                                                        ModuleConfig.module == "honeypot")
                             .values(config=cfg.model_dump(mode="json"), version=ModuleConfig.version + 1,
                                     updated_at=utcnow()))
            await db.commit()
        await self.bot.cache.reload_module(guild_id, "honeypot")

    async def _load(self, guild_id: int) -> HoneypotConfig:
        from nexus_bot.client import RpcFailure

        async with sessionmaker()() as db:
            row = await db.get(ModuleConfig, (guild_id, "honeypot"))
        if row is None or not row.enabled:
            raise RpcFailure("module_disabled")
        return parse_config("honeypot", row.config, self.loc(guild_id))  # type: ignore[return-value]

    async def rpc_setup(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea el canal «honeypot» arriba del todo, publica el aviso y lo guarda en la configuración."""
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        if guild is None:
            raise RpcFailure("not_found")
        cfg = await self._load(guild.id)
        name = "honeypot"
        try:
            channel = await guild.create_text_channel(name, position=0, reason="NEXUS honeypot")
            cfg.channel_id, cfg.message_id = channel.id, None
            msg = await self._publish(guild, channel, cfg)
        except discord.Forbidden as exc:
            raise RpcFailure("bot_missing_permissions") from exc
        cfg.message_id = msg.id
        await self._save(guild.id, cfg)
        return {"channel_id": str(channel.id), "message_id": str(msg.id)}

    async def rpc_publish(self, params: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        if guild is None:
            raise RpcFailure("not_found")
        cfg = await self._load(guild.id)
        channel = guild.get_channel(cfg.channel_id or 0)
        if not isinstance(channel, discord.TextChannel):
            raise RpcFailure("channel_not_found")
        try:
            msg = await self._publish(guild, channel, cfg)
        except discord.Forbidden as exc:
            raise RpcFailure("bot_cannot_send") from exc
        cfg.message_id = msg.id
        await self._save(guild.id, cfg)
        return {"message_id": str(msg.id), "jump_url": msg.jump_url}


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Honeypot(bot))
