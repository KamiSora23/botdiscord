"""Fase 4: paneles de Reaction Roles y gestión de miembros."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.cases import active_warn_count, case_json
from nexus_core.db.models import MemberNote, ModerationCase, RolePanel
from nexus_core.db.repo import add_audit, utcnow
from nexus_core.discord.rest import DiscordError, avatar_url
from nexus_core.modules.roles import RolePanelIn
from nexus_core.rpc import RpcError, call

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.errors import ApiError
from nexus_api.services.guild_data import reject_dangerous_roles
from nexus_api.routers.modules import validation_fields

router = APIRouter(prefix="/guilds/{guild_id}", tags=["roles"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])
write_limit = Depends(rate_limit("write", 30, per="guild"))

MAX_PANELS = 25


async def rpc(request: Request, method: str, params: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    try:
        return await call(request.app.state.redis, method, params, timeout=timeout)
    except RpcError as exc:
        raise ApiError(409 if exc.code not in ("bot_offline", "bot_timeout") else 503, exc.code, **exc.extra) from exc


def panel_json(p: RolePanel) -> dict[str, Any]:
    return {
        "id": str(p.id), "name": p.name, "channel_id": str(p.channel_id) if p.channel_id else None,
        "message_id": str(p.message_id) if p.message_id else None, "panel_type": p.panel_type, "mode": p.mode,
        "message": p.message, "max_choices": p.max_choices, "placeholder": p.placeholder,
        "options": p.options, "version": p.version,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "outdated": bool(p.published_at and p.updated_at > p.published_at),
        "jump_url": f"https://discord.com/channels/{p.guild_id}/{p.channel_id}/{p.message_id}" if p.message_id else None,
    }


def _parse(body: dict[str, Any]) -> dict[str, Any]:
    try:
        data = RolePanelIn.model_validate(body).model_dump(mode="json")
    except ValidationError as exc:
        raise ApiError(400, "validation_error", fields=validation_fields(exc)) from exc
    data["channel_id"] = int(data["channel_id"]) if data["channel_id"] else None
    return data


async def _panel(db: AsyncSession, guild_id: int, panel_id: int) -> RolePanel:
    p = await db.get(RolePanel, panel_id)
    if p is None or p.guild_id != guild_id:
        raise ApiError(404, "not_found")
    return p


@router.get("/role-panels")
async def list_panels(access: GuildAccess = Depends(guild_access(1, module="reaction_roles")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.scalars(select(RolePanel).where(RolePanel.guild_id == access.guild_id).order_by(RolePanel.id))).all()
    return {"data": [panel_json(p) for p in rows], "can_edit": access.level >= 2}


@router.post("/role-panels", status_code=201, dependencies=[write_limit])
async def create_panel(body: dict[str, Any], request: Request,
                       access: GuildAccess = Depends(guild_access(2, module="reaction_roles")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    data = _parse(body)
    await reject_dangerous_roles(request, access.guild_id, [o["role_id"] for o in data["options"]], "options")
    count = len((await db.scalars(select(RolePanel.id).where(RolePanel.guild_id == access.guild_id))).all())
    if count >= MAX_PANELS:
        raise ApiError(400, "validation_error", fields={"_": "too_many_panels"})
    p = RolePanel(guild_id=access.guild_id, **data)
    db.add(p)
    await db.flush()
    await add_audit(db, guild_id=access.guild_id, action="role_panel.create", source="dashboard",
                    actor_id=access.auth.user.id, module="reaction_roles", changes={"panel": {"old": None, "new": p.name}})
    await db.commit()
    return {"data": panel_json(p)}


@router.put("/role-panels/{panel_id}", dependencies=[write_limit])
async def update_panel(panel_id: int, body: dict[str, Any], request: Request,
                       access: GuildAccess = Depends(guild_access(2, module="reaction_roles")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    p = await _panel(db, access.guild_id, panel_id)
    if body.pop("version", None) != p.version:
        raise ApiError(409, "version_conflict", current_version=p.version)
    data = _parse(body)
    await reject_dangerous_roles(request, access.guild_id, [o["role_id"] for o in data["options"]], "options")
    if p.message_id and data["channel_id"] != p.channel_id:
        raise ApiError(400, "validation_error", fields={"channel_id": "unpublish_first"})
    for k, v in data.items():
        setattr(p, k, v)
    p.version += 1
    p.updated_at = utcnow()
    await add_audit(db, guild_id=access.guild_id, action="role_panel.update", source="dashboard",
                    actor_id=access.auth.user.id, module="reaction_roles")
    await db.commit()
    return {"data": panel_json(p)}


@router.post("/role-panels/{panel_id}/publish", dependencies=[write_limit])
async def publish_panel(panel_id: int, request: Request,
                        access: GuildAccess = Depends(guild_access(2, module="reaction_roles")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    p = await _panel(db, access.guild_id, panel_id)
    if not p.channel_id:
        raise ApiError(400, "validation_error", fields={"channel_id": "channel_required"})
    res = await rpc(request, "role_panel.publish", {"guild_id": access.guild_id, "panel_id": p.id})
    await db.refresh(p)
    await add_audit(db, guild_id=access.guild_id, action="role_panel.publish", source="dashboard",
                    actor_id=access.auth.user.id, module="reaction_roles")
    await db.commit()
    return {"data": panel_json(p), "result": res}


@router.delete("/role-panels/{panel_id}", status_code=204, dependencies=[write_limit])
async def delete_panel(panel_id: int, request: Request, delete_message: bool = True,
                       access: GuildAccess = Depends(guild_access(3, module="reaction_roles")),
                       db: AsyncSession = Depends(get_db)) -> Response:
    p = await _panel(db, access.guild_id, panel_id)
    if p.message_id and p.channel_id and delete_message:
        try:
            await request.app.state.discord.request("DELETE", f"/channels/{p.channel_id}/messages/{p.message_id}")
        except DiscordError:
            pass  # el mensaje ya no existía
    await add_audit(db, guild_id=access.guild_id, action="role_panel.delete", source="dashboard",
                    actor_id=access.auth.user.id, module="reaction_roles", changes={"panel": {"old": p.name, "new": None}})
    await db.delete(p)
    await db.commit()
    return Response(status_code=204)


# --- Miembros ----------------------------------------------------------------

def _member_json(m: dict[str, Any], guild_id: int) -> dict[str, Any]:
    u = m["user"]
    return {
        "id": u["id"], "username": u["username"], "global_name": u.get("global_name"), "nick": m.get("nick"),
        "avatar_url": avatar_url(u["id"], u.get("avatar")), "bot": u.get("bot", False),
        "roles": m.get("roles", []), "joined_at": m.get("joined_at"),
        "timed_out_until": m.get("communication_disabled_until"),
    }


@router.get("/members")
async def search_members(request: Request, query: str = Query("", max_length=100),
                         access: GuildAccess = Depends(guild_access(1, module="moderation"))) -> dict:
    rest = request.app.state.discord
    if query.isdigit() and len(query) >= 15:
        try:
            members = [await rest.request("GET", f"/guilds/{access.guild_id}/members/{query}")]
        except DiscordError:
            members = []
    elif query.strip():
        members = await rest.request("GET", f"/guilds/{access.guild_id}/members/search",
                                     params={"query": query.strip(), "limit": 25})
    else:
        members = await rest.request("GET", f"/guilds/{access.guild_id}/members", params={"limit": 25})
    return {"data": [_member_json(m, access.guild_id) for m in members]}


@router.get("/members/{user_id}")
async def member_profile(user_id: int, request: Request,
                         access: GuildAccess = Depends(guild_access(1, module="moderation")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    member = None
    try:
        member = _member_json(await request.app.state.discord.request(
            "GET", f"/guilds/{access.guild_id}/members/{user_id}"), access.guild_id)
    except DiscordError:
        pass
    cases = (await db.scalars(select(ModerationCase).where(
        ModerationCase.guild_id == access.guild_id, ModerationCase.target_id == user_id)
        .order_by(ModerationCase.case_number.desc()).limit(50))).all()
    notes = (await db.scalars(select(MemberNote).where(
        MemberNote.guild_id == access.guild_id, MemberNote.user_id == user_id)
        .order_by(MemberNote.id.desc()))).all()
    if member is None and not cases and not notes:
        raise ApiError(404, "not_found")
    return {
        "member": member,
        "in_guild": member is not None,
        "active_warns": await active_warn_count(db, access.guild_id, user_id),
        "cases": [case_json(c) for c in cases],
        "notes": [{"id": str(n.id), "author": n.author_name, "note": n.note, "created_at": n.created_at.isoformat()}
                  for n in notes],
        "can_act": access.level >= 2,
    }


class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


@router.post("/members/{user_id}/notes", status_code=201, dependencies=[write_limit])
async def add_note(user_id: int, body: NoteIn, access: GuildAccess = Depends(guild_access(2, module="moderation")),
                   db: AsyncSession = Depends(get_db)) -> dict:
    u = access.auth.user
    n = MemberNote(guild_id=access.guild_id, user_id=user_id, author_id=u.id,
                   author_name=u.global_name or u.username, note=body.note.strip())
    db.add(n)
    await db.commit()
    return {"id": str(n.id)}


@router.delete("/members/{user_id}/notes/{note_id}", status_code=204, dependencies=[write_limit])
async def delete_note(user_id: int, note_id: int, access: GuildAccess = Depends(guild_access(2, module="moderation")),
                      db: AsyncSession = Depends(get_db)) -> Response:
    n = await db.get(MemberNote, note_id)
    if n is None or n.guild_id != access.guild_id or n.user_id != user_id:
        raise ApiError(404, "not_found")
    await db.delete(n)
    await db.commit()
    return Response(status_code=204)


class ActionIn(BaseModel):
    action: Literal["warn", "timeout", "untimeout", "kick", "ban", "unban"]
    reason: str | None = Field(None, max_length=1000)
    duration_seconds: int | None = Field(None, ge=60, le=2419200 * 52)


@router.post("/members/{user_id}/actions", dependencies=[write_limit])
async def member_action(user_id: int, body: ActionIn, request: Request,
                        access: GuildAccess = Depends(guild_access(2, module="moderation"))) -> dict:
    """Se ejecuta en el bot (jerarquía, aviso por MD, caso, escalado), igual que los comandos."""
    if body.action == "timeout" and not body.duration_seconds:
        raise ApiError(400, "validation_error", fields={"duration_seconds": "duration_required"})
    res = await rpc(request, "mod.action", {
        "guild_id": access.guild_id, "user_id": user_id, "moderator_id": access.auth.user.id,
        "action": body.action, "reason": body.reason, "duration": body.duration_seconds,
    })
    return {"case": res.get("case")}
