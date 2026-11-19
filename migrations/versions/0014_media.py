"""media (imágenes subidas para embeds)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-18 19:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], name=op.f("fk_media_guild_id_guilds"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
    )
    op.create_index("ix_media_guild_id", "media", ["guild_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_media_guild_id", table_name="media")
    op.drop_table("media")
