"""Contadores: canales de voz bloqueados arriba del todo con cifras en vivo («👥 Miembros: 1.420»)."""

from __future__ import annotations

import secrets
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from nexus_core.messages.template import OptSnowflake

CounterType = Literal["members", "humans", "bots", "boosts", "channels", "roles", "in_voice"]

# Discord solo deja renombrar un canal 2 veces cada 10 minutos: no se actualiza más a menudo.
UPDATE_MINUTES = 10

DEFAULT_TEMPLATES: dict[str, dict[str, str]] = {
    "es": {"members": "👥 Miembros: {count}", "humans": "🙂 Personas: {count}", "bots": "🤖 Bots: {count}",
           "boosts": "🚀 Mejoras: {count}", "channels": "💬 Canales: {count}", "roles": "🏷️ Roles: {count}",
           "in_voice": "🔊 En voz: {count}"},
    "en": {"members": "👥 Members: {count}", "humans": "🙂 Humans: {count}", "bots": "🤖 Bots: {count}",
           "boosts": "🚀 Boosts: {count}", "channels": "💬 Channels: {count}", "roles": "🏷️ Roles: {count}",
           "in_voice": "🔊 In voice: {count}"},
}


class Counter(BaseModel):
    id: str = Field(default_factory=lambda: secrets.token_hex(4), pattern=r"^[a-f0-9]{8}$")
    type: CounterType = "members"
    template: str = Field("👥 Miembros: {count}", min_length=1, max_length=90)
    channel_id: OptSnowflake = None  # canal de voz bloqueado; lo crea el bot

    @field_validator("template")
    @classmethod
    def _tpl(cls, v: str) -> str:
        if "{count}" not in v:
            raise ValueError("count_required")
        return v


class CountersConfig(BaseModel):
    category_id: OptSnowflake = None
    counters: list[Counter] = Field(default_factory=list, max_length=10)


def counters_default(locale: str = "es") -> CountersConfig:
    tpl = DEFAULT_TEMPLATES.get(locale, DEFAULT_TEMPLATES["es"])
    return CountersConfig(counters=[Counter(type="members", template=tpl["members"]),
                                    Counter(type="humans", template=tpl["humans"])])


def format_count(n: int, locale: str = "es") -> str:
    """1420 → «1.420» (es) o «1,420» (en)."""
    s = f"{n:,}"
    return s.replace(",", ".") if locale == "es" else s


def render_name(template: str, n: int, locale: str = "es") -> str:
    return template.replace("{count}", format_count(n, locale))[:100]
