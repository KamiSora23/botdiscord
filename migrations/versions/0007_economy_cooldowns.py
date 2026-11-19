"""economy cooldowns: weekly, rob, crime

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-16 12:50:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("last_weekly_at", "last_rob_at", "last_crime_at")


def upgrade() -> None:
    for col in COLUMNS:
        op.add_column("member_wallets", sa.Column(col, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for col in COLUMNS:
        op.drop_column("member_wallets", col)
