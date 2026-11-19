"""Canales de voz temporales: al entrar en «➕ Crear sala» se crea una sala propia que se borra al quedar vacía."""

from __future__ import annotations

from pydantic import BaseModel, Field

from nexus_core.messages.template import OptSnowflake


class TempVoiceConfig(BaseModel):
    hub_channel_id: OptSnowflake = None  # canal de voz «➕ Crear sala»
    category_id: OptSnowflake = None  # vacío = la categoría del canal «Crear sala»
    name_template: str = Field("Sala de {user}", min_length=1, max_length=90)
    default_limit: int = Field(0, ge=0, le=99)  # 0 = sin límite
    max_rooms_per_user: int = Field(1, ge=1, le=3)


def tempvoice_default(locale: str = "es") -> TempVoiceConfig:
    return TempVoiceConfig(name_template="Sala de {user}" if locale == "es" else "{user}'s room")


def room_name(template: str, display_name: str) -> str:
    """Nombre de la sala a partir de la plantilla ({user} = nombre del miembro). Máx. 100 caracteres."""
    name = template.replace("{user}", display_name).strip()
    return (name or display_name)[:100]
