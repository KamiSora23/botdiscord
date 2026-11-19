"""anti-raid: member quarantine

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-16 13:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member_quarantine",
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_ids", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("moderator_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], name=op.f("fk_member_quarantine_guild_id_guilds"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("guild_id", "user_id", name=op.f("pk_member_quarantine")),
    )


def downgrade() -> None:
    op.drop_table("member_quarantine")
