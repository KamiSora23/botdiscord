"""Fase 6: niveles/XP y economía virtual (puntos sin valor real: sin compras con dinero ni casino)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from nexus_core.messages.template import OptSnowflake, Snowflake

# --- Niveles -------------------------------------------------------------------


def xp_for_next(level: int) -> int:
    """XP necesaria para pasar de ``level`` a ``level + 1`` (curva cuadrática)."""
    return 5 * level * level + 50 * level + 100


def total_xp_for(level: int) -> int:
    return sum(xp_for_next(n) for n in range(level))


def level_from_xp(xp: int) -> tuple[int, int, int]:
    """(nivel, xp dentro del nivel, xp necesaria para el siguiente)."""
    level = 0
    while xp >= xp_for_next(level):
        xp -= xp_for_next(level)
        level += 1
    return level, xp, xp_for_next(level)


class LevelReward(BaseModel):
    level: int = Field(ge=1, le=500)
    role_id: Snowflake


class LevelsConfig(BaseModel):
    xp_min: int = Field(15, ge=1, le=500)
    xp_max: int = Field(25, ge=1, le=500)
    cooldown_seconds: int = Field(60, ge=0, le=3600)
    ignored_channel_ids: list[Snowflake] = Field(default_factory=list, max_length=100)
    ignored_role_ids: list[Snowflake] = Field(default_factory=list, max_length=25)
    announce: Literal["current", "channel", "dm", "none"] = "current"
    announce_channel_id: OptSnowflake = None
    announce_message: str = Field("🎉 {user} subió al **nivel {level}**.", min_length=1, max_length=500)
    rewards: list[LevelReward] = Field(default_factory=list, max_length=50)
    stack_rewards: bool = True
    card_color: int = Field(0x7465F7, ge=0, le=0xFFFFFF)

    @model_validator(mode="after")
    def _check(self) -> "LevelsConfig":
        if self.xp_min > self.xp_max:
            raise ValueError("xp_min_gt_max")
        if self.announce == "channel" and not self.announce_channel_id:
            raise ValueError("channel_required")
        levels = [r.level for r in self.rewards]
        if len(set(levels)) != len(levels):
            raise ValueError("duplicate_level")
        self.rewards = sorted(self.rewards, key=lambda r: r.level)
        return self


def levels_default(locale: str = "es") -> LevelsConfig:
    msg = "🎉 {user} subió al **nivel {level}**." if locale == "es" else "🎉 {user} reached **level {level}**."
    return LevelsConfig(announce_message=msg)


# --- Economía ------------------------------------------------------------------


class EconomyConfig(BaseModel):
    currency_name: str = Field("monedas", min_length=1, max_length=30)
    currency_emoji: str = Field("🪙", min_length=1, max_length=64)
    start_balance: int = Field(0, ge=0, le=1_000_000)
    daily_amount: int = Field(100, ge=0, le=1_000_000)
    work_min: int = Field(20, ge=0, le=1_000_000)
    work_max: int = Field(80, ge=0, le=1_000_000)
    work_cooldown_minutes: int = Field(60, ge=1, le=1440)
    weekly_amount: int = Field(500, ge=0, le=10_000_000)
    gambling_enabled: bool = True  # /apostar y /tragamonedas
    max_bet: int = Field(10_000, ge=1, le=1_000_000_000)
    rob_enabled: bool = True  # /robar y /crimen
    message_reward: int = Field(0, ge=0, le=1000)
    message_cooldown_seconds: int = Field(60, ge=10, le=3600)
    transfers_enabled: bool = True
    max_balance: int = Field(1_000_000_000, ge=1000, le=1_000_000_000_000)

    @model_validator(mode="after")
    def _check(self) -> "EconomyConfig":
        if self.work_min > self.work_max:
            raise ValueError("work_min_gt_max")
        return self


def economy_default(locale: str = "es") -> EconomyConfig:
    return EconomyConfig(currency_name="monedas" if locale == "es" else "coins")


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str | None = Field(None, max_length=200)
    price: int = Field(ge=0, le=1_000_000_000)
    stock: int | None = Field(None, ge=0, le=1_000_000)
    role_id: OptSnowflake = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()


class BalanceAdjustIn(BaseModel):
    amount: int = Field(ge=-1_000_000_000, le=1_000_000_000)
    reason: str | None = Field(None, max_length=200)

    @field_validator("amount")
    @classmethod
    def _nonzero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("amount_zero")
        return v
