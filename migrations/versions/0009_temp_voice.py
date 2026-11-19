"""temp voice channels

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-16 13:10:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "temp_voice_channels",
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], name=op.f("fk_temp_voice_channels_guild_id_guilds"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("channel_id", name=op.f("pk_temp_voice_channels")),
    )
    op.create_index("ix_temp_voice_channels_guild_id_owner_id", "temp_voice_channels", ["guild_id", "owner_id"])


def downgrade() -> None:
    op.drop_index("ix_temp_voice_channels_guild_id_owner_id", table_name="temp_voice_channels")
    op.drop_table("temp_voice_channels")
