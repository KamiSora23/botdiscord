"""Esquemas de autoroles y reaction roles (fase 4)."""

from __future__ import annotations

import re
import secrets
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from nexus_core.messages.template import MessageTemplate, OptSnowflake, Snowflake


class AutorolesConfig(BaseModel):
    human_role_ids: list[Snowflake] = Field(default_factory=list, max_length=10)
    bot_role_ids: list[Snowflake] = Field(default_factory=list, max_length=10)
    delay_seconds: int = Field(0, ge=0, le=3600)
    wait_for_screening: bool = True  # esperar a que acepte las reglas (Membership Screening)


def autoroles_default(locale: str = "es") -> AutorolesConfig:
    return AutorolesConfig()


class ReactionRolesConfig(BaseModel):
    """El módulo solo tiene interruptor; los paneles viven en su propia tabla."""

    remove_reaction_after: bool = False


def reaction_roles_default(locale: str = "es") -> ReactionRolesConfig:
    return ReactionRolesConfig()


CUSTOM_EMOJI = re.compile(r"^<a?:\w{2,32}:\d{15,21}>$")


class PanelOption(BaseModel):
    id: str = Field(default_factory=lambda: secrets.token_hex(4), pattern=r"^[a-f0-9]{8}$")
    role_id: Snowflake
    label: str = Field("", max_length=80)
    emoji: str | None = Field(None, max_length=64)
    description: str | None = Field(None, max_length=100)
    style: Literal["primary", "secondary", "success", "danger"] = "secondary"

    @field_validator("emoji")
    @classmethod
    def _emoji(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        v = v.strip()
        if CUSTOM_EMOJI.match(v) or len(v) <= 8:  # emoji Unicode (puede tener varios code points)
            return v
        raise ValueError("invalid_emoji")


class RolePanelIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    channel_id: OptSnowflake = None
    panel_type: Literal["buttons", "select", "reactions"] = "buttons"
    mode: Literal["normal", "unique", "verify", "drop"] = "normal"
    message: MessageTemplate
    max_choices: int | None = Field(None, ge=1, le=25)
    placeholder: str | None = Field(None, max_length=150)
    options: list[PanelOption] = Field(min_length=1, max_length=25)

    @model_validator(mode="after")
    def _check(self) -> "RolePanelIn":
        roles = [o.role_id for o in self.options]
        if len(set(roles)) != len(roles):
            raise ValueError("duplicate_role")
        ids = [o.id for o in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate_option")
        for o in self.options:
            if self.panel_type == "reactions" and not o.emoji:
                raise ValueError("emoji_required")
            if self.panel_type != "reactions" and not (o.label or o.emoji):
                raise ValueError("label_required")
        if self.panel_type == "reactions" and len(self.options) > 20:
            raise ValueError("too_many_reactions")
        return self
