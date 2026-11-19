"""Respuestas automáticas: etiquetas (/tag), respuestas por palabras clave y mensajes fijos al final de un canal."""

from __future__ import annotations

import re
import secrets
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from nexus_core.messages.template import Snowflake

TAG_NAME = re.compile(r"^[a-z0-9áéíóúñü_-]{1,32}$")


def _id() -> str:
    return secrets.token_hex(4)


class Tag(BaseModel):
    name: str
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip().lower().replace(" ", "-")
        if not TAG_NAME.match(v):
            raise ValueError("invalid_tag_name")
        return v


class Trigger(BaseModel):
    id: str = Field(default_factory=_id, pattern=r"^[a-f0-9]{8}$")
    keywords: list[str] = Field(min_length=1, max_length=10)
    match: Literal["contains", "word", "exact", "starts"] = "word"
    response: str = Field(min_length=1, max_length=2000)
    channel_ids: list[Snowflake] = Field(default_factory=list, max_length=25)  # vacío = todos
    reply: bool = True  # responder citando el mensaje
    cooldown_seconds: int = Field(30, ge=0, le=3600)

    @field_validator("keywords")
    @classmethod
    def _kw(cls, v: list[str]) -> list[str]:
        out = [k.strip()[:100] for k in v if k and k.strip()]
        if not out:
            raise ValueError("keywords_required")
        return out


class Sticky(BaseModel):
    channel_id: Snowflake
    content: str = Field(min_length=1, max_length=2000)


class ResponsesConfig(BaseModel):
    tags: list[Tag] = Field(default_factory=list, max_length=100)
    triggers: list[Trigger] = Field(default_factory=list, max_length=50)
    stickies: list[Sticky] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _unique(self) -> "ResponsesConfig":
        names = [t.name for t in self.tags]
        if len(names) != len(set(names)):
            raise ValueError("duplicate_tag")
        chans = [s.channel_id for s in self.stickies]
        if len(chans) != len(set(chans)):
            raise ValueError("duplicate_sticky")
        return self


def responses_default(locale: str = "es") -> ResponsesConfig:
    return ResponsesConfig()


def _norm(text: str) -> str:
    """Minúsculas y sin tildes, para que «cómo» y «como» coincidan."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def matches(trigger: Trigger, content: str) -> bool:
    msg = _norm(content).strip()
    for kw in trigger.keywords:
        k = _norm(kw).strip()
        if not k:
            continue
        if trigger.match == "exact" and msg == k:
            return True
        if trigger.match == "starts" and msg.startswith(k):
            return True
        if trigger.match == "contains" and k in msg:
            return True
        if trigger.match == "word" and re.search(rf"(?<!\w){re.escape(k)}(?!\w)", msg):
            return True
    return False
