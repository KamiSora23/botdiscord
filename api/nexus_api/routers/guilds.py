"""Servidores: lista, datos, overview, configuración, diagnóstico e historial."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.models import (
    DashboardRolePermission,
    Guild,
    GuildAuditLog,
    GuildConfig,
    GuildDailyStats,
    ModuleConfig,
    User,
)
from nexus_core.db.repo import add_audit, diff_changes, upsert_guild, utcnow
from nexus_core.discord.permissions import can_manage_guild
from nexus_core.discord.rest import avatar_url, guild_icon_url
from nexus_core.modules import REGISTRY
from nexus_core.sync import publish

from nexus_api.deps import (
    Auth,
    GuildAccess,
    current_auth,
    get_db,
    guild_access,
    rate_limit,
    require_csrf,
    module_levels,
    role_level,
)
from nexus_api.errors import ApiError
from nexus_api.routers.me import validate_timezone
from nexus_api.services import guild_data as G
from nexus_api.services.discord_user import get_user_guilds

router = APIRouter(prefix="/guilds", tags=["guilds"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])

write_limit = Depends(rate_limit("write", 30, per="guild"))


def guild_json(g: Guild) -> dict:
    return {
        "id": str(g.id),
        "name": g.name,
        "icon_url": guild_icon_url(g.id, g.icon),
        "member_count": g.member_count,
        "bot_present": g.bot_present,
    }


@router.get("")
async def list_guilds(request: Request, refresh: bool = False,
                      auth: Auth = Depends(current_auth), db: AsyncSession = Depends(get_db)) -> dict:
    guilds = await get_user_guilds(request, db, auth.user, fresh=refresh)
    manageable = [g for g in guilds
                  if can_manage_guild(int(g.get("permissions", 0)), is_owner=g.get("owner", False))]
    # Servidores donde no administra, pero un rol suyo tiene acceso al dashboard (fase 3).
    others = [g for g in guilds if g not in manageable]
    if others:
        with_perms = set((await db.scalars(select(DashboardRolePermission.guild_id).distinct().where(
            DashboardRolePermission.guild_id.in_([int(g["id"]) for g in others])))).all())
        for g in others:
            if int(g["id"]) in with_perms and await role_level(request, db, int(g["id"]), auth.user.id, None) > 0:
                g = {**g, "_role_access": True}
                manageable.append(g)
    ids = [int(g["id"]) for g in manageable]
    rows = {g.id: g for g in (await db.scalars(select(Guild).where(Guild.id.in_(ids)))).all()} if ids else {}
    data = []
    for g in manageable:
        gid = int(g["id"])
        row = rows.get(gid)
        present = bool(row and row.bot_present)
        data.append({
            "id": g["id"],
            "name": g["name"],
            "icon_url": guild_icon_url(gid, g.get("icon")),
            "member_count": row.member_count if present else None,
            "bot_present": present,
            "access": "role" if g.get("_role_access") else "full",
            "invite_url": None if present else G.invite_url_for(gid),
        })
    data.sort(key=lambda x: (not x["bot_present"], x["name"].lower()))
    return {"data": data}


@router.get("/{guild_id}")
async def get_guild(request: Request, access: GuildAccess = Depends(guild_access(1, require_bot=False)),
                    db: AsyncSession = Depends(get_db)) -> dict:
    dg = access.discord_guild
    if access.guild is None:
        # Primera vez que alguien abre este servidor: se registra (sin bot todavía).
        await upsert_guild(db, guild_id=access.guild_id, name=dg["name"], icon=dg.get("icon"),
                           owner_id=access.auth.user.id if dg.get("owner") else 0)
        await db.commit()
        guild = await db.get(Guild, access.guild_id)
    else:
        guild = access.guild
    assert guild is not None
    # Quien administra el servidor lo ve todo; el resto, solo las secciones que su rol tiene en «Permisos».
    full = can_manage_guild(int(dg.get("permissions", 0)), is_owner=dg.get("owner", False))
    levels = {"*": 3} if full else await module_levels(request, db, access.guild_id, access.auth.user.id)
    return {
        **guild_json(guild),
        "access_level": access.level,
        "full_access": full,
        "module_levels": levels,
        "invite_url": None if guild.bot_present else G.invite_url_for(access.guild_id),
    }


@router.get("/{guild_id}/channels")
async def channels(request: Request, access: GuildAccess = Depends(guild_access(1))) -> dict:
    assert access.guild is not None
    return {"data": await G.channels_with_bot_perms(request, access.guild_id, access.guild.owner_id)}


@router.get("/{guild_id}/roles")
async def roles(request: Request, access: GuildAccess = Depends(guild_access(1))) -> dict:
    raw = await G.guild_roles(request, access.guild_id)
    bot_top = 0
    try:
        member = await G.bot_member(request, access.guild_id)
        mine = {str(x) for x in (member or {}).get("roles", [])}
        bot_top = max([r.get("position", 0) for r in raw if str(r["id"]) in mine] or [0])
    except Exception:
        pass
    data = [
        {"id": str(r["id"]), "name": r["name"], "color": r.get("color", 0),
         "position": r.get("position", 0), "managed": r.get("managed", False),
         "is_everyone": str(r["id"]) == str(access.guild_id),
         "bot_can_assign": r.get("position", 0) < bot_top and not r.get("managed", False)}
        for r in raw
    ]
    data.sort(key=lambda r: -r["position"])
    return {"data": data}


async def _module_states(db: AsyncSession, guild_id: int) -> list[dict]:
    rows = {m.module: m for m in (await db.scalars(
        select(ModuleConfig).where(ModuleConfig.guild_id == guild_id))).all()}
    return [
        {"module": m.key, "category": m.category, "available": m.available, "phase": m.phase,
         "toggleable": m.toggleable, "enabled": bool(rows.get(m.key) and rows[m.key].enabled)}
        for m in REGISTRY.values()
    ]


@router.get("/{guild_id}/modules")
async def modules(access: GuildAccess = Depends(guild_access(1)),
                  db: AsyncSession = Depends(get_db)) -> dict:
    return {"data": await _module_states(db, access.guild_id)}


@router.get("/{guild_id}/overview")
async def overview(request: Request, days: int = Query(7),
                   access: GuildAccess = Depends(guild_access(1)),
                   db: AsyncSession = Depends(get_db)) -> dict:
    if days not in (7, 30):
        raise ApiError(400, "validation_error", fields={"days": "must_be_7_or_30"})
    guild = access.guild
    assert guild is not None
    today = utcnow().date()
    start = today - timedelta(days=days - 1)
    stats_rows = (await db.scalars(
        select(GuildDailyStats)
        .where(GuildDailyStats.guild_id == guild.id, GuildDailyStats.day >= start)
    )).all()
    by_day = {r.day: r for r in stats_rows}
    chart = []
    for i in range(days):
        d: date = start + timedelta(days=i)
        r = by_day.get(d)
        chart.append({"day": d.isoformat(),
                      "members_joined": r.members_joined if r else 0,
                      "members_left": r.members_left if r else 0,
                      "commands_used": r.commands_used if r else 0})
    last7 = [c for c in chart if c["day"] >= (today - timedelta(days=6)).isoformat()]

    mods = await _module_states(db, guild.id)
    avail = [m for m in mods if m["available"] and m["toggleable"]]

    alerts = await G.guild_alerts(request, guild.id)
    try:
        base, _ = await G.bot_base_permissions(request, guild.id, guild.owner_id)
        for p in G.missing_permissions(base):
            if not p["granted"]:
                alerts.insert(0, {"code": "missing_permission", "permission": p["permission"],
                                  "severity": "error"})
    except Exception:
        pass  # Discord no disponible: el resto del overview sigue funcionando.

    audit = (await db.execute(
        select(GuildAuditLog, User)
        .outerjoin(User, User.id == GuildAuditLog.actor_id)
        .where(GuildAuditLog.guild_id == guild.id)
        .order_by(GuildAuditLog.created_at.desc())
        .limit(8)
    )).all()

    return {
        "guild": guild_json(guild),
        "bot": await G.bot_status(request),
        "stats": {
            "member_count": guild.member_count,
            "joined_7d": sum(c["members_joined"] for c in last7),
            "left_7d": sum(c["members_left"] for c in last7),
            "commands_7d": sum(c["commands_used"] for c in last7),
            "modules_enabled": sum(1 for m in avail if m["enabled"]),
            "modules_total": len(avail),
        },
        "chart": chart,
        "modules": mods,
        "alerts": alerts,
        "recent_activity": [_audit_json(a, u) for a, u in audit],
    }


def _audit_json(a: GuildAuditLog, u: User | None) -> dict:
    actor = None
    if a.actor_id is not None:
        actor = {
            "id": str(a.actor_id),
            "name": (u.global_name or u.username) if u else None,
            "avatar_url": avatar_url(a.actor_id, u.avatar if u else None),
        }
    return {
        "id": str(a.id),
        "actor": actor,
        "source": a.source,
        "action": a.action,
        "module": a.module,
        "changes": a.changes,
        "created_at": a.created_at.isoformat(),
    }


# --- Configuración general -------------------------------------------------

def _settings_json(c: GuildConfig) -> dict:
    return {
        "locale": c.locale,
        "timezone": c.timezone,
        "embed_color": c.embed_color,
        "version": c.version,
        "updated_at": c.updated_at.isoformat(),
        "updated_by": str(c.updated_by) if c.updated_by else None,
    }


class SettingsIn(BaseModel):
    locale: Literal["es", "en"]
    timezone: str
    embed_color: int = Field(ge=0, le=0xFFFFFF)
    version: int = Field(ge=1)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        return validate_timezone(v)


async def _config(db: AsyncSession, guild_id: int) -> GuildConfig:
    cfg = await db.get(GuildConfig, guild_id)
    if cfg is None:
        raise ApiError(404, "not_found")
    return cfg


@router.get("/{guild_id}/settings")
async def get_settings_(access: GuildAccess = Depends(guild_access(1, module="settings")),
                        db: AsyncSession = Depends(get_db)) -> dict:
    return {"data": _settings_json(await _config(db, access.guild_id)),
            "can_edit": access.level >= 3}


@router.put("/{guild_id}/settings", dependencies=[write_limit])
async def put_settings(body: SettingsIn, request: Request,
                       access: GuildAccess = Depends(guild_access(3, module="settings")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    cfg = await _config(db, access.guild_id)
    old = {"locale": cfg.locale, "timezone": cfg.timezone, "embed_color": cfg.embed_color}
    new = {"locale": body.locale, "timezone": body.timezone, "embed_color": body.embed_color}
    result = await db.execute(
        update(GuildConfig)
        .where(GuildConfig.guild_id == access.guild_id, GuildConfig.version == body.version)
        .values(**new, version=GuildConfig.version + 1, updated_at=utcnow(),
                updated_by=access.auth.user.id)
        .returning(GuildConfig.version)
    )
    new_version = result.scalar_one_or_none()
    if new_version is None:
        await db.rollback()
        current = await db.scalar(
            select(GuildConfig.version).where(GuildConfig.guild_id == access.guild_id))
        raise ApiError(409, "version_conflict", current_version=current)
    changes = diff_changes(old, new)
    if changes:
        await add_audit(db, guild_id=access.guild_id, action="settings.update", source="dashboard",
                        actor_id=access.auth.user.id, changes=changes)
    await db.commit()
    try:
        await publish(request.app.state.redis, "settings.updated", access.guild_id,
                      version=new_version)
    except Exception:
        pass  # el bot recupera el cambio en su revisión periódica
    await db.refresh(cfg)
    return {"data": _settings_json(cfg), "warnings": []}


# --- Diagnóstico -----------------------------------------------------------

@router.get("/{guild_id}/diagnostics")
async def diagnostics(request: Request, access: GuildAccess = Depends(guild_access(1))) -> dict:
    guild = access.guild
    assert guild is not None
    base, _ = await G.bot_base_permissions(request, guild.id, guild.owner_id)
    perms = G.missing_permissions(base)
    status = await G.bot_status(request)
    issues = [{"code": "missing_permission", "permission": p["permission"], "severity": "error"}
              for p in perms if not p["granted"]]
    if not status["online"]:
        issues.insert(0, {"code": "bot_offline", "severity": "warning"})
    else:
        if not status["intents"].get("guild_members", False):
            issues.append({"code": "missing_intent", "intent": "guild_members", "severity": "error"})
        if not status["intents"].get("message_content", False):
            issues.append({"code": "missing_intent", "intent": "message_content", "severity": "warning"})
    return {
        "permissions": perms,
        "intents": {"guild_members": status["intents"].get("guild_members"),
                    "message_content": status["intents"].get("message_content")},
        "issues": issues,
        "invite_url": G.invite_url_for(guild.id),
    }


# --- Historial -------------------------------------------------------------

@router.get("/{guild_id}/audit-log")
async def audit_log(access: GuildAccess = Depends(guild_access(1)),
                    db: AsyncSession = Depends(get_db),
                    cursor: str | None = None, limit: int = Query(50, ge=1, le=100),
                    module: str | None = None) -> dict:
    q = (select(GuildAuditLog, User)
         .outerjoin(User, User.id == GuildAuditLog.actor_id)
         .where(GuildAuditLog.guild_id == access.guild_id))
    if cursor and cursor.isdigit():
        q = q.where(GuildAuditLog.id < int(cursor))
    if module:
        q = q.where(GuildAuditLog.module == module)
    rows = (await db.execute(q.order_by(GuildAuditLog.id.desc()).limit(limit + 1))).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "data": [_audit_json(a, u) for a, u in rows],
        "next_cursor": str(rows[-1][0].id) if has_more and rows else None,
    }
