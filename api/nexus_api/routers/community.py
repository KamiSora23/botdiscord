"""Fase 5: tickets, sugerencias, sorteos, encuestas, comandos personalizados y mensajes programados."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.models import (
    CustomCommand,
    Giveaway,
    GuildConfig,
    ScheduledMessage,
    Suggestion,
    Ticket,
)
from nexus_core.db.repo import add_audit, utcnow
from nexus_core.modules.community import CustomCommandIn, GiveawayIn, PollIn, ScheduledMessageIn
from nexus_core.scheduling import next_run, schedule_message_job
from nexus_core.sync import publish

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.errors import ApiError
from nexus_api.routers.modules import validation_fields
from nexus_api.routers.roles import rpc

router = APIRouter(prefix="/guilds/{guild_id}", tags=["community"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])
write_limit = Depends(rate_limit("write", 30, per="guild"))


def _validate(model: type[BaseModel], body: dict[str, Any]) -> Any:
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        raise ApiError(400, "validation_error", fields=validation_fields(exc)) from exc


async def _audit(db: AsyncSession, access: GuildAccess, action: str, module: str, **changes: Any) -> None:
    await add_audit(db, guild_id=access.guild_id, action=action, source="dashboard", actor_id=access.auth.user.id,
                    module=module, changes={k: {"old": None, "new": v} for k, v in changes.items()} or None)


# --- Tickets -----------------------------------------------------------------

@router.get("/tickets")
async def list_tickets(access: GuildAccess = Depends(guild_access(1, module="tickets")),
                       db: AsyncSession = Depends(get_db), status: Literal["open", "closed", "all"] = "open",
                       limit: int = Query(50, ge=1, le=100)) -> dict:
    q = select(Ticket).where(Ticket.guild_id == access.guild_id)
    if status != "all":
        q = q.where(Ticket.status == status)
    rows = (await db.scalars(q.order_by(Ticket.number.desc()).limit(limit))).all()
    open_count = await db.scalar(select(func.count()).select_from(Ticket).where(
        Ticket.guild_id == access.guild_id, Ticket.status == "open"))
    return {"open_count": open_count, "data": [{
        "number": t.number, "panel_id": t.panel_id, "creator": {"id": str(t.creator_id), "name": t.creator_name},
        "channel_id": str(t.channel_id) if t.channel_id else None, "status": t.status, "subject": t.subject,
        "claimed_by": str(t.claimed_by) if t.claimed_by else None, "opened_at": t.opened_at.isoformat(),
        "closed_at": t.closed_at.isoformat() if t.closed_at else None, "close_reason": t.close_reason,
    } for t in rows]}


@router.post("/tickets/panels/{panel_id}/publish", dependencies=[write_limit])
async def publish_ticket_panel(panel_id: str, request: Request,
                               access: GuildAccess = Depends(guild_access(2, module="tickets")),
                               db: AsyncSession = Depends(get_db)) -> dict:
    res = await rpc(request, "tickets.publish", {"guild_id": access.guild_id, "panel_id": panel_id})
    await _audit(db, access, "tickets.publish", "tickets")
    await db.commit()
    return res


class CloseIn(BaseModel):
    reason: str | None = Field(None, max_length=500)


@router.post("/tickets/{number}/close", dependencies=[write_limit])
async def close_ticket(number: int, body: CloseIn, request: Request,
                       access: GuildAccess = Depends(guild_access(2, module="tickets"))) -> dict:
    return await rpc(request, "tickets.close", {"guild_id": access.guild_id, "number": number,
                                                "closer_id": access.auth.user.id, "reason": body.reason})


# --- Sugerencias ----------------------------------------------------------------

@router.get("/suggestions")
async def list_suggestions(access: GuildAccess = Depends(guild_access(1, module="suggestions")),
                           db: AsyncSession = Depends(get_db), status: str | None = None,
                           limit: int = Query(50, ge=1, le=100)) -> dict:
    q = select(Suggestion).where(Suggestion.guild_id == access.guild_id)
    if status:
        q = q.where(Suggestion.status == status)
    rows = (await db.scalars(q.order_by(Suggestion.number.desc()).limit(limit))).all()
    return {"data": [{
        "number": s.number, "author": {"id": str(s.author_id), "name": s.author_name}, "content": s.content,
        "status": s.status, "upvotes": s.upvotes, "downvotes": s.downvotes, "staff_response": s.staff_response,
        "jump_url": f"https://discord.com/channels/{s.guild_id}/{s.channel_id}/{s.message_id}" if s.message_id else None,
        "created_at": s.created_at.isoformat(),
    } for s in rows]}


class RespondIn(BaseModel):
    status: Literal["pending", "approved", "denied", "in_progress", "implemented"]
    response: str | None = Field(None, max_length=1000)


@router.post("/suggestions/{number}/respond", dependencies=[write_limit])
async def respond_suggestion(number: int, body: RespondIn, request: Request,
                             access: GuildAccess = Depends(guild_access(2, module="suggestions"))) -> dict:
    return await rpc(request, "suggestions.respond", {
        "guild_id": access.guild_id, "number": number, "status": body.status, "response": body.response,
        "staff_id": access.auth.user.id})


# --- Sorteos y encuestas ----------------------------------------------------------

def _giveaway_json(g: Giveaway, entries: int) -> dict[str, Any]:
    return {
        "id": str(g.id), "channel_id": str(g.channel_id), "prize": g.prize, "description": g.description,
        "winner_count": g.winner_count, "ends_at": g.ends_at.isoformat(), "ended": g.ended, "entries": entries,
        "winner_ids": [str(w) for w in g.winner_ids], "seed": g.seed,
        "jump_url": f"https://discord.com/channels/{g.guild_id}/{g.channel_id}/{g.message_id}" if g.message_id else None,
    }


@router.get("/giveaways")
async def list_giveaways(access: GuildAccess = Depends(guild_access(1, module="giveaways")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    from nexus_core.db.models import GiveawayEntry

    rows = (await db.execute(
        select(Giveaway, func.count(GiveawayEntry.user_id)).outerjoin(GiveawayEntry, GiveawayEntry.giveaway_id == Giveaway.id)
        .where(Giveaway.guild_id == access.guild_id).group_by(Giveaway.id).order_by(Giveaway.id.desc()).limit(50))).all()
    return {"data": [_giveaway_json(g, n) for g, n in rows]}


@router.post("/giveaways", status_code=201, dependencies=[write_limit])
async def create_giveaway(body: dict[str, Any], request: Request,
                          access: GuildAccess = Depends(guild_access(2, module="giveaways")),
                          db: AsyncSession = Depends(get_db)) -> dict:
    g = _validate(GiveawayIn, body)
    res = await rpc(request, "giveaways.create", {**g.model_dump(mode="json"), "guild_id": access.guild_id,
                                                  "host_id": access.auth.user.id})
    await _audit(db, access, "giveaway.create", "giveaways", prize=g.prize)
    await db.commit()
    return res


@router.post("/giveaways/{giveaway_id}/{action}", dependencies=[write_limit])
async def giveaway_action(giveaway_id: int, action: Literal["end", "reroll", "cancel"], request: Request,
                          access: GuildAccess = Depends(guild_access(2, module="giveaways"))) -> dict:
    return await rpc(request, f"giveaways.{action}", {"guild_id": access.guild_id, "giveaway_id": giveaway_id})


@router.post("/polls", dependencies=[write_limit])
async def create_poll(body: dict[str, Any], request: Request,
                      access: GuildAccess = Depends(guild_access(2, module="polls"))) -> dict:
    p = _validate(PollIn, body)
    return await rpc(request, "polls.create", {**p.model_dump(mode="json"), "guild_id": access.guild_id})


# --- Comandos personalizados ------------------------------------------------------

MAX_COMMANDS = 50


def _cmd_json(c: CustomCommand) -> dict[str, Any]:
    return {"id": str(c.id), "name": c.name, "description": c.description, "enabled": c.enabled,
            "response": c.response, "ephemeral": c.ephemeral, "uses": c.uses, "version": c.version,
            "add_role_ids": [str(x) for x in c.add_role_ids], "remove_role_ids": [str(x) for x in c.remove_role_ids],
            "allowed_role_ids": [str(x) for x in c.allowed_role_ids]}


def _cmd_values(c: CustomCommandIn) -> dict[str, Any]:
    d = c.model_dump(mode="json")
    for k in ("add_role_ids", "remove_role_ids", "allowed_role_ids"):
        d[k] = [int(x) for x in d[k]]
    return d


async def _sync_commands(request: Request, guild_id: int) -> None:
    try:
        await publish(request.app.state.redis, "commands.sync", guild_id)
    except Exception:
        pass


@router.get("/custom-commands")
async def list_commands(access: GuildAccess = Depends(guild_access(1, module="custom_commands")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.scalars(select(CustomCommand).where(CustomCommand.guild_id == access.guild_id)
                             .order_by(CustomCommand.name))).all()
    return {"data": [_cmd_json(c) for c in rows], "can_edit": access.level >= 2, "max": MAX_COMMANDS}


@router.post("/custom-commands", status_code=201, dependencies=[write_limit])
async def create_command(body: dict[str, Any], request: Request,
                         access: GuildAccess = Depends(guild_access(2, module="custom_commands")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    data = _cmd_values(_validate(CustomCommandIn, body))
    count = await db.scalar(select(func.count()).select_from(CustomCommand).where(CustomCommand.guild_id == access.guild_id))
    if count >= MAX_COMMANDS:
        raise ApiError(400, "validation_error", fields={"_": "too_many_commands"})
    if await db.scalar(select(CustomCommand.id).where(CustomCommand.guild_id == access.guild_id,
                                                      CustomCommand.name == data["name"])):
        raise ApiError(400, "validation_error", fields={"name": "name_taken"})
    c = CustomCommand(guild_id=access.guild_id, **data)
    db.add(c)
    await db.flush()
    await _audit(db, access, "command.create", "custom_commands", name=c.name)
    await db.commit()
    await _sync_commands(request, access.guild_id)
    return {"data": _cmd_json(c)}


@router.put("/custom-commands/{command_id}", dependencies=[write_limit])
async def update_command(command_id: int, body: dict[str, Any], request: Request,
                         access: GuildAccess = Depends(guild_access(2, module="custom_commands")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    c = await db.get(CustomCommand, command_id)
    if c is None or c.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    if body.pop("version", None) != c.version:
        raise ApiError(409, "version_conflict", current_version=c.version)
    data = _cmd_values(_validate(CustomCommandIn, body))
    if data["name"] != c.name and await db.scalar(select(CustomCommand.id).where(
            CustomCommand.guild_id == access.guild_id, CustomCommand.name == data["name"])):
        raise ApiError(400, "validation_error", fields={"name": "name_taken"})
    for k, v in data.items():
        setattr(c, k, v)
    c.version += 1
    c.updated_at = utcnow()
    await _audit(db, access, "command.update", "custom_commands", name=c.name)
    await db.commit()
    await _sync_commands(request, access.guild_id)
    return {"data": _cmd_json(c)}


@router.delete("/custom-commands/{command_id}", status_code=204, dependencies=[write_limit])
async def delete_command(command_id: int, request: Request,
                         access: GuildAccess = Depends(guild_access(3, module="custom_commands")),
                         db: AsyncSession = Depends(get_db)) -> Response:
    c = await db.get(CustomCommand, command_id)
    if c is None or c.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    await _audit(db, access, "command.delete", "custom_commands", name=c.name)
    await db.delete(c)
    await db.commit()
    await _sync_commands(request, access.guild_id)
    return Response(status_code=204)


# --- Mensajes programados ---------------------------------------------------------

def _sched_json(m: ScheduledMessage) -> dict[str, Any]:
    return {"id": str(m.id), "name": m.name, "channel_id": str(m.channel_id), "message": m.message,
            "local_time": m.local_time, "timezone": m.timezone, "repeat": m.repeat, "status": m.status,
            "version": m.version,
            "next_run_at": m.next_run_at.isoformat() if m.next_run_at else None,
            "last_sent_at": m.last_sent_at.isoformat() if m.last_sent_at else None, "last_error": m.last_error}


schedule_job = schedule_message_job


async def _tz(db: AsyncSession, guild_id: int) -> str:
    cfg = await db.get(GuildConfig, guild_id)
    return cfg.timezone if cfg else "UTC"


@router.get("/scheduled-messages")
async def list_scheduled(access: GuildAccess = Depends(guild_access(1, module="scheduled_messages")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.scalars(select(ScheduledMessage).where(ScheduledMessage.guild_id == access.guild_id)
                             .order_by(ScheduledMessage.next_run_at.asc().nulls_last()))).all()
    return {"data": [_sched_json(m) for m in rows], "timezone": await _tz(db, access.guild_id),
            "can_edit": access.level >= 2}


def _sched_values(s: ScheduledMessageIn) -> dict[str, Any]:
    d = s.model_dump(mode="json")
    d["channel_id"] = int(d["channel_id"])
    d["status"] = "paused" if d.pop("paused") else "scheduled"
    return d


@router.post("/scheduled-messages", status_code=201, dependencies=[write_limit])
async def create_scheduled(body: dict[str, Any], access: GuildAccess = Depends(guild_access(2, module="scheduled_messages")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    data = _sched_values(_validate(ScheduledMessageIn, body))
    tz = data["timezone"] or await _tz(db, access.guild_id)
    if data["status"] == "scheduled" and next_run(data["local_time"], tz, data["repeat"], utcnow()) is None:
        raise ApiError(400, "validation_error", fields={"local_time": "in_the_past"})
    if await db.scalar(select(func.count()).select_from(ScheduledMessage).where(
            ScheduledMessage.guild_id == access.guild_id)) >= 50:
        raise ApiError(400, "validation_error", fields={"_": "too_many_messages"})
    m = ScheduledMessage(guild_id=access.guild_id, **data)
    db.add(m)
    await db.flush()
    await schedule_job(db, m, tz)
    await _audit(db, access, "scheduled.create", "scheduled_messages", name=m.name)
    await db.commit()
    return {"data": _sched_json(m)}


@router.put("/scheduled-messages/{message_id}", dependencies=[write_limit])
async def update_scheduled(message_id: int, body: dict[str, Any],
                           access: GuildAccess = Depends(guild_access(2, module="scheduled_messages")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    m = await db.get(ScheduledMessage, message_id)
    if m is None or m.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    if body.pop("version", None) != m.version:
        raise ApiError(409, "version_conflict", current_version=m.version)
    data = _sched_values(_validate(ScheduledMessageIn, body))
    tz = data["timezone"] or await _tz(db, access.guild_id)
    if data["status"] == "scheduled" and next_run(data["local_time"], tz, data["repeat"], utcnow()) is None:
        raise ApiError(400, "validation_error", fields={"local_time": "in_the_past"})
    for k, v in data.items():
        setattr(m, k, v)
    m.version += 1
    m.last_error = None
    await schedule_job(db, m, tz)
    await _audit(db, access, "scheduled.update", "scheduled_messages", name=m.name)
    await db.commit()
    return {"data": _sched_json(m)}


@router.post("/scheduled-messages/{message_id}/send-now", dependencies=[write_limit])
async def send_now(message_id: int, request: Request,
                   access: GuildAccess = Depends(guild_access(2, module="scheduled_messages"))) -> dict:
    return await rpc(request, "scheduled.send_now", {"guild_id": access.guild_id, "id": message_id})


@router.delete("/scheduled-messages/{message_id}", status_code=204, dependencies=[write_limit])
async def delete_scheduled(message_id: int, access: GuildAccess = Depends(guild_access(3, module="scheduled_messages")),
                           db: AsyncSession = Depends(get_db)) -> Response:
    m = await db.get(ScheduledMessage, message_id)
    if m is None or m.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    m.status = "paused"
    await schedule_job(db, m, "UTC")
    await _audit(db, access, "scheduled.delete", "scheduled_messages", name=m.name)
    await db.delete(m)
    await db.commit()
    return Response(status_code=204)

