"""Registro de módulos. Añadir un módulo = añadir una entrada aquí + su esquema."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

CURRENT_PHASE = 7


@dataclass(frozen=True)
class ModuleInfo:
    key: str
    category: str
    phase: int
    toggleable: bool = True  # False = herramienta sin interruptor (p. ej. el editor de embeds)

    @property
    def available(self) -> bool:
        return self.phase <= CURRENT_PHASE


REGISTRY: dict[str, ModuleInfo] = {
    m.key: m
    for m in [
        ModuleInfo("welcome", "general", 2),
        ModuleInfo("embeds", "general", 2, toggleable=False),
        ModuleInfo("moderation", "moderation", 3),
        ModuleInfo("automod", "moderation", 3),
        ModuleInfo("antiraid", "moderation", 7),
        ModuleInfo("honeypot", "moderation", 7),
        ModuleInfo("ai_moderation", "moderation", 7),
        ModuleInfo("logging", "moderation", 3),
        ModuleInfo("autoroles", "roles", 4),
        ModuleInfo("reaction_roles", "roles", 4),
        ModuleInfo("tickets", "community", 5),
        ModuleInfo("suggestions", "community", 5),
        ModuleInfo("starboard", "community", 5),
        ModuleInfo("polls", "community", 5),
        ModuleInfo("giveaways", "community", 5),
        ModuleInfo("custom_commands", "community", 5, toggleable=False),
        ModuleInfo("responses", "community", 7),
        ModuleInfo("levels", "progression", 6),
        ModuleInfo("economy", "progression", 6),
        ModuleInfo("scheduled_messages", "utility", 5),
        ModuleInfo("integrations", "utility", 7),
        ModuleInfo("tempvoice", "utility", 7),
        ModuleInfo("voice_activity", "utility", 7),
        ModuleInfo("counters", "utility", 7),
        ModuleInfo("events", "community", 7),
    ]
}


@dataclass(frozen=True)
class ModuleSchema:
    model: type[BaseModel]
    default: Callable[[str], BaseModel]


def schemas() -> dict[str, ModuleSchema]:
    """Esquemas de configuración por módulo (se importan aquí para evitar ciclos)."""
    from nexus_core.modules import antiraid as ar
    from nexus_core.modules import honeypot as hp
    from nexus_core.modules import moderation as mod
    from nexus_core.modules import community as cm
    from nexus_core.modules import integrations as ig
    from nexus_core.modules import progression as pg
    from nexus_core.modules import counters, events, responses, roles, tempvoice, voice_activity, welcome

    return {
        "welcome": ModuleSchema(welcome.WelcomeConfig, welcome.default_config),
        "moderation": ModuleSchema(mod.ModerationConfig, mod.moderation_default),
        "automod": ModuleSchema(mod.AutomodConfig, mod.automod_default),
        "antiraid": ModuleSchema(ar.AntiraidConfig, ar.antiraid_default),
        "honeypot": ModuleSchema(hp.HoneypotConfig, hp.honeypot_default),
        "logging": ModuleSchema(mod.LoggingConfig, mod.logging_default),
        "autoroles": ModuleSchema(roles.AutorolesConfig, roles.autoroles_default),
        "reaction_roles": ModuleSchema(roles.ReactionRolesConfig, roles.reaction_roles_default),
        "tickets": ModuleSchema(cm.TicketsConfig, cm.tickets_default),
        "suggestions": ModuleSchema(cm.SuggestionsConfig, cm.suggestions_default),
        "starboard": ModuleSchema(cm.StarboardConfig, cm.starboard_default),
        "giveaways": ModuleSchema(cm.GiveawaysConfig, cm.giveaways_default),
        "polls": ModuleSchema(cm.PollsConfig, cm.polls_default),
        "scheduled_messages": ModuleSchema(cm.EmptyConfig, cm.empty_default),
        "custom_commands": ModuleSchema(cm.EmptyConfig, cm.empty_default),
        "responses": ModuleSchema(responses.ResponsesConfig, responses.responses_default),
        "levels": ModuleSchema(pg.LevelsConfig, pg.levels_default),
        "economy": ModuleSchema(pg.EconomyConfig, pg.economy_default),
        "integrations": ModuleSchema(ig.IntegrationsConfig, ig.integrations_default),
        "ai_moderation": ModuleSchema(ig.AIModerationConfig, ig.ai_default),
        "tempvoice": ModuleSchema(tempvoice.TempVoiceConfig, tempvoice.tempvoice_default),
        "voice_activity": ModuleSchema(voice_activity.VoiceActivityConfig, voice_activity.voice_activity_default),
        "counters": ModuleSchema(counters.CountersConfig, counters.counters_default),
        "events": ModuleSchema(events.EventsConfig, events.events_default),
    }


def available_modules() -> list[ModuleInfo]:
    return [m for m in REGISTRY.values() if m.available]


def parse_config(module: str, data: dict[str, Any], locale: str = "es") -> BaseModel:
    """Valida la configuración guardada; si está vacía, devuelve los valores por defecto."""
    schema = schemas()[module]
    if not data:
        return schema.default(locale)
    return schema.model.model_validate(data)
