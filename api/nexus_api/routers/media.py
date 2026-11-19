"""Imágenes subidas para usar en embeds (ver nexus_core.media)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core import media as M
from nexus_core.db.models import Media
from nexus_core.db.repo import add_audit

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.errors import ApiError

router = APIRouter(prefix="/guilds/{guild_id}/media", tags=["media"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])
upload_limit = Depends(rate_limit("media_upload", 20, per="guild"))


def _json(m: Any, used_in: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {"id": m.id, "url": f"media://{m.id}", "filename": m.filename, "content_type": m.content_type,
            "size": m.size, "created_at": m.created_at.isoformat(), "used_in": used_in or []}


async def _usage(db: AsyncSession, guild_id: int) -> tuple[int, int]:
    count, total = (await db.execute(select(func.count(), func.coalesce(func.sum(Media.size), 0))
                                     .where(Media.guild_id == guild_id))).one()
    return int(count), int(total)


@router.get("")
async def list_media(access: GuildAccess = Depends(guild_access(1, module=M.IMAGE_MODULES)),
                     db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    rows = (await db.execute(select(Media.id, Media.filename, Media.content_type, Media.size, Media.created_at)
                             .where(Media.guild_id == access.guild_id)
                             .order_by(Media.created_at.desc()))).all()
    count, total = await _usage(db, access.guild_id)
    used = await M.usage(db, access.guild_id)
    return {"items": [_json(r, used.get(r.id)) for r in rows],
            "usage": {"count": count, "bytes": total, "max_count": M.MAX_COUNT, "max_bytes": M.MAX_TOTAL,
                      "max_file": M.MAX_SIZE, "unused_ttl_days": M.UNUSED_TTL_DAYS},
            "can_edit": access.level >= 2}


@router.post("/cleanup")
async def cleanup_media(access: GuildAccess = Depends(guild_access(2, module=M.IMAGE_MODULES)),
                        db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Borra ya todas las imágenes que no usa ninguna configuración (las ya enviadas siguen en Discord)."""
    n = await M.cleanup_unused(db, access.guild_id, older_than_days=None)
    if n:
        await add_audit(db, guild_id=access.guild_id, action="media.cleanup", source="dashboard",
                        actor_id=access.auth.user.id, module="embeds", changes={"deleted": {"old": None, "new": n}})
    await db.commit()
    return {"deleted": n}


@router.post("", status_code=201, dependencies=[upload_limit])
async def upload_media(file: UploadFile, access: GuildAccess = Depends(guild_access(2, module=M.IMAGE_MODULES)),
                       db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    data = await file.read(M.MAX_SIZE + 1)
    try:
        row = await M.store(db, access.guild_id, file.filename or "", data, access.auth.user.id)
    except M.MediaError as exc:
        if exc.code == "media_quota":
            raise ApiError(409, "media_quota") from exc
        raise ApiError(413 if exc.code == "file_too_large" else 400, "validation_error",
                       fields={"file": exc.code}) from exc
    name = row.filename
    await add_audit(db, guild_id=access.guild_id, action="media.uploaded", source="dashboard",
                    actor_id=access.auth.user.id, module="embeds", changes={"filename": {"old": None, "new": name}})
    await db.commit()
    await db.refresh(row)
    return _json(row)


@router.get("/{media_id}")
async def view_media(media_id: str, access: GuildAccess = Depends(guild_access(1, module=M.IMAGE_MODULES)),
                     db: AsyncSession = Depends(get_db)) -> Response:
    row = (await db.execute(select(Media.content_type, Media.data)
                            .where(Media.guild_id == access.guild_id, Media.id == media_id))).first()
    if row is None:
        raise ApiError(404, "not_found")
    return Response(row.data, media_type=row.content_type,
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff",
                             "Content-Security-Policy": "default-src 'none'"})


@router.delete("/{media_id}", status_code=204)
async def delete_media(media_id: str, access: GuildAccess = Depends(guild_access(2, module=M.IMAGE_MODULES)),
                       db: AsyncSession = Depends(get_db)) -> Response:
    res = await db.execute(delete(Media).where(Media.guild_id == access.guild_id, Media.id == media_id))
    if not res.rowcount:
        raise ApiError(404, "not_found")
    await add_audit(db, guild_id=access.guild_id, action="media.deleted", source="dashboard",
                    actor_id=access.auth.user.id, module="embeds")
    await db.commit()
    return Response(status_code=204)
