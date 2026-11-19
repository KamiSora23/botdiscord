"""Cuenta del usuario (docs/NEXUS_API_SPEC.md §6.2)."""

from __future__ import annotations

import uuid
from typing import Literal
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.models import User, UserSession
from nexus_core.db.repo import utcnow

from nexus_api.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    Auth,
    current_auth,
    get_db,
    rate_limit,
    require_csrf,
)
from nexus_api.errors import ApiError
from nexus_api.routers.auth import user_json

router = APIRouter(prefix="/me", tags=["account"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])


def validate_timezone(value: str) -> str:
    if value != "UTC" and value not in available_timezones():
        raise ValueError("invalid_timezone")
    return value


class MePatch(BaseModel):
    locale: Literal["es", "en"] | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        return None if v is None else validate_timezone(v)


class DeleteConfirm(BaseModel):
    confirm: Literal["DELETE"]


@router.patch("")
async def patch_me(body: MePatch, auth: Auth = Depends(current_auth),
                   db: AsyncSession = Depends(get_db)) -> dict:
    user = await db.get(User, auth.user.id)
    assert user is not None
    if body.locale:
        user.locale = body.locale
    if body.timezone:
        user.timezone = body.timezone
    user.updated_at = utcnow()
    await db.commit()
    return user_json(user)


@router.get("/sessions")
async def sessions(auth: Auth = Depends(current_auth), db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.scalars(
        select(UserSession)
        .where(UserSession.user_id == auth.user.id, UserSession.revoked_at.is_(None),
               UserSession.expires_at > utcnow())
        .order_by(UserSession.last_seen_at.desc())
    )).all()
    return {"data": [
        {
            "id": str(s.id),
            "current": s.id == auth.session.id,
            "created_at": s.created_at.isoformat(),
            "last_seen_at": s.last_seen_at.isoformat(),
            "ip": str(s.ip) if s.ip else None,
            "user_agent": s.user_agent,
        }
        for s in rows
    ]}


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(session_id: uuid.UUID, auth: Auth = Depends(current_auth),
                         db: AsyncSession = Depends(get_db)) -> Response:
    sess = await db.get(UserSession, session_id)
    if sess is None or sess.user_id != auth.user.id:
        raise ApiError(404, "not_found")
    sess.revoked_at = utcnow()
    await db.commit()
    return Response(status_code=204)


@router.delete("", status_code=204)
async def delete_me(body: DeleteConfirm, auth: Auth = Depends(current_auth),
                    db: AsyncSession = Depends(get_db)) -> Response:
    await db.execute(delete(User).where(User.id == auth.user.id))
    await db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp
