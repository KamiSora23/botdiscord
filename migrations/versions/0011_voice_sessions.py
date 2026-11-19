"""voice activity sessions

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-16 17:30:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_name", sa.Text(), server_default="", nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_name", sa.Text(), server_default="", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], name=op.f("fk_voice_sessions_guild_id_guilds"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_voice_sessions")),
    )
    op.create_index("ix_voice_sessions_guild_id_user_id", "voice_sessions", ["guild_id", "user_id"])
    op.create_index("ix_voice_sessions_guild_id_joined_at", "voice_sessions", ["guild_id", sa.text("joined_at DESC")])
    op.create_index("ix_voice_sessions_open", "voice_sessions", ["guild_id", "user_id"],
                    postgresql_where=sa.text("left_at IS NULL"))


def downgrade() -> None:
    op.drop_index("ix_voice_sessions_open", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_guild_id_joined_at", table_name="voice_sessions")
    op.drop_index("ix_voice_sessions_guild_id_user_id", table_name="voice_sessions")
    op.drop_table("voice_sessions")
