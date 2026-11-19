"""Modelos de la V1. Ver docs/NEXUS_DATABASE_SPEC.md §2."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

TZ = DateTime(timezone=True)
DEFAULT_EMBED_COLOR = 0x7465F7


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _now() -> Any:
    return mapped_column(TZ, nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("locale IN ('es','en')", name="locale"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    global_name: Mapped[str | None] = mapped_column(Text)
    avatar: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, nullable=False, server_default="es")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
    last_login_at: Mapped[datetime | None] = mapped_column(TZ)


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    access_token_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_token_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    updated_at: Mapped[datetime] = _now()


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_at: Mapped[datetime] = _now()
    last_seen_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(TZ, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TZ)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)


class Guild(Base):
    __tablename__ = "guilds"
    __table_args__ = (
        Index(
            "ix_guilds_bot_left_at",
            "bot_left_at",
            postgresql_where=text("bot_present = false"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bot_present: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    bot_joined_at: Mapped[datetime | None] = mapped_column(TZ)
    bot_left_at: Mapped[datetime | None] = mapped_column(TZ)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class GuildConfig(Base):
    __tablename__ = "guild_configs"
    __table_args__ = (CheckConstraint("locale IN ('es','en')", name="locale"),)

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(Text, nullable=False, server_default="es")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    embed_color: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=str(DEFAULT_EMBED_COLOR)
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[datetime] = _now()
    updated_by: Mapped[int | None] = mapped_column(BigInteger)


class ModuleConfig(Base):
    __tablename__ = "module_configs"
    __table_args__ = (CheckConstraint("module ~ '^[a-z][a-z_]{1,31}$'", name="module_name"),)

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    module: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[datetime] = _now()
    updated_by: Mapped[int | None] = mapped_column(BigInteger)


class DashboardRolePermission(Base):
    __tablename__ = "dashboard_role_permissions"
    __table_args__ = (CheckConstraint("level BETWEEN 1 AND 3", name="level"),)

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    module: Mapped[str] = mapped_column(Text, primary_key=True)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class GuildAuditLog(Base):
    __tablename__ = "guild_audit_logs"
    __table_args__ = (
        Index("ix_guild_audit_logs_guild_id_created_at", "guild_id", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()


class GuildDailyStats(Base):
    __tablename__ = "guild_daily_stats"

    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    members_joined: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    members_left: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    commands_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    welcome_sent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    mod_actions: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ModerationCase(Base):
    """Fase 3: warn, timeout, kick, ban… en una sola tabla (docs/NEXUS_DATABASE_SPEC.md §4)."""

    __tablename__ = "moderation_cases"
    __table_args__ = (
        CheckConstraint("action IN ('warn','timeout','untimeout','kick','ban','unban','softban','note')",
                        name="action"),
        CheckConstraint("source IN ('manual','dashboard','automod','ai','system')", name="source"),
        UniqueConstraint("guild_id", "case_number", name="uq_moderation_cases_guild_id_case_number"),
        Index("ix_moderation_cases_guild_id_target_id", "guild_id", "target_id"),
        Index("ix_moderation_cases_guild_id_created_at", "guild_id", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    case_number: Mapped[int] = mapped_column(Integer, nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_name: Mapped[str] = mapped_column(Text, nullable=False)
    moderator_id: Mapped[int | None] = mapped_column(BigInteger)
    moderator_name: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(TZ)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")
    created_at: Mapped[datetime] = _now()


class AutomodRule(Base):
    __tablename__ = "automod_rules"
    __table_args__ = (
        CheckConstraint("rule_type IN ('spam','duplicates','bad_words','links','invites','mass_mentions','caps')",
                        name="rule_type"),
        Index("ix_automod_rules_guild_id", "guild_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    exempt_role_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, server_default="{}")
    exempt_channel_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, server_default="{}")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    test_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class AutomodEvent(Base):
    __tablename__ = "automod_events"
    __table_args__ = (Index("ix_automod_events_guild_id_created_at", "guild_id", text("created_at DESC")),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    rule_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("automod_rules.id", ondelete="SET NULL"))
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    test_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    excerpt: Mapped[str | None] = mapped_column(Text)  # máx. 200 caracteres; retención 30 días
    created_at: Mapped[datetime] = _now()


class RolePanel(Base):
    """Fase 4: panel de Reaction Roles (botones, menú desplegable o reacciones)."""

    __tablename__ = "role_panels"
    __table_args__ = (
        CheckConstraint("panel_type IN ('buttons','select','reactions')", name="panel_type"),
        CheckConstraint("mode IN ('normal','unique','verify','drop')", name="mode"),
        Index("ix_role_panels_guild_id", "guild_id"),
        Index("ix_role_panels_message_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    panel_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="buttons")
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="normal")
    message: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    max_choices: Mapped[int | None] = mapped_column(SmallInteger)
    placeholder: Mapped[str | None] = mapped_column(Text)
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    published_at: Mapped[datetime | None] = mapped_column(TZ)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class MemberNote(Base):
    __tablename__ = "member_notes"
    __table_args__ = (Index("ix_member_notes_guild_id_user_id", "guild_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_name: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()


class Ticket(Base):
    """Fase 5: tickets de soporte (la transcripción se envía como archivo, no se guarda)."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("status IN ('open','closed')", name="status"),
        UniqueConstraint("guild_id", "number", name="uq_tickets_guild_id_number"),
        Index("ix_tickets_channel_id", "channel_id"),
        Index("ix_tickets_guild_id_status", "guild_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    panel_id: Mapped[str] = mapped_column(Text, nullable=False)
    creator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_name: Mapped[str] = mapped_column(Text, nullable=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    claimed_by: Mapped[int | None] = mapped_column(BigInteger)
    subject: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime] = _now()
    last_activity_at: Mapped[datetime] = _now()
    closed_at: Mapped[datetime | None] = mapped_column(TZ)
    closed_by: Mapped[int | None] = mapped_column(BigInteger)
    close_reason: Mapped[str | None] = mapped_column(Text)


class Suggestion(Base):
    __tablename__ = "suggestions"
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','denied','in_progress','implemented')", name="status"),
        UniqueConstraint("guild_id", "number", name="uq_suggestions_guild_id_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    author_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_name: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    upvotes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    downvotes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    staff_response: Mapped[str | None] = mapped_column(Text)
    responded_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class SuggestionVote(Base):
    __tablename__ = "suggestion_votes"
    __table_args__ = (CheckConstraint("vote IN (-1, 1)", name="vote"),)

    suggestion_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("suggestions.id", ondelete="CASCADE"),
                                               primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vote: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class Giveaway(Base):
    __tablename__ = "giveaways"
    __table_args__ = (Index("ix_giveaways_guild_id", "guild_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    prize: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    winner_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    required_role_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, server_default="{}")
    host_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    ended: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    winner_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, server_default="{}")
    seed: Mapped[str | None] = mapped_column(Text)  # semilla usada: el sorteo se puede verificar
    created_at: Mapped[datetime] = _now()


class GiveawayEntry(Base):
    __tablename__ = "giveaway_entries"

    giveaway_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("giveaways.id", ondelete="CASCADE"),
                                             primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = _now()


class StarboardEntry(Base):
    __tablename__ = "starboard_entries"

    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True)
    source_message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    starboard_message_id: Mapped[int | None] = mapped_column(BigInteger)
    star_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = _now()


class CustomCommand(Base):
    __tablename__ = "custom_commands"
    __table_args__ = (UniqueConstraint("guild_id", "name", name="uq_custom_commands_guild_id_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    ephemeral: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    add_role_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, server_default="{}")
    remove_role_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, server_default="{}")
    allowed_role_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, server_default="{}")
    uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class ScheduledMessage(Base):
    __tablename__ = "scheduled_messages"
    __table_args__ = (
        CheckConstraint("repeat IN ('none','daily','weekly','monthly')", name="repeat"),
        CheckConstraint("status IN ('scheduled','paused','sent','failed')", name="status"),
        Index("ix_scheduled_messages_guild_id", "guild_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    next_run_at: Mapped[datetime | None] = mapped_column(TZ)
    local_time: Mapped[str] = mapped_column(Text, nullable=False)  # "2026-11-20T09:00" en ``timezone``
    timezone: Mapped[str | None] = mapped_column(Text)  # zona de quien lo programó; None = la del servidor
    repeat: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="scheduled")
    last_sent_at: Mapped[datetime | None] = mapped_column(TZ)
    last_error: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = _now()


class MemberXP(Base):
    """Fase 6: experiencia por miembro."""

    __tablename__ = "member_xp"
    __table_args__ = (Index("ix_member_xp_guild_id_xp", "guild_id", text("xp DESC")),)

    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    avatar: Mapped[str | None] = mapped_column(Text)
    xp: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_xp_at: Mapped[datetime | None] = mapped_column(TZ)


class MemberWallet(Base):
    __tablename__ = "member_wallets"
    __table_args__ = (CheckConstraint("balance >= 0", name="balance"), Index("ix_member_wallets_guild_id_balance",
                                                                               "guild_id", text("balance DESC")))

    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    last_daily_at: Mapped[datetime | None] = mapped_column(TZ)
    last_work_at: Mapped[datetime | None] = mapped_column(TZ)
    last_weekly_at: Mapped[datetime | None] = mapped_column(TZ)
    last_rob_at: Mapped[datetime | None] = mapped_column(TZ)
    last_crime_at: Mapped[datetime | None] = mapped_column(TZ)
    last_message_reward_at: Mapped[datetime | None] = mapped_column(TZ)


class EconomyTransaction(Base):
    """Registro inmutable de movimientos de la moneda virtual."""

    __tablename__ = "economy_transactions"
    __table_args__ = (Index("ix_economy_transactions_guild_id_created_at", "guild_id", text("created_at DESC")),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # daily, work, transfer_in, transfer_out, buy, admin, message
    reference: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class EconomyItem(Base):
    __tablename__ = "economy_items"
    __table_args__ = (Index("ix_economy_items_guild_id", "guild_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stock: Mapped[int | None] = mapped_column(Integer)  # None = ilimitado
    role_id: Mapped[int | None] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _now()


class EconomyInventory(Base):
    __tablename__ = "economy_inventory"

    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("economy_items.id", ondelete="CASCADE"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class Integration(Base):
    """Fase 7: avisos de YouTube, Twitch, RSS y GitHub (se consultan por sondeo, sin URL pública)."""

    __tablename__ = "integrations"
    __table_args__ = (
        CheckConstraint("provider IN ('youtube','twitch','rss','github')", name="provider"),
        Index("ix_integrations_guild_id", "guild_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)  # canal UC…, login, URL o owner/repo
    display_name: Mapped[str | None] = mapped_column(Text)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    initialized: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")  # ok, error, pending
    last_error: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(TZ)
    last_event_at: Mapped[datetime | None] = mapped_column(TZ)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = _now()


class IntegrationDelivery(Base):
    """Eventos ya avisados (evita avisos repetidos). Retención: 30 días."""

    __tablename__ = "integration_deliveries"
    __table_args__ = (UniqueConstraint("integration_id", "external_event_id",
                                       name="uq_integration_deliveries_integration_id_external_event_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    integration_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("integrations.id", ondelete="CASCADE"),
                                                nullable=False)
    external_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="sent")
    created_at: Mapped[datetime] = _now()


class AIModerationEvent(Base):
    """Resultado de un análisis de IA. No se guarda el texto del mensaje (solo categoría y enlace)."""

    __tablename__ = "ai_moderation_events"
    __table_args__ = (
        CheckConstraint("review_status IN ('none','pending','confirmed','dismissed')", name="review_status"),
        Index("ix_ai_moderation_events_guild_id_created_at", "guild_id", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    category: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)  # explicación corta del modelo, sin citar el mensaje
    action: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = _now()


class AIUsage(Base):
    __tablename__ = "ai_usage"

    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True)
    month: Mapped[str] = mapped_column(Text, primary_key=True)  # "2026-11"
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','done','failed','cancelled')", name="status"
        ),
        Index("ix_scheduled_jobs_due", "run_at", postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("guilds.id", ondelete="CASCADE")
    )
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    run_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="5")
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(TZ)
    last_error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = _now()
    completed_at: Mapped[datetime | None] = mapped_column(TZ)


class MemberQuarantine(Base):
    """Anti-raid: roles que tenía un miembro antes de la cuarentena (para devolvérselos con /liberar)."""

    __tablename__ = "member_quarantine"

    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    reason: Mapped[str | None] = mapped_column(Text)
    moderator_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = _now()


class TempVoiceChannel(Base):
    """Salas de voz temporales vivas (para borrarlas aunque el bot se reinicie)."""

    __tablename__ = "temp_voice_channels"
    __table_args__ = (Index("ix_temp_voice_channels_guild_id_owner_id", "guild_id", "owner_id"),)

    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = _now()


class VoiceSession(Base):
    """Una estancia de un miembro en un canal de voz (sin audio: solo quién, dónde y cuánto)."""

    __tablename__ = "voice_sessions"
    __table_args__ = (
        Index("ix_voice_sessions_guild_id_user_id", "guild_id", "user_id"),
        Index("ix_voice_sessions_guild_id_joined_at", "guild_id", text("joined_at DESC")),
        Index("ix_voice_sessions_open", "guild_id", "user_id", postgresql_where=text("left_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    joined_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(TZ)
    last_seen_at: Mapped[datetime] = mapped_column(TZ, nullable=False)  # para cerrar bien si el bot se apaga
    duration_seconds: Mapped[int | None] = mapped_column(Integer)


class Event(Base):
    """Evento con inscripción (tarjeta con botones en un canal)."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("status IN ('scheduled','started','cancelled')", name="status"),
        Index("ix_events_guild_id_starts_at", "guild_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    starts_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    max_slots: Mapped[int | None] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="scheduled")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = _now()


class EventRsvp(Base):
    __tablename__ = "event_rsvps"
    __table_args__ = (CheckConstraint("status IN ('going','maybe','no')", name="status"),)

    event_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = _now()


class HoneypotStrike(Base):
    """Cada vez que una cuenta escribió en el canal trampa (para sancionar más fuerte a quien reincide)."""

    __tablename__ = "honeypot_strikes"
    __table_args__ = (Index("ix_honeypot_strikes_guild_id_user_id", "guild_id", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()


class Media(Base):
    """Imagen subida para usar en embeds (ver nexus_core.media)."""

    __tablename__ = "media"
    __table_args__ = (Index("ix_media_guild_id", "guild_id", "created_at"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # 32 hex
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)  # nombre original (solo para mostrar)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = _now()

