"""honeypot strikes (escalation)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-18 17:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "honeypot_strikes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], name=op.f("fk_honeypot_strikes_guild_id_guilds"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_honeypot_strikes")),
    )
    op.create_index("ix_honeypot_strikes_guild_id_user_id", "honeypot_strikes", ["guild_id", "user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_honeypot_strikes_guild_id_user_id", table_name="honeypot_strikes")
    op.drop_table("honeypot_strikes")
