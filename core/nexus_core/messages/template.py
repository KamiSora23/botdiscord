"""MessageTemplate: formato común de mensajes (docs/NEXUS_DATABASE_SPEC.md §3.1)."""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer, field_validator, model_validator

# --- Snowflake ---------------------------------------------------------------


def _to_snowflake(v: Any) -> int | None:
    if v is None or v == "":
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if not s.isdigit() or not 15 <= len(s) <= 21:
        raise ValueError("invalid_id")
    return int(s)


Snowflake = Annotated[int, BeforeValidator(_to_snowflake), PlainSerializer(lambda v: str(v), return_type=str)]
OptSnowflake = Annotated[
    int | None, BeforeValidator(_to_snowflake), PlainSerializer(lambda v: None if v is None else str(v), return_type=str | None)
]

# --- Límites de Discord --------------------------------------------------------

CONTENT_MAX = 2000
TITLE_MAX = 256
DESCRIPTION_MAX = 4096
FIELDS_MAX = 25
FIELD_NAME_MAX = 256
FIELD_VALUE_MAX = 1024
FOOTER_MAX = 2048
AUTHOR_MAX = 256
EMBED_TOTAL_MAX = 6000
EMBEDS_MAX = 1  # V1 (Discord permite 10)

_URL_OR_VAR = re.compile(r"^(https://\S+|media://[0-9a-f]{32}|\{[a-z_.]+\})$")


def _check_url(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    v = v.strip()
    if not _URL_OR_VAR.match(v):
        raise ValueError("invalid_url")
    return v


class EmbedAuthor(BaseModel):
    name: str | None = Field(None, max_length=AUTHOR_MAX)
    icon_url: str | None = None
    url: str | None = None

    @field_validator("icon_url", "url")
    @classmethod
    def _urls(cls, v: str | None) -> str | None:
        return _check_url(v)


class EmbedFooter(BaseModel):
    text: str | None = Field(None, max_length=FOOTER_MAX)
    icon_url: str | None = None

    @field_validator("icon_url")
    @classmethod
    def _urls(cls, v: str | None) -> str | None:
        return _check_url(v)


class EmbedField(BaseModel):
    name: str = Field(min_length=1, max_length=FIELD_NAME_MAX)
    value: str = Field(min_length=1, max_length=FIELD_VALUE_MAX)
    inline: bool = False


class Embed(BaseModel):
    title: str | None = Field(None, max_length=TITLE_MAX)
    description: str | None = Field(None, max_length=DESCRIPTION_MAX)
    url: str | None = None
    color: int | None = Field(None, ge=0, le=0xFFFFFF)
    author: EmbedAuthor = Field(default_factory=EmbedAuthor)
    thumbnail_url: str | None = None
    image_url: str | None = None
    footer: EmbedFooter = Field(default_factory=EmbedFooter)
    timestamp: bool = False
    fields: list[EmbedField] = Field(default_factory=list, max_length=FIELDS_MAX)

    @field_validator("url", "thumbnail_url", "image_url")
    @classmethod
    def _urls(cls, v: str | None) -> str | None:
        return _check_url(v)

    def total_chars(self) -> int:
        return sum(len(x or "") for x in (self.title, self.description, self.author.name, self.footer.text)) + sum(
            len(f.name) + len(f.value) for f in self.fields
        )

    def has_content(self) -> bool:
        return bool(
            self.title or self.description or self.fields or self.image_url or self.thumbnail_url
            or self.author.name or self.footer.text
        )


class MessageTemplate(BaseModel):
    content: str | None = Field(None, max_length=CONTENT_MAX)
    embeds: list[Embed] = Field(default_factory=list, max_length=EMBEDS_MAX)

    @model_validator(mode="after")
    def _not_empty(self) -> "MessageTemplate":
        if not (self.content and self.content.strip()) and not any(e.has_content() for e in self.embeds):
            raise ValueError("message_empty")
        if sum(e.total_chars() for e in self.embeds) > EMBED_TOTAL_MAX:
            raise ValueError("embed_too_long")
        return self
