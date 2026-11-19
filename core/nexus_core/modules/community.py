"""Esquemas de la fase 5: tickets, sugerencias, starboard, sorteos, encuestas, comandos y mensajes programados."""

from __future__ import annotations

import re
import secrets
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from nexus_core.messages.template import Embed, MessageTemplate, OptSnowflake, Snowflake

# --- Tickets -------------------------------------------------------------------


class TicketPanel(BaseModel):
    id: str = Field(default_factory=lambda: secrets.token_hex(4), pattern=r"^[a-f0-9]{8}$")
    name: str = Field("Soporte", min_length=1, max_length=60)
    channel_id: OptSnowflake = None
    message_id: OptSnowflake = None
    message: MessageTemplate
    button_label: str = Field("Abrir ticket", min_length=1, max_length=80)
    button_emoji: str | None = Field("🎫", max_length=64)
    category_channel_id: OptSnowflake = None
    support_role_ids: list[Snowflake] = Field(default_factory=list, max_length=10)
    opening_message: str = Field("Hola {user}, el equipo te atenderá pronto. Describe tu problema.", max_length=2000)
    ask_subject: bool = False


class TicketsConfig(BaseModel):
    panels: list[TicketPanel] = Field(default_factory=list, max_length=5)
    transcript_channel_id: OptSnowflake = None
    max_open_per_user: int = Field(1, ge=1, le=5)
    auto_close_hours: int | None = Field(None, ge=1, le=720)
    dm_transcript: bool = False


def tickets_default(locale: str = "es") -> TicketsConfig:
    es = locale == "es"
    return TicketsConfig(panels=[TicketPanel(
        name="Soporte" if es else "Support",
        message=MessageTemplate(embeds=[Embed(
            title="¿Necesitas ayuda?" if es else "Need help?",
            description=("Pulsa el botón para abrir un ticket privado con el equipo." if es
                         else "Press the button to open a private ticket with the team."))]),
        button_label="Abrir ticket" if es else "Open ticket",
        opening_message=("Hola {user}, el equipo te atenderá pronto. Describe tu problema." if es
                         else "Hi {user}, the team will be with you soon. Describe your issue."),
    )])


# --- Sugerencias -----------------------------------------------------------------


class SuggestionsConfig(BaseModel):
    channel_id: OptSnowflake = None
    create_thread: bool = True
    staff_role_ids: list[Snowflake] = Field(default_factory=list, max_length=10)
    anonymous: bool = False


def suggestions_default(locale: str = "es") -> SuggestionsConfig:
    return SuggestionsConfig()


# --- Starboard ---------------------------------------------------------------------


class StarboardConfig(BaseModel):
    channel_id: OptSnowflake = None
    emoji: str = Field("⭐", min_length=1, max_length=64)
    threshold: int = Field(3, ge=1, le=100)
    allow_self_star: bool = False
    include_bots: bool = False
    ignored_channel_ids: list[Snowflake] = Field(default_factory=list, max_length=100)


def starboard_default(locale: str = "es") -> StarboardConfig:
    return StarboardConfig()


class EmptyConfig(BaseModel):
    """Módulos que solo tienen interruptor (sus datos viven en tablas propias)."""


def empty_default(locale: str = "es") -> EmptyConfig:
    return EmptyConfig()


# --- Sorteos y encuestas ----------------------------------------------------------


class GiveawaysConfig(BaseModel):
    manager_role_ids: list[Snowflake] = Field(default_factory=list, max_length=10)
    ping_role_id: OptSnowflake = None


def giveaways_default(locale: str = "es") -> GiveawaysConfig:
    return GiveawaysConfig()


class PollsConfig(BaseModel):
    allow_members: bool = False  # si no, solo quien tenga «Gestionar mensajes» puede crear encuestas


def polls_default(locale: str = "es") -> PollsConfig:
    return PollsConfig()


class GiveawayIn(BaseModel):
    channel_id: Snowflake
    prize: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    winner_count: int = Field(1, ge=1, le=20)
    duration_seconds: int = Field(ge=60, le=60 * 60 * 24 * 60)
    required_role_ids: list[Snowflake] = Field(default_factory=list, max_length=5)


class PollIn(BaseModel):
    channel_id: Snowflake
    question: str = Field(min_length=1, max_length=300)
    answers: list[str] = Field(min_length=2, max_length=10)
    duration_hours: int = Field(24, ge=1, le=768)
    multiple: bool = False

    @field_validator("answers")
    @classmethod
    def _answers(cls, v: list[str]) -> list[str]:
        out = [a.strip()[:55] for a in v if a.strip()]
        if len(out) < 2:
            raise ValueError("two_answers_required")
        return out


# --- Comandos personalizados --------------------------------------------------------

COMMAND_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")
RESERVED = {"ping", "help", "ayuda", "panel", "dashboard", "bienvenida", "welcome", "advertir", "warn", "aislar",
            "timeout", "expulsar", "kick", "banear", "ban", "desbanear", "unban", "historial", "warnings", "caso", "case",
            "limpiar", "purge", "ticket", "sugerir", "suggest", "sugerencia", "suggestion", "encuesta", "poll",
            "sorteo", "giveaway", "nivel", "rank", "ranking", "leaderboard", "economia", "balance", "daily", "tienda",
            "shop", "quitar-aislamiento", "untimeout"}


class CustomCommandIn(BaseModel):
    name: str
    description: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    response: MessageTemplate
    ephemeral: bool = False
    add_role_ids: list[Snowflake] = Field(default_factory=list, max_length=5)
    remove_role_ids: list[Snowflake] = Field(default_factory=list, max_length=5)
    allowed_role_ids: list[Snowflake] = Field(default_factory=list, max_length=10)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip().lower()
        if not COMMAND_NAME.match(v):
            raise ValueError("invalid_command_name")
        if v in RESERVED:
            raise ValueError("reserved_command_name")
        return v


# --- Mensajes programados ----------------------------------------------------------


class ScheduledMessageIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    channel_id: Snowflake
    message: MessageTemplate
    local_time: str  # "YYYY-MM-DDTHH:MM" en ``timezone``
    timezone: str | None = Field(None, max_length=64)  # zona del navegador; None = la del servidor
    repeat: Literal["none", "daily", "weekly", "monthly"] = "none"
    paused: bool = False

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if not v:
            return None
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("invalid_timezone") from exc
        return v

    @field_validator("local_time")
    @classmethod
    def _time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%dT%H:%M")
        except ValueError as exc:
            raise ValueError("invalid_datetime") from exc
        return v

