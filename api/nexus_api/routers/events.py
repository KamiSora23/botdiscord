"""Eventos (lista, crear, cancelar) y contadores (crear canales, actualizar). Lo que toca Discord lo hace el bot."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.models import Event, EventRsvp
from nexus_core.db.repo import add_audit, utcnow
from nexus_core.modules.events import EventIn
from nexus_core.sync import guild_channels_key

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.errors import ApiError
from nexus_api.routers.modules import validation_fields
from nexus_api.routers.roles import rpc

router = APIRouter(prefix="/guilds/{guild_id}", tags=["events"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])
write_limit = Depends(rate_limit("write", 30, per="guild"))


@router.get("/events")
async def list_events(when: str = Query("upcoming", pattern="^(upcoming|past)$"),
                      access: GuildAccess = Depends(guild_access(1, module="events")),
                      db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    q = select(Event).where(Event.guild_id == access.guild_id)
    if when == "upcoming":
        q = q.where(Event.status == "scheduled", Event.starts_at > utcnow()).order_by(Event.starts_at)
    else:
        q = q.where((Event.status != "scheduled") | (Event.starts_at <= utcnow())).order_by(Event.starts_at.desc())
    rows = (await db.scalars(q.limit(50))).all()
    counts: dict[int, dict[str, int]] = {}
    if rows:
        for ev_id, status, n in (await db.execute(select(EventRsvp.event_id, EventRsvp.status, func.count())
                                                  .where(EventRsvp.event_id.in_([r.id for r in rows]))
                                                  .group_by(EventRsvp.event_id, EventRsvp.status))).all():
            counts.setdefault(ev_id, {})[status] = n
    return {"data": [{
        "id": str(e.id), "title": e.title, "description": e.description, "starts_at": e.starts_at.isoformat(),
        "channel_id": str(e.channel_id), "max_slots": e.max_slots, "status": e.status, "image_url": e.image_url,
        "going": counts.get(e.id, {}).get("going", 0), "maybe": counts.get(e.id, {}).get("maybe", 0),
        "no": counts.get(e.id, {}).get("no", 0),
        "url": f"https://discord.com/channels/{e.guild_id}/{e.channel_id}/{e.message_id}" if e.message_id else None,
    } for e in rows]}


@router.post("/events", status_code=201, dependencies=[write_limit])
async def create_event(body: dict[str, Any], request: Request,
                       access: GuildAccess = Depends(guild_access(2, module="events")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    try:
        data = EventIn.model_validate(body)
    except ValidationError as exc:
        raise ApiError(400, "validation_error", fields=validation_fields(exc)) from exc
    res = await rpc(request, "events.create", {
        "guild_id": access.guild_id, "title": data.title, "description": data.description,
        "starts_at": data.starts_at.isoformat(), "channel_id": data.channel_id, "max_slots": data.max_slots,
        "image_url": data.image_url, "creator_id": access.auth.user.id})
    await add_audit(db, guild_id=access.guild_id, action="event.create", source="dashboard",
                    actor_id=access.auth.user.id, module="events", changes={"title": {"old": None, "new": data.title}})
    await db.commit()
    return res


@router.post("/events/{event_id}/cancel", dependencies=[write_limit])
async def cancel_event(event_id: int, request: Request, access: GuildAccess = Depends(guild_access(2, module="events")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    res = await rpc(request, "events.cancel", {"guild_id": access.guild_id, "event_id": event_id})
    await add_audit(db, guild_id=access.guild_id, action="event.cancel", source="dashboard",
                    actor_id=access.auth.user.id, module="events")
    await db.commit()
    return res


@router.post("/counters/setup", dependencies=[write_limit])
async def counters_setup(request: Request, access: GuildAccess = Depends(guild_access(3, module="counters")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    res = await rpc(request, "counters.setup", {"guild_id": access.guild_id}, timeout=60)
    await request.app.state.redis.delete(guild_channels_key(access.guild_id))
    await add_audit(db, guild_id=access.guild_id, action="counters.setup", source="dashboard",
                    actor_id=access.auth.user.id, module="counters")
    await db.commit()
    return res


@router.post("/counters/refresh", dependencies=[write_limit])
async def counters_refresh(request: Request, access: GuildAccess = Depends(guild_access(2, module="counters"))) -> dict:
    return await rpc(request, "counters.refresh", {"guild_id": access.guild_id}, timeout=30)
