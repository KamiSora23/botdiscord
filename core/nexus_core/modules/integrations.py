"""Fase 7: integraciones e IA de moderación."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from nexus_core.messages.template import Embed, EmbedFooter, MessageTemplate, OptSnowflake, Snowflake

Provider = Literal["youtube", "twitch", "rss", "github"]


class IntegrationsConfig(BaseModel):
    """Solo interruptor; cada integración vive en la tabla ``integrations``."""


def integrations_default(locale: str = "es") -> IntegrationsConfig:
    return IntegrationsConfig()


DEFAULT_MESSAGES = {
    "youtube": {"es": "📺 **{name}** subió un vídeo nuevo", "en": "📺 **{name}** uploaded a new video"},
    "twitch": {"es": "🔴 **{name}** está en directo", "en": "🔴 **{name}** is live"},
    "rss": {"es": "📰 Nuevo en **{name}**", "en": "📰 New on **{name}**"},
    "github": {"es": "🚀 Nueva versión de **{name}**", "en": "🚀 New release of **{name}**"},
}


def default_message(provider: str, locale: str) -> MessageTemplate:
    text = DEFAULT_MESSAGES[provider].get(locale, DEFAULT_MESSAGES[provider]["en"])
    return MessageTemplate(content=text, embeds=[Embed(title="{title}", url="{url}", image_url="{thumbnail}",
                                                       footer=EmbedFooter(text="{author}"))])


class IntegrationIn(BaseModel):
    provider: Provider
    source: str = Field(min_length=2, max_length=500)  # lo que escribe el usuario (URL, ID, owner/repo, login)
    channel_id: Snowflake
    message: MessageTemplate
    enabled: bool = True


# --- IA de moderación -----------------------------------------------------------

AI_CATEGORIES = ("spam", "scam", "insults", "harassment", "hate", "sexual", "violence", "off_rules")


class AIModerationConfig(BaseModel):
    categories: dict[str, bool] = Field(default_factory=dict)
    rules_text: str = Field("", max_length=2000)  # reglas del servidor que la IA debe tener en cuenta
    action_threshold: float = Field(0.9, ge=0.5, le=1.0)
    review_threshold: float = Field(0.6, ge=0.3, le=1.0)
    action: Literal["alert", "delete", "delete_timeout"] = "delete"
    timeout_seconds: int = Field(600, ge=60, le=2419200)
    alert_channel_id: OptSnowflake = None
    monitored_channel_ids: list[Snowflake] = Field(default_factory=list, max_length=100)  # vacío = todos
    exempt_role_ids: list[Snowflake] = Field(default_factory=list, max_length=25)
    min_length: int = Field(12, ge=1, le=500)
    max_requests_per_minute: int = Field(20, ge=1, le=120)
    monthly_token_limit: int = Field(1_000_000, ge=10_000, le=100_000_000)

    @model_validator(mode="after")
    def _fill(self) -> "AIModerationConfig":
        self.categories = {c: bool(self.categories.get(c, c not in ("off_rules",))) for c in AI_CATEGORIES}
        if self.review_threshold > self.action_threshold:
            raise ValueError("review_gt_action")
        return self


def ai_default(locale: str = "es") -> AIModerationConfig:
    return AIModerationConfig()
