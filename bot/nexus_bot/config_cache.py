"""Caché de configuración por servidor (docs/NEXUS_API_SPEC.md §7.2).

Los eventos de Discord leen de aquí, nunca directamente de PostgreSQL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from nexus_core.db import sessionmaker
from nexus_core.db.models import DEFAULT_EMBED_COLOR, AutomodRule, GuildConfig, ModuleConfig
from nexus_core.db.repo import utcnow

log = logging.getLogger("nexus.bot.cache")


def _rule_dict(r: AutomodRule) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "enabled": r.enabled, "rule_type": r.rule_type, "config": r.config,
            "actions": r.actions, "exempt_role_ids": list(r.exempt_role_ids),
            "exempt_channel_ids": list(r.exempt_channel_ids), "priority": r.priority, "test_mode": r.test_mode}


@dataclass
class ModuleState:
    enabled: bool
    config: dict[str, Any]
    version: int


@dataclass
class GuildState:
    locale: str = "es"
    timezone: str = "UTC"
    embed_color: int = DEFAULT_EMBED_COLOR
    settings_version: int = 0
    modules: dict[str, ModuleState] = field(default_factory=dict)
    automod_rules: list[dict[str, Any]] = field(default_factory=list)

    def module(self, name: str) -> ModuleState | None:
        m = self.modules.get(name)
        return m if m and m.enabled else None


class ConfigCache:
    def __init__(self) -> None:
        self._guilds: dict[int, GuildState] = {}
        self._last_check: datetime = utcnow()

    def get(self, guild_id: int) -> GuildState:
        return self._guilds.get(guild_id) or GuildState()

    def __contains__(self, guild_id: int) -> bool:
        return guild_id in self._guilds

    async def load_all(self, guild_ids: list[int]) -> None:
        started = utcnow()
        self._guilds = {gid: GuildState() for gid in guild_ids}
        if not guild_ids:
            self._last_check = started
            return
        async with sessionmaker()() as db:
            for cfg in (await db.scalars(
                    select(GuildConfig).where(GuildConfig.guild_id.in_(guild_ids)))).all():
                self._apply_settings(cfg)
            for mod in (await db.scalars(
                    select(ModuleConfig).where(ModuleConfig.guild_id.in_(guild_ids)))).all():
                self._apply_module(mod)
            for rule in (await db.scalars(
                    select(AutomodRule).where(AutomodRule.guild_id.in_(guild_ids)))).all():
                self._guilds[rule.guild_id].automod_rules.append(_rule_dict(rule))
        self._last_check = started
        log.info("Configuración cargada para %d servidores", len(guild_ids))

    async def reload_guild(self, guild_id: int) -> None:
        self._guilds[guild_id] = GuildState()
        async with sessionmaker()() as db:
            cfg = await db.get(GuildConfig, guild_id)
            if cfg:
                self._apply_settings(cfg)
            for mod in (await db.scalars(
                    select(ModuleConfig).where(ModuleConfig.guild_id == guild_id))).all():
                self._apply_module(mod)
            await self._load_rules(db, guild_id)

    async def _load_rules(self, db: Any, guild_id: int) -> None:
        rules = (await db.scalars(select(AutomodRule).where(AutomodRule.guild_id == guild_id))).all()
        self._guilds.setdefault(guild_id, GuildState()).automod_rules = [_rule_dict(r) for r in rules]

    async def reload_settings(self, guild_id: int, version: int | None = None) -> None:
        state = self._guilds.get(guild_id)
        if state is None:
            return await self.reload_guild(guild_id)
        if version is not None and version <= state.settings_version:
            return
        async with sessionmaker()() as db:
            cfg = await db.get(GuildConfig, guild_id)
            if cfg:
                self._apply_settings(cfg)

    async def reload_module(self, guild_id: int, module: str, version: int | None = None) -> None:
        state = self._guilds.get(guild_id)
        if state is None:
            return await self.reload_guild(guild_id)
        if module == "automod":
            # Las reglas viven en su propia tabla y no llevan versión en el aviso: siempre se recargan.
            async with sessionmaker()() as db:
                await self._load_rules(db, guild_id)
                mod = await db.get(ModuleConfig, (guild_id, module))
                if mod:
                    self._apply_module(mod)
            return
        current = state.modules.get(module)
        if version is not None and current is not None and version <= current.version:
            return
        async with sessionmaker()() as db:
            mod = await db.get(ModuleConfig, (guild_id, module))
            if mod:
                self._apply_module(mod)
            else:
                state.modules.pop(module, None)

    def forget(self, guild_id: int) -> None:
        self._guilds.pop(guild_id, None)

    async def check_updates(self) -> int:
        """Recuperación: recarga lo que cambió desde la última revisión (avisos perdidos)."""
        # Margen por si los relojes de la base de datos y del bot no coinciden exactamente.
        since = self._last_check - timedelta(seconds=10)
        started = utcnow()
        changed = 0
        async with sessionmaker()() as db:
            for cfg in (await db.scalars(
                    select(GuildConfig).where(GuildConfig.updated_at > since))).all():
                if cfg.guild_id in self._guilds:
                    self._apply_settings(cfg)
                    changed += 1
            for mod in (await db.scalars(
                    select(ModuleConfig).where(ModuleConfig.updated_at > since))).all():
                if mod.guild_id in self._guilds:
                    self._apply_module(mod)
                    changed += 1
        self._last_check = started
        return changed

    def _apply_settings(self, cfg: GuildConfig) -> None:
        state = self._guilds.setdefault(cfg.guild_id, GuildState())
        state.locale = cfg.locale
        state.timezone = cfg.timezone
        state.embed_color = cfg.embed_color
        state.settings_version = cfg.version

    def _apply_module(self, mod: ModuleConfig) -> None:
        state = self._guilds.setdefault(mod.guild_id, GuildState())
        state.modules[mod.module] = ModuleState(mod.enabled, mod.config, mod.version)
