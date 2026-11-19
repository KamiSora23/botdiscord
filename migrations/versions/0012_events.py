"""events with RSVP

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-16 18:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("max_slots", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="scheduled", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('scheduled','started','cancelled')", name=op.f("ck_events_status")),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], name=op.f("fk_events_guild_id_guilds"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index("ix_events_guild_id_starts_at", "events", ["guild_id", "starts_at"])
    op.create_table(
        "event_rsvps",
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_name", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('going','maybe','no')", name=op.f("ck_event_rsvps_status")),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], name=op.f("fk_event_rsvps_event_id_events"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id", "user_id", name=op.f("pk_event_rsvps")),
    )


def downgrade() -> None:
    op.drop_table("event_rsvps")
    op.drop_index("ix_events_guild_id_starts_at", table_name="events")
    op.drop_table("events")
