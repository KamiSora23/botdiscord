"""Actividad de voz: estadísticas e historial de sesiones (solo metadatos, nunca audio)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import BigInteger, Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.models import VoiceSession
from nexus_core.db.repo import utcnow

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf

router = APIRouter(prefix="/guilds/{guild_id}/voice", tags=["voice"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])


def _seconds():
    """Duración de cada sesión; las abiertas cuentan hasta ahora."""
    return cast(func.coalesce(VoiceSession.duration_seconds,
                              func.extract("epoch", func.now() - VoiceSession.joined_at)), BigInteger)


@router.get("/stats")
async def voice_stats(days: int = Query(30, ge=0, le=365),
                      access: GuildAccess = Depends(guild_access(1, module="voice_activity")),
                      db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    conds = [VoiceSession.guild_id == access.guild_id]
    if days:
        conds.append(VoiceSession.joined_at >= utcnow() - timedelta(days=days))
    total, sessions, members = (await db.execute(select(
        func.coalesce(func.sum(_seconds()), 0), func.count(), func.count(func.distinct(VoiceSession.user_id)))
        .where(*conds))).one()
    top_users = (await db.execute(select(VoiceSession.user_id, func.max(VoiceSession.user_name),
                                         func.sum(_seconds()), func.count())
                                  .where(*conds).group_by(VoiceSession.user_id)
                                  .order_by(func.sum(_seconds()).desc()).limit(10))).all()
    top_channels = (await db.execute(select(VoiceSession.channel_id, func.max(VoiceSession.channel_name),
                                            func.sum(_seconds()), func.count())
                                     .where(*conds).group_by(VoiceSession.channel_id)
                                     .order_by(func.sum(_seconds()).desc()).limit(10))).all()
    day = cast(VoiceSession.joined_at, Date)
    daily = (await db.execute(select(day, func.sum(_seconds())).where(*conds).group_by(day).order_by(day))).all()
    now_open = await db.scalar(select(func.count()).where(VoiceSession.guild_id == access.guild_id,
                                                          VoiceSession.left_at.is_(None)))
    return {
        "days": days, "total_seconds": int(total), "sessions": sessions, "members": members, "in_voice_now": now_open,
        "top_users": [{"user_id": str(u), "name": n, "seconds": int(s), "sessions": c} for u, n, s, c in top_users],
        "top_channels": [{"channel_id": str(ch), "name": n, "seconds": int(s), "sessions": c}
                         for ch, n, s, c in top_channels],
        "daily": [{"day": d.isoformat(), "seconds": int(s)} for d, s in daily],
    }


@router.get("/sessions")
async def voice_sessions(user_id: str | None = Query(None, pattern=r"^\d{15,21}$"),
                         limit: int = Query(50, ge=1, le=200),
                         access: GuildAccess = Depends(guild_access(1, module="voice_activity")),
                         db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    q = select(VoiceSession).where(VoiceSession.guild_id == access.guild_id)
    if user_id:
        q = q.where(VoiceSession.user_id == int(user_id))
    rows = (await db.scalars(q.order_by(VoiceSession.joined_at.desc()).limit(limit))).all()
    now = utcnow()
    return {"data": [{
        "id": str(r.id), "user_id": str(r.user_id), "user_name": r.user_name, "channel_id": str(r.channel_id),
        "channel_name": r.channel_name, "joined_at": r.joined_at.isoformat(),
        "left_at": r.left_at.isoformat() if r.left_at else None,
        "seconds": r.duration_seconds if r.duration_seconds is not None else int((now - r.joined_at).total_seconds()),
        "open": r.left_at is None,
    } for r in rows]}
