"""Actividad de voz: quién entra a los canales de voz, cuánto tiempo está y estadísticas.

Solo se guardan metadatos (miembro, canal, hora de entrada y salida). Nunca audio.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from nexus_core.messages.template import Snowflake


class VoiceActivityConfig(BaseModel):
    retention_days: int = Field(90, ge=7, le=365)  # el historial más antiguo se borra solo
    ignored_channel_ids: list[Snowflake] = Field(default_factory=list, max_length=100)
    ignore_afk: bool = True  # no contar el canal AFK del servidor


def voice_activity_default(locale: str = "es") -> VoiceActivityConfig:
    return VoiceActivityConfig()


def format_duration(seconds: int | float, locale: str = "es") -> str:
    """3725 → «1 h 2 min». Menos de un minuto → «45 s»."""
    s = max(0, int(seconds))
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    d = "d"
    parts = []
    if days:
        parts.append(f"{days} {d}")
    if hours:
        parts.append(f"{hours} h")
    if minutes and days == 0:
        parts.append(f"{minutes} min")
    if not parts:
        parts.append(f"{secs} s")
    return " ".join(parts)
