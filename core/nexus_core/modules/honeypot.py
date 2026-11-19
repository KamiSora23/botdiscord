"""Canal trampa (honeypot): quien escribe en él es casi siempre un bot de spam que publica en todos los canales.

Las personas ven el aviso y no escriben; los bots de spam caen. NEXUS borra lo que esa cuenta envió en los
últimos minutos en cualquier canal y aplica la sanción elegida.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from nexus_core.messages.template import Embed, MessageTemplate, OptSnowflake, Snowflake


Action = Literal["delete", "timeout", "kick", "softban", "ban"]


class EscalationStep(BaseModel):
    """«A partir de la vez N» → otra sanción (p. ej. a la 3.ª vez, ban)."""

    count: int = Field(ge=2, le=50)
    action: Action = "ban"
    timeout_minutes: int = Field(1440, ge=1, le=40320)


class HoneypotConfig(BaseModel):
    channel_id: OptSnowflake = None
    message_id: OptSnowflake = None
    message: MessageTemplate
    action: Action = "timeout"
    timeout_minutes: int = Field(60, ge=1, le=40320)  # máx. 28 días (límite de Discord)
    purge_minutes: int = Field(60, ge=0, le=1440)  # borrar lo que envió en los últimos N minutos (0 = solo ese)
    exempt_role_ids: list[Snowflake] = Field(default_factory=list, max_length=20)
    alert_channel_id: OptSnowflake = None  # vacío = canal de registro de Moderación
    # Reincidencia: cuántas veces cayó la misma cuenta en los últimos N días (0 = desde siempre).
    escalation: list[EscalationStep] = Field(default_factory=list, max_length=5)
    strike_window_days: int = Field(30, ge=0, le=365)

    @model_validator(mode="after")
    def _steps(self) -> "HoneypotConfig":
        counts = [st.count for st in self.escalation]
        if len(counts) != len(set(counts)):
            raise ValueError("duplicate_step")
        self.escalation.sort(key=lambda st: st.count)
        return self


_TEXTS = {
    "es": ("🚫 No escribas en este canal",
           "Este canal es una **trampa para bots de spam**.\n\nSi escribes aquí, NEXUS te tratará como spam y "
           "aplicará una sanción automática. Puedes reaccionar, pero **no envíes mensajes**."),
    "en": ("🚫 Don't write in this channel",
           "This channel is a **trap for spam bots**.\n\nIf you write here, NEXUS will treat you as spam and apply an "
           "automatic sanction. You can react, but **don't send messages**."),
}


def honeypot_default(locale: str = "es") -> HoneypotConfig:
    title, desc = _TEXTS.get(locale, _TEXTS["es"])
    return HoneypotConfig(message=MessageTemplate(embeds=[Embed(title=title, description=desc, color=0xEF4444)]))


def is_exempt(*, is_owner: bool, is_staff: bool, is_bot: bool, role_ids: set[int], exempt: list[int]) -> bool:
    """¿Esta cuenta puede escribir en el canal trampa sin sanción?"""
    return is_owner or is_staff or is_bot or bool(role_ids & set(exempt))


def pick_action(cfg: HoneypotConfig, strikes: int) -> tuple[str, int, EscalationStep | None]:
    """Sanción para la vez número ``strikes``: el escalón más alto alcanzado, o la sanción normal."""
    step = None
    for st in cfg.escalation:  # ordenados de menor a mayor
        if strikes >= st.count:
            step = st
    if step is None:
        return cfg.action, cfg.timeout_minutes, None
    return step.action, step.timeout_minutes, step
