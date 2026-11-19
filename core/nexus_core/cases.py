"""Casos de moderación compartidos por el bot y la API."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.models import ModerationCase
from nexus_core.db.repo import add_daily_stats, utcnow


async def create_case(db: AsyncSession, *, guild_id: int, target_id: int, target_name: str, action: str,
                      moderator_id: int | None, moderator_name: str | None, reason: str | None,
                      duration_seconds: int | None = None, source: str = "manual",
                      expires_in: timedelta | None = None) -> ModerationCase:
    """Crea el caso con el siguiente número del servidor. El bloqueo evita números repetidos."""
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": guild_id})
    number = (await db.scalar(select(func.coalesce(func.max(ModerationCase.case_number), 0))
                              .where(ModerationCase.guild_id == guild_id))) + 1
    expires = None
    if duration_seconds:
        expires = utcnow() + timedelta(seconds=duration_seconds)
    elif expires_in:
        expires = utcnow() + expires_in
    case = ModerationCase(
        guild_id=guild_id, case_number=number, target_id=target_id, target_name=target_name[:100],
        moderator_id=moderator_id, moderator_name=(moderator_name or "")[:100] or None,
        action=action, reason=(reason or "")[:1000] or None, duration_seconds=duration_seconds,
        expires_at=expires, source=source,
    )
    db.add(case)
    await add_daily_stats(db, guild_id, utcnow().date(), {"mod_actions": 1})
    await db.flush()
    return case


async def active_warn_count(db: AsyncSession, guild_id: int, target_id: int) -> int:
    now = utcnow()
    return await db.scalar(
        select(func.count()).select_from(ModerationCase).where(
            ModerationCase.guild_id == guild_id, ModerationCase.target_id == target_id,
            ModerationCase.action == "warn", ModerationCase.active.is_(True),
            (ModerationCase.expires_at.is_(None)) | (ModerationCase.expires_at > now),
        )) or 0


async def deactivate_temporary(db: AsyncSession, guild_id: int, target_id: int, action: str) -> None:
    await db.execute(update(ModerationCase).where(
        ModerationCase.guild_id == guild_id, ModerationCase.target_id == target_id,
        ModerationCase.action == action, ModerationCase.active.is_(True)).values(active=False))


def case_json(c: ModerationCase) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "number": c.case_number,
        "target": {"id": str(c.target_id), "name": c.target_name},
        "moderator": {"id": str(c.moderator_id), "name": c.moderator_name} if c.moderator_id else None,
        "action": c.action,
        "reason": c.reason,
        "duration_seconds": c.duration_seconds,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "active": c.active,
        "source": c.source,
        "created_at": c.created_at.isoformat(),
    }
