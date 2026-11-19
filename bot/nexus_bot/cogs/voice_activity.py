"""Actividad de voz: registra quién entra a los canales de voz y cuánto tiempo está (sin audio)."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks
from sqlalchemy import BigInteger, cast, delete, func, select, update

from nexus_core.db import sessionmaker
from nexus_core.db.models import VoiceSession
from nexus_core.db.repo import utcnow
from nexus_core.i18n import t
from nexus_core.modules import parse_config
from nexus_core.modules.voice_activity import VoiceActivityConfig, format_duration

from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.voice_activity")

BLUE, GREY, PURPLE = 0x3B82F6, 0x6B7280, 0x7465F7
PERIODS = [app_commands.Choice(name=key("va.p7"), value=7), app_commands.Choice(name=key("va.p30"), value=30),
           app_commands.Choice(name=key("va.p0"), value=0)]


def seconds_expr():
    """Duración de cada sesión; las abiertas cuentan hasta ahora."""
    return cast(func.coalesce(VoiceSession.duration_seconds,
                              func.extract("epoch", func.now() - VoiceSession.joined_at)), BigInteger)


class VoiceActivity(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self._synced = False
        self.heartbeat.start()

    def cog_unload(self) -> None:
        self.heartbeat.cancel()

    def cfg(self, guild_id: int) -> VoiceActivityConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("voice_activity")
        return parse_config("voice_activity", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    def loc(self, guild_id: int | None) -> str:
        return self.bot.cache.get(guild_id or 0).locale

    def _tracked(self, channel: discord.abc.GuildChannel | None, cfg: VoiceActivityConfig | None) -> bool:
        if channel is None or cfg is None:
            return False
        if channel.id in set(cfg.ignored_channel_ids):
            return False
        return not (cfg.ignore_afk and channel.guild.afk_channel and channel.id == channel.guild.afk_channel.id)

    # --- Sesiones ---------------------------------------------------------------------------
    async def _open(self, member: discord.Member, channel: discord.abc.GuildChannel) -> None:
        now = utcnow()
        async with sessionmaker()() as db:
            db.add(VoiceSession(guild_id=member.guild.id, user_id=member.id, user_name=member.display_name[:100],
                                channel_id=channel.id, channel_name=channel.name[:100], joined_at=now,
                                last_seen_at=now))
            await db.commit()

    async def _close(self, guild_id: int, user_id: int, at=None) -> int | None:  # type: ignore[no-untyped-def]
        """Cierra la sesión abierta del miembro; devuelve su duración en segundos."""
        at = at or utcnow()
        async with sessionmaker()() as db:
            row = await db.scalar(select(VoiceSession).where(
                VoiceSession.guild_id == guild_id, VoiceSession.user_id == user_id, VoiceSession.left_at.is_(None))
                .order_by(VoiceSession.joined_at.desc()).limit(1))
            if row is None:
                return None
            row.left_at = max(at, row.joined_at)
            row.last_seen_at = row.left_at
            row.duration_seconds = int((row.left_at - row.joined_at).total_seconds())
            # Por si quedó alguna más abierta (no debería): cerrarla también.
            await db.execute(update(VoiceSession).where(
                VoiceSession.guild_id == guild_id, VoiceSession.user_id == user_id, VoiceSession.left_at.is_(None),
                VoiceSession.id != row.id).values(left_at=at, duration_seconds=0))
            duration = row.duration_seconds
            await db.commit()
        return duration

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if member.bot or before.channel == after.channel:
            return  # silenciarse, ensordecerse o compartir pantalla no es entrar ni salir
        cfg = self.cfg(member.guild.id)
        duration = None
        if before.channel is not None:
            duration = await self._close(member.guild.id, member.id)
        if after.channel is not None and self._tracked(after.channel, cfg):
            await self._open(member, after.channel)
        await self._log(member, before.channel, after.channel, duration)

    async def _log(self, member: discord.Member, before: discord.abc.GuildChannel | None,
                   after: discord.abc.GuildChannel | None, duration: int | None) -> None:
        logcog = self.bot.get_cog("Logging")
        if logcog is None:
            return
        loc = self.loc(member.guild.id)
        if before and after:
            event, color, title = "voice_move", PURPLE, t(loc, "log.voice_move")
        elif after:
            event, color, title = "voice_join", BLUE, t(loc, "log.voice_join")
        else:
            event, color, title = "voice_leave", GREY, t(loc, "log.voice_leave")
        e = discord.Embed(title=title, color=color, description=f"{member.mention} ({member})")
        if before and after:
            e.add_field(name=t(loc, "log.voice_from"), value=before.mention)
            e.add_field(name=t(loc, "log.voice_to"), value=after.mention)
        else:
            e.add_field(name=t(loc, "log.voice_channel"), value=(after or before).mention)  # type: ignore[union-attr]
        if duration is not None and before is not None:
            e.add_field(name=t(loc, "log.voice_stayed"), value=format_duration(duration, loc))
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text=f"ID {member.id}")
        await logcog._send(member.guild, event, e)  # type: ignore[attr-defined]

    # --- Mantenimiento: latido, recuperación tras reinicio y limpieza ---------------------
    @tasks.loop(minutes=2)
    async def heartbeat(self) -> None:
        now = utcnow()
        if not self._synced:
            await self._recover(now)
            self._synced = True
        async with sessionmaker()() as db:
            await db.execute(update(VoiceSession).where(VoiceSession.left_at.is_(None)).values(last_seen_at=now))
            await db.commit()
        if self.heartbeat.current_loop % 180 == 0:  # ~cada 6 horas
            await self._cleanup(now)

    @heartbeat.before_loop
    async def _wait_ready(self) -> None:
        await self.bot.wait_until_ready()

    async def _recover(self, now) -> None:  # type: ignore[no-untyped-def]
        """Tras un reinicio: cierra lo que quedó abierto sin el bot y abre las sesiones de quien ya está en voz."""
        async with sessionmaker()() as db:
            rows = (await db.scalars(select(VoiceSession).where(VoiceSession.left_at.is_(None)))).all()
            still = set()
            for r in rows:
                guild = self.bot.get_guild(r.guild_id)
                member = guild.get_member(r.user_id) if guild else None
                if member and member.voice and member.voice.channel and member.voice.channel.id == r.channel_id:
                    still.add((r.guild_id, r.user_id))  # sigue en el mismo canal: la sesión continúa
                    continue
                r.left_at = max(r.last_seen_at, r.joined_at)  # se fue mientras el bot no estaba: hasta el último latido
                r.duration_seconds = int((r.left_at - r.joined_at).total_seconds())
            await db.commit()
        for guild in self.bot.guilds:
            cfg = self.cfg(guild.id)
            for channel in guild.voice_channels + guild.stage_channels:
                if not self._tracked(channel, cfg):
                    continue
                for member in channel.members:
                    if not member.bot and (guild.id, member.id) not in still:
                        await self._open(member, channel)
        log.info("Actividad de voz recuperada tras el arranque (%s sesiones siguen abiertas)", len(still))

    async def _cleanup(self, now) -> None:  # type: ignore[no-untyped-def]
        for guild in self.bot.guilds:
            cfg = self.cfg(guild.id)
            days = cfg.retention_days if cfg else 90
            async with sessionmaker()() as db:
                await db.execute(delete(VoiceSession).where(VoiceSession.guild_id == guild.id,
                                                            VoiceSession.joined_at < now - timedelta(days=days)))
                await db.commit()

    # --- Comandos ---------------------------------------------------------------------------------
    async def _check(self, i: discord.Interaction) -> bool:
        if i.guild_id and self.cfg(i.guild_id) is None:
            await i.response.send_message(t(self.loc(i.guild_id), "va.disabled"), ephemeral=True)
            return False
        return True

    @app_commands.command(name=key("cmd.voicetime.name"), description=key("cmd.voicetime.description"))
    @app_commands.guild_only()
    @app_commands.describe(user=key("arg.target_user"), period=key("arg.period"))
    @app_commands.choices(period=PERIODS)
    async def voicetime(self, i: discord.Interaction, user: discord.Member | None = None,
                        period: app_commands.Choice[int] | None = None) -> None:
        if not await self._check(i):
            return
        who = user or i.user
        days = period.value if period else 30
        loc = self.loc(i.guild_id)
        conds = [VoiceSession.guild_id == i.guild_id, VoiceSession.user_id == who.id]
        if days:
            conds.append(VoiceSession.joined_at >= utcnow() - timedelta(days=days))
        async with sessionmaker()() as db:
            total, count = (await db.execute(select(func.coalesce(func.sum(seconds_expr()), 0), func.count())
                                             .where(*conds))).one()
            top = (await db.execute(select(VoiceSession.channel_id, VoiceSession.channel_name,
                                           func.sum(seconds_expr()).label("s"))
                                    .where(*conds).group_by(VoiceSession.channel_id, VoiceSession.channel_name)
                                    .order_by(func.sum(seconds_expr()).desc()).limit(3))).all()
            current = await db.scalar(select(VoiceSession).where(*conds[:2], VoiceSession.left_at.is_(None)))
        e = discord.Embed(title=t(loc, "va.title", user=who.display_name), color=PURPLE)
        e.set_thumbnail(url=who.display_avatar.url)
        e.set_footer(text=t(loc, f"va.p{days}"))
        if not count:
            e.description = t(loc, "va.none")
        else:
            e.add_field(name=t(loc, "va.total"), value=f"**{format_duration(total, loc)}**")
            e.add_field(name=t(loc, "va.sessions"), value=str(count))
            if top:
                e.add_field(name=t(loc, "va.top_channels"), inline=False, value="\n".join(
                    f"<#{cid}> · {format_duration(s, loc)}" for cid, _, s in top))
        if current:
            e.add_field(name=t(loc, "va.now"), inline=False, value=t(
                loc, "va.now_in", channel=f"<#{current.channel_id}>",
                since=discord.utils.format_dt(current.joined_at, "R")))
        await i.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name=key("cmd.voicetop.name"), description=key("cmd.voicetop.description"))
    @app_commands.guild_only()
    @app_commands.describe(period=key("arg.period"))
    @app_commands.choices(period=PERIODS)
    async def voicetop(self, i: discord.Interaction, period: app_commands.Choice[int] | None = None) -> None:
        if not await self._check(i):
            return
        days = period.value if period else 7
        loc = self.loc(i.guild_id)
        conds = [VoiceSession.guild_id == i.guild_id]
        if days:
            conds.append(VoiceSession.joined_at >= utcnow() - timedelta(days=days))
        async with sessionmaker()() as db:
            rows = (await db.execute(select(VoiceSession.user_id, func.sum(seconds_expr()).label("s"))
                                     .where(*conds).group_by(VoiceSession.user_id)
                                     .order_by(func.sum(seconds_expr()).desc()).limit(10))).all()
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"{medals[n] if n < 3 else f'`#{n + 1}`'} <@{uid}> · **{format_duration(s, loc)}**"
                 for n, (uid, s) in enumerate(rows)]
        e = discord.Embed(title=t(loc, "va.board_title", period=t(loc, f"va.p{days}")), color=PURPLE,
                          description="\n".join(lines) or t(loc, "va.none"))
        await i.response.send_message(embed=e, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(VoiceActivity(bot))
