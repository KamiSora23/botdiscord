"""Anti-raid y verificación: captcha al entrar, cuentas nuevas, detección de raids y cuarentena."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from nexus_core.messages.template import Embed, MessageTemplate, OptSnowflake, Snowflake


class VerificationSettings(BaseModel):
    enabled: bool = False
    channel_id: OptSnowflake = None
    message_id: OptSnowflake = None
    role_id: OptSnowflake = None  # rol que se da al verificarse
    method: Literal["button", "captcha"] = "captcha"
    message: MessageTemplate
    button_label: str = Field("Verificarme", min_length=1, max_length=80)
    # Restricción de canales: quien no está verificado solo ve estos canales (+ el de verificación).
    public_channel_ids: list[Snowflake] = Field(default_factory=list, max_length=10)
    # Estado que escribe el bot al aplicar/deshacer la restricción (no se edita a mano).
    gate_active: bool = False
    # Permisos previos para poder deshacer: "e:<canal>" = @everyone, "r:<canal>" = rol verificado; None = no tenía.
    gate_backup: dict[str, list[int] | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "VerificationSettings":
        if self.enabled and (self.role_id is None or self.channel_id is None):
            raise ValueError("verification_incomplete")
        return self


class AntiraidConfig(BaseModel):
    verification: VerificationSettings
    alert_channel_id: OptSnowflake = None  # vacío = canal de registro de moderación
    # Cuentas nuevas: 0 = desactivado
    min_account_age_days: int = Field(0, ge=0, le=365)
    young_action: Literal["alert", "kick", "quarantine"] = "alert"
    # Raid: N entradas en S segundos
    raid_detection: bool = True
    raid_joins: int = Field(10, ge=3, le=100)
    raid_seconds: int = Field(10, ge=5, le=300)
    raid_action: Literal["alert", "lockdown", "kick"] = "alert"
    raid_minutes: int = Field(10, ge=1, le=120)  # cuánto dura el modo raid tras detectarlo
    quarantine_role_id: OptSnowflake = None

    @model_validator(mode="after")
    def _check(self) -> "AntiraidConfig":
        if self.young_action == "quarantine" and self.min_account_age_days and not self.quarantine_role_id:
            raise ValueError("quarantine_role_required")
        return self


_TEXTS = {
    "es": ("🛡️ Verificación", "Para acceder al servidor pulsa el botón y responde la pregunta.", "Verificarme"),
    "en": ("🛡️ Verification", "To access the server, press the button and answer the question.", "Verify me"),
}


def antiraid_default(locale: str = "es") -> AntiraidConfig:
    title, desc, label = _TEXTS.get(locale, _TEXTS["es"])
    return AntiraidConfig(verification=VerificationSettings(
        message=MessageTemplate(embeds=[Embed(title=title, description=desc)]), button_label=label))


class GateChannel(BaseModel):
    """Datos mínimos de un canal para decidir cómo restringirlo (sin depender de discord.py)."""

    id: int
    is_category: bool = False
    in_category: bool = False
    synced: bool = False  # hereda los permisos de su categoría
    everyone_can_view: bool = True


def plan_gate(channels: list[GateChannel], public_ids: set[int]) -> tuple[list[int], list[int]]:
    """Qué canales se abren explícitamente a @everyone y cuáles se ocultan (y se abren al rol verificado).

    - Los canales que @everyone ya no ve (staff, tickets…) no se tocan: el rol verificado tampoco los verá.
    - Los públicos se abren de forma explícita (así no heredan el ocultado de su categoría).
    - Se ocultan las categorías y los canales que no siguen a su categoría; los sincronizados heredan.
    """
    public, hidden = [], []
    for ch in channels:
        if not ch.everyone_can_view:
            continue
        if ch.id in public_ids:
            public.append(ch.id)
        elif ch.is_category or not ch.in_category or not ch.synced:
            hidden.append(ch.id)
    return public, hidden
