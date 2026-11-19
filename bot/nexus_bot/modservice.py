"""Acciones de moderación: jerarquía, aviso por MD, acción en Discord, caso, registro y escalado."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import discord

from nexus_core.cases import active_warn_count, create_case, deactivate_temporary
from nexus_core.db import sessionmaker
from nexus_core.db.models import ModerationCase, ScheduledJob
from nexus_core.db.repo import utcnow
from nexus_core.i18n import t
from nexus_core.modules import parse_config
from nexus_core.modules.moderation import LoggingConfig, ModerationConfig, channel_for

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.mod")

ACTION_COLORS = {"warn": 0xF59E0B, "timeout": 0xF97316, "untimeout": 0x22C55E, "kick": 0xEF4444,
                 "ban": 0xB91C1C, "unban": 0x22C55E, "softban": 0xEF4444, "note": 0x6B7280}


class ModError(Exception):
    """Error que se muestra al moderador (clave de traducción)."""

    def __init__(self, key: str, **params: object):
        super().__init__(key)
        self.key = key
        self.params = params


def human_duration(seconds: int | None, locale: str) -> str:
    if not seconds:
        return t(locale, "mod.permanent")
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size and seconds % size == 0:
            return f"{seconds // size}{unit}"
    return f"{seconds // 60}m"


def parse_duration(text: str | None) -> int | None:
    """'10m', '2h', '7d', '1d12h' → segundos."""
    if not text:
        return None
    import re

    total = 0
    for n, unit in re.findall(r"(\d+)\s*([smhdw])", text.lower()):
        total += int(n) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    return total or None


class ModService:
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot

    def config(self, guild_id: int) -> ModerationConfig:
        state = self.bot.cache.get(guild_id)
        mod = state.modules.get("moderation")
        return parse_config("moderation", mod.config if mod else {}, state.locale)  # type: ignore[return-value]

    def logging_config(self, guild_id: int) -> LoggingConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("logging")
        return parse_config("logging", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    def check_hierarchy(self, guild: discord.Guild, moderator: discord.Member | None,
                        target: discord.Member | discord.User) -> None:
        if not isinstance(target, discord.Member):
            return
        if target.id == guild.owner_id:
            raise ModError("mod.err_owner")
        if moderator and target.id == moderator.id:
            raise ModError("mod.err_self")
        if moderator and moderator.id != guild.owner_id and target.top_role >= moderator.top_role:
            raise ModError("mod.err_hierarchy_you")
        me = guild.me
        if target.top_role >= me.top_role:
            raise ModError("mod.err_hierarchy_bot")

    async def _dm(self, target: discord.abc.User, guild: discord.Guild, action: str, reason: str | None,
                  duration: int | None) -> None:
        loc = self.bot.cache.get(guild.id).locale
        embed = discord.Embed(
            title=t(loc, f"mod.dm_{action}", server=guild.name),
            description=t(loc, "mod.reason_line", reason=reason or t(loc, "mod.no_reason")),
            color=ACTION_COLORS.get(action, 0x6B7280),
        )
        if duration:
            embed.add_field(name=t(loc, "mod.duration"), value=human_duration(duration, loc))
        try:
            await target.send(embed=embed)
        except discord.HTTPException:
            pass

    async def apply(self, guild: discord.Guild, target: discord.Member | discord.User, action: str, *,
                    moderator: discord.Member | None, reason: str | None, duration: int | None = None,
                    source: str = "manual", delete_message_days: int | None = None) -> ModerationCase:
        cfg = self.config(guild.id)
        if source == "manual" and cfg.require_reason and not reason and action not in ("unban", "untimeout"):
            raise ModError("mod.err_reason_required")
        if action in ("timeout", "kick", "ban", "softban"):
            self.check_hierarchy(guild, moderator, target)
        member = target if isinstance(target, discord.Member) else guild.get_member(target.id)
        audit_reason = f"{moderator or 'NEXUS'}: {reason or '-'}"[:500]

        if cfg.dm_on_action and action in ("warn", "timeout", "kick", "ban", "softban"):
            await self._dm(target, guild, action, reason, duration)
        try:
            if action == "timeout":
                if member is None:
                    raise ModError("mod.err_not_member")
                await member.timeout(timedelta(seconds=min(duration or 600, 2419200)), reason=audit_reason)
            elif action == "untimeout":
                if member is None:
                    raise ModError("mod.err_not_member")
                await member.timeout(None, reason=audit_reason)
            elif action == "kick":
                if member is None:
                    raise ModError("mod.err_not_member")
                await member.kick(reason=audit_reason)
            elif action in ("ban", "softban"):
                days = cfg.ban_delete_message_days if delete_message_days is None else delete_message_days
                await guild.ban(target, reason=audit_reason, delete_message_seconds=days * 86400)
                if action == "softban":
                    await guild.unban(target, reason=audit_reason)
            elif action == "unban":
                await guild.unban(target, reason=audit_reason)
        except discord.Forbidden as exc:
            raise ModError("mod.err_bot_permission") from exc
        except discord.NotFound as exc:
            raise ModError("mod.err_not_found") from exc

        async with sessionmaker()() as db:
            if action in ("untimeout", "unban"):
                await deactivate_temporary(db, guild.id, target.id, "timeout" if action == "untimeout" else "ban")
            expires = timedelta(days=cfg.warn_expiry_days) if action == "warn" and cfg.warn_expiry_days else None
            case = await create_case(
                db, guild_id=guild.id, target_id=target.id, target_name=str(target), action=action,
                moderator_id=moderator.id if moderator else None,
                moderator_name=str(moderator) if moderator else "NEXUS", reason=reason,
                duration_seconds=duration if action in ("timeout", "ban") else None, source=source,
                expires_in=expires,
            )
            if action == "ban" and duration:
                db.add(ScheduledJob(guild_id=guild.id, job_type="ban.expire", run_at=utcnow() + timedelta(seconds=duration),
                                    payload={"user_id": str(target.id), "case": case.case_number},
                                    dedupe_key=f"ban.expire:{guild.id}:{target.id}"))
            warns = await active_warn_count(db, guild.id, target.id) if action == "warn" else 0
            await db.commit()
        await self.log_case(guild, case)

        if action == "warn":
            step = next((s for s in cfg.escalation if s.warns == warns), None)
            if step:
                loc = self.bot.cache.get(guild.id).locale
                try:
                    await self.apply(guild, target, step.action, moderator=None, duration=step.duration_seconds,
                                     reason=t(loc, "mod.escalation_reason", count=warns), source="system")
                except ModError as exc:
                    log.info("Escalado no aplicado en %s: %s", guild.id, exc.key)
        return case

    async def log_case(self, guild: discord.Guild, case: ModerationCase) -> None:
        cfg = self.config(guild.id)
        lcfg = self.logging_config(guild.id)
        channel_id = cfg.log_channel_id or (channel_for(lcfg, "mod_case") if lcfg else None)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            return
        loc = self.bot.cache.get(guild.id).locale
        embed = discord.Embed(
            title=t(loc, "mod.case_title", number=case.case_number, action=t(loc, f"mod.action_{case.action}")),
            color=ACTION_COLORS.get(case.action, 0x6B7280), timestamp=case.created_at,
        )
        embed.add_field(name=t(loc, "mod.user"), value=f"<@{case.target_id}> ({case.target_name})")
        embed.add_field(name=t(loc, "mod.moderator"), value=f"<@{case.moderator_id}>" if case.moderator_id else "NEXUS")
        if case.duration_seconds:
            embed.add_field(name=t(loc, "mod.duration"), value=human_duration(case.duration_seconds, loc))
        embed.add_field(name=t(loc, "mod.reason"), value=case.reason or t(loc, "mod.no_reason"), inline=False)
        embed.set_footer(text=f"ID {case.target_id} · {case.source}")
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass


async def ban_expire_job(bot: NexusBot, job: ScheduledJob) -> None:
    guild = bot.get_guild(job.guild_id or 0)
    if guild is None:
        return
    user = discord.Object(id=int(job.payload["user_id"]))
    try:
        await guild.unban(user, reason="NEXUS: temporary ban expired")
    except discord.NotFound:
        return
    async with sessionmaker()() as db:
        await deactivate_temporary(db, guild.id, user.id, "ban")
        case = await create_case(db, guild_id=guild.id, target_id=user.id, target_name=str(user.id), action="unban",
                                 moderator_id=None, moderator_name="NEXUS", reason="Temporary ban expired",
                                 source="system")
        await db.commit()
    await ModService(bot).log_case(guild, case)


__all__ = ["ModService", "ModError", "ban_expire_job", "parse_duration", "human_duration"]
