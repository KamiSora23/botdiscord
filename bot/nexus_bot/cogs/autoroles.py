"""Autoroles: roles automáticos al entrar (personas y bots por separado)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from nexus_core.discord.permissions import is_dangerous
from nexus_core.modules import parse_config
from nexus_core.modules.roles import AutorolesConfig

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.autoroles")


class Autoroles(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot

    def _cfg(self, guild_id: int) -> AutorolesConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("autoroles")
        return parse_config("autoroles", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    async def _give(self, member: discord.Member, cfg: AutorolesConfig) -> None:
        ids = cfg.bot_role_ids if member.bot else cfg.human_role_ids
        me = member.guild.me
        roles = []
        for rid in ids:
            role = member.guild.get_role(rid)
            if role is None:
                log.warning("Autoroles en %s: el rol %s ya no existe", member.guild.id, rid)
            elif role.managed or not role < me.top_role:
                log.warning("Autoroles en %s: el rol «%s» está por encima del de NEXUS o es de una integración",
                            member.guild.id, role.name)
            elif is_dangerous(role.permissions.value):
                log.warning("Autoroles en %s: el rol «%s» tiene permisos de staff y no se reparte",
                            member.guild.id, role.name)
            else:
                roles.append(role)
        if not roles:
            return
        try:
            await member.add_roles(*roles, reason="NEXUS autoroles")
            log.info("Autoroles en %s: %s recibió %s", member.guild.id, member.id, ", ".join(r.name for r in roles))
        except discord.HTTPException:
            log.warning("Autoroles en %s: Discord no dejó dar los roles a %s", member.guild.id, member.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = self._cfg(member.guild.id)
        if cfg is None:
            return
        if cfg.wait_for_screening and member.pending and not member.bot:
            return  # se dan en on_member_update cuando acepte las reglas
        if cfg.delay_seconds:
            await asyncio.sleep(cfg.delay_seconds)
            member = member.guild.get_member(member.id) or member
            if member.guild.get_member(member.id) is None:
                return  # se fue antes de tiempo
        await self._give(member, cfg)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.pending and not after.pending:
            cfg = self._cfg(after.guild.id)
            if cfg and cfg.wait_for_screening:
                if cfg.delay_seconds:
                    await asyncio.sleep(cfg.delay_seconds)
                await self._give(after, cfg)


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Autoroles(bot))
