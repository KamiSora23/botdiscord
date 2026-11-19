"""Esquema del módulo welcome (docs/NEXUS_DATABASE_SPEC.md §3.3)."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from nexus_core.messages.template import Embed, EmbedFooter, MessageTemplate, OptSnowflake


class WelcomeDM(BaseModel):
    enabled: bool = False
    message: MessageTemplate | None = None

    @model_validator(mode="after")
    def _msg(self) -> "WelcomeDM":
        if self.enabled and self.message is None:
            raise ValueError("message_required")
        return self


class WelcomeJoin(BaseModel):
    enabled: bool = True
    channel_id: OptSnowflake = None
    ignore_bots: bool = True
    message: MessageTemplate
    dm: WelcomeDM = Field(default_factory=WelcomeDM)
    delete_after_seconds: int | None = Field(None, ge=5, le=86400)

    @model_validator(mode="after")
    def _channel(self) -> "WelcomeJoin":
        if self.enabled and self.channel_id is None:
            raise ValueError("channel_required")
        return self


class WelcomeLeave(BaseModel):
    enabled: bool = False
    channel_id: OptSnowflake = None
    ignore_bots: bool = True
    message: MessageTemplate

    @model_validator(mode="after")
    def _channel(self) -> "WelcomeLeave":
        if self.enabled and self.channel_id is None:
            raise ValueError("channel_required")
        return self


class WelcomeConfig(BaseModel):
    join: WelcomeJoin
    leave: WelcomeLeave


_TEXTS = {
    "es": {
        "join_title": "¡Bienvenido a {server}!",
        "join_desc": "¡Hola {user}! Nos alegra tenerte aquí.\nYa somos **{member_count}** miembros.",
        "dm": "¡Hola {user.display_name}! Gracias por unirte a **{server}**.",
        "leave": "**{user.name}** salió del servidor. Ahora somos {member_count}.",
    },
    "en": {
        "join_title": "Welcome to {server}!",
        "join_desc": "Hi {user}! We're glad to have you here.\nWe are now **{member_count}** members.",
        "dm": "Hi {user.display_name}! Thanks for joining **{server}**.",
        "leave": "**{user.name}** left the server. We are now {member_count}.",
    },
}


def default_config(locale: str = "es") -> WelcomeConfig:
    tx = _TEXTS.get(locale, _TEXTS["en"])
    return WelcomeConfig(
        join=WelcomeJoin(
            enabled=False,
            message=MessageTemplate(embeds=[Embed(
                title=tx["join_title"], description=tx["join_desc"], thumbnail_url="{user.avatar}",
                footer=EmbedFooter(text="NEXUS BOT"), timestamp=True,
            )]),
            dm=WelcomeDM(enabled=False, message=MessageTemplate(content=tx["dm"])),
        ),
        leave=WelcomeLeave(enabled=False, message=MessageTemplate(content=tx["leave"])),
    )
