"""scheduled messages: per-message timezone

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-16 17:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scheduled_messages", sa.Column("timezone", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scheduled_messages", "timezone")
