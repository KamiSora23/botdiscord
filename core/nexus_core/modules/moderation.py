"""Esquemas de moderation, automod y logging (fase 3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from nexus_core.messages.template import OptSnowflake, Snowflake

# --- Moderación --------------------------------------------------------------


class EscalationStep(BaseModel):
    warns: int = Field(ge=1, le=50)
    action: Literal["timeout", "kick", "ban"]
    duration_seconds: int | None = Field(None, ge=60, le=2419200)  # timeout máx. 28 días

    @model_validator(mode="after")
    def _duration(self) -> "EscalationStep":
        if self.action == "timeout" and not self.duration_seconds:
            raise ValueError("duration_required")
        return self


class ModerationConfig(BaseModel):
    log_channel_id: OptSnowflake = None
    dm_on_action: bool = True
    require_reason: bool = False
    default_reasons: list[str] = Field(default_factory=list, max_length=25)
    warn_expiry_days: int | None = Field(None, ge=1, le=365)
    escalation: list[EscalationStep] = Field(default_factory=list, max_length=10)
    ban_delete_message_days: int = Field(0, ge=0, le=7)

    @field_validator("default_reasons")
    @classmethod
    def _reasons(cls, v: list[str]) -> list[str]:
        return [r.strip()[:200] for r in v if r.strip()]

    @field_validator("escalation")
    @classmethod
    def _sorted(cls, v: list[EscalationStep]) -> list[EscalationStep]:
        counts = [s.warns for s in v]
        if len(set(counts)) != len(counts):
            raise ValueError("duplicate_warn_count")
        return sorted(v, key=lambda s: s.warns)


def moderation_default(locale: str = "es") -> ModerationConfig:
    reasons = {
        "es": ["Spam", "Lenguaje ofensivo", "Acoso", "Contenido NSFW", "Publicidad no permitida"],
        "en": ["Spam", "Offensive language", "Harassment", "NSFW content", "Unallowed advertising"],
    }
    return ModerationConfig(
        default_reasons=reasons.get(locale, reasons["en"]),
        escalation=[EscalationStep(warns=3, action="timeout", duration_seconds=3600),
                    EscalationStep(warns=5, action="kick")],
        warn_expiry_days=30,
    )


# --- AutoMod -----------------------------------------------------------------


class AutomodConfig(BaseModel):
    log_channel_id: OptSnowflake = None
    exempt_role_ids: list[Snowflake] = Field(default_factory=list, max_length=50)
    exempt_channel_ids: list[Snowflake] = Field(default_factory=list, max_length=100)


def automod_default(locale: str = "es") -> AutomodConfig:
    return AutomodConfig()


RuleType = Literal["spam", "duplicates", "bad_words", "links", "invites", "mass_mentions", "caps"]
ActionType = Literal["delete", "alert", "warn", "timeout", "kick", "ban"]


class RuleAction(BaseModel):
    type: ActionType
    duration_seconds: int | None = Field(None, ge=60, le=2419200)

    @model_validator(mode="after")
    def _duration(self) -> "RuleAction":
        if self.type == "timeout" and not self.duration_seconds:
            raise ValueError("duration_required")
        return self


class SpamCfg(BaseModel):
    max_messages: int = Field(5, ge=2, le=50)
    per_seconds: int = Field(5, ge=1, le=120)


class DuplicatesCfg(BaseModel):
    max_repeats: int = Field(3, ge=2, le=20)
    per_seconds: int = Field(30, ge=5, le=600)


class BadWordsCfg(BaseModel):
    words: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("words")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return sorted({w.strip().lower()[:60] for w in v if w.strip()})


class LinksCfg(BaseModel):
    mode: Literal["block_all", "allowlist", "blocklist"] = "allowlist"
    domains: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("domains")
    @classmethod
    def _domains(cls, v: list[str]) -> list[str]:
        out = []
        for d in v:
            d = d.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0].removeprefix("www.")
            if d:
                out.append(d)
        return sorted(set(out))


class InvitesCfg(BaseModel):
    allow_own_server: bool = True


class MassMentionsCfg(BaseModel):
    max_mentions: int = Field(5, ge=1, le=50)


class CapsCfg(BaseModel):
    min_length: int = Field(10, ge=3, le=500)
    max_percent: int = Field(70, ge=30, le=100)


RULE_CONFIGS: dict[str, type[BaseModel]] = {
    "spam": SpamCfg, "duplicates": DuplicatesCfg, "bad_words": BadWordsCfg, "links": LinksCfg,
    "invites": InvitesCfg, "mass_mentions": MassMentionsCfg, "caps": CapsCfg,
}


class AutomodRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    enabled: bool = True
    rule_type: RuleType
    config: dict = Field(default_factory=dict)
    actions: list[RuleAction] = Field(min_length=1, max_length=4)
    exempt_role_ids: list[Snowflake] = Field(default_factory=list, max_length=50)
    exempt_channel_ids: list[Snowflake] = Field(default_factory=list, max_length=100)
    priority: int = Field(0, ge=0, le=100)
    test_mode: bool = False

    @model_validator(mode="after")
    def _config(self) -> "AutomodRuleIn":
        self.config = RULE_CONFIGS[self.rule_type].model_validate(self.config).model_dump()
        types = [a.type for a in self.actions]
        if len(set(types)) != len(types):
            raise ValueError("duplicate_action")
        if len({"warn", "timeout", "kick", "ban"} & set(types)) > 1:
            raise ValueError("one_punishment_only")
        return self


# --- Logs --------------------------------------------------------------------

LOG_EVENTS: dict[str, list[str]] = {
    "messages": ["message_delete", "message_edit", "message_bulk_delete"],
    "members": ["member_join", "member_leave", "member_nickname", "member_roles"],
    "roles": ["role_create", "role_delete", "role_update"],
    "channels": ["channel_create", "channel_delete", "channel_update"],
    "moderation": ["mod_case", "automod_action"],
    "voice": ["voice_join", "voice_leave", "voice_move"],
}


class LogCategory(BaseModel):
    channel_id: OptSnowflake = None
    events: dict[str, bool] = Field(default_factory=dict)
    # Canal propio para algún aviso concreto (p. ej. «Salió de voz» en #voz-logs). Si no, el de la categoría.
    event_channels: dict[str, Snowflake] = Field(default_factory=dict)


class LoggingConfig(BaseModel):
    categories: dict[str, LogCategory] = Field(default_factory=dict)
    ignored_channel_ids: list[Snowflake] = Field(default_factory=list, max_length=100)
    ignore_bots: bool = True

    @model_validator(mode="after")
    def _fill(self) -> "LoggingConfig":
        for cat, events in LOG_EVENTS.items():
            c = self.categories.get(cat) or LogCategory()
            c.events = {e: bool(c.events.get(e, True)) for e in events}
            c.event_channels = {e: ch for e, ch in c.event_channels.items() if e in events}
            self.categories[cat] = c
        self.categories = {k: v for k, v in self.categories.items() if k in LOG_EVENTS}
        return self


def logging_default(locale: str = "es") -> LoggingConfig:
    return LoggingConfig()


def channel_for(cfg: LoggingConfig, event: str) -> int | None:
    for cat, events in LOG_EVENTS.items():
        if event in events:
            c = cfg.categories.get(cat)
            if c and c.events.get(event, True):
                return c.event_channels.get(event) or c.channel_id
    return None
