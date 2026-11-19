"""Contadores: canales de voz bloqueados cuyo nombre muestra una cifra en vivo (miembros, bots, mejoras…)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands, tasks
from sqlalchemy import update

from nexus_core.db import sessionmaker
from nexus_core.db.models import ModuleConfig
from nexus_core.db.repo import utcnow
from nexus_core.modules import parse_config
from nexus_core.modules.counters import UPDATE_MINUTES, CountersConfig, render_name

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.counters")


def count(guild: discord.Guild, kind: str) -> int:
    if kind == "members":
        return guild.member_count or len(guild.members)
    if kind == "humans":
        return sum(1 for m in guild.members if not m.bot)
    if kind == "bots":
        return sum(1 for m in guild.members if m.bot)
    if kind == "boosts":
        return guild.premium_subscription_count or 0
    if kind == "channels":
        return sum(1 for c in guild.channels if not isinstance(c, discord.CategoryChannel))
    if kind == "roles":
        return max(0, len(guild.roles) - 1)
    if kind == "in_voice":
        return sum(sum(1 for m in c.members if not m.bot) for c in (*guild.voice_channels, *guild.stage_channels))
    return 0


class Counters(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        bot.rpc_handlers["counters.setup"] = self.rpc_setup
        bot.rpc_handlers["counters.refresh"] = self.rpc_refresh
        self.loop.start()

    def cog_unload(self) -> None:
        self.loop.cancel()

    def cfg(self, guild_id: int) -> CountersConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("counters")
        return parse_config("counters", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    async def refresh(self, guild: discord.Guild) -> int:
        """Renombra los canales cuyo número cambió. Devuelve cuántos se actualizaron."""
        cfg = self.cfg(guild.id)
        if cfg is None:
            return 0
        loc = self.bot.cache.get(guild.id).locale
        changed = 0
        for c in cfg.counters:
            channel = guild.get_channel(c.channel_id or 0)
            if channel is None:
                continue
            name = render_name(c.template, count(guild, c.type), loc)
            if channel.name == name:
                continue
            try:
                await channel.edit(name=name, reason="NEXUS contadores")
                changed += 1
            except discord.HTTPException as exc:  # p. ej. límite de 2 cambios de nombre cada 10 minutos
                log.info("Contador %s en %s no actualizado: %s", c.id, guild.id, exc)
        return changed

    @tasks.loop(minutes=UPDATE_MINUTES)
    async def loop(self) -> None:
        for guild in self.bot.guilds:
            if self.cfg(guild.id) is not None:
                await self.refresh(guild)

    @loop.before_loop
    async def _ready(self) -> None:
        await self.bot.wait_until_ready()

    # --- Panel ---------------------------------------------------------------------------
    async def rpc_setup(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea (o completa) la categoría «📊 Estadísticas» y un canal de voz bloqueado por contador."""
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        async with sessionmaker()() as db:
            row = await db.get(ModuleConfig, (int(params["guild_id"]), "counters"))
        if guild is None or row is None or not row.enabled:
            raise RpcFailure("module_disabled")
        loc = self.bot.cache.get(guild.id).locale
        cfg: CountersConfig = parse_config("counters", row.config, loc)  # type: ignore[assignment]
        locked = {guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=False),
                  guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True)}
        try:
            category = guild.get_channel(cfg.category_id or 0)
            if not isinstance(category, discord.CategoryChannel):
                category = await guild.create_category("📊 Estadísticas" if loc == "es" else "📊 Stats",
                                                       overwrites=locked, position=0, reason="NEXUS contadores")
                cfg.category_id = category.id
            created = 0
            for c in cfg.counters:
                if guild.get_channel(c.channel_id or 0) is not None:
                    continue
                ch = await guild.create_voice_channel(render_name(c.template, count(guild, c.type), loc),
                                                      category=category, overwrites=locked, reason="NEXUS contadores")
                c.channel_id = ch.id
                created += 1
        except discord.Forbidden as exc:
            raise RpcFailure("bot_missing_permissions") from exc
        async with sessionmaker()() as db:
            await db.execute(update(ModuleConfig).where(ModuleConfig.guild_id == guild.id,
                                                        ModuleConfig.module == "counters")
                             .values(config=cfg.model_dump(mode="json"), version=ModuleConfig.version + 1,
                                     updated_at=utcnow()))
            await db.commit()
        await self.bot.cache.reload_module(guild.id, "counters")
        return {"created": created, "category_id": str(cfg.category_id)}

    async def rpc_refresh(self, params: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        if guild is None:
            raise RpcFailure("not_found")
        return {"changed": await self.refresh(guild),
                "values": {k: count(guild, k) for k in ("members", "humans", "bots", "boosts", "channels",
                                                        "roles", "in_voice")}}


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Counters(bot))
