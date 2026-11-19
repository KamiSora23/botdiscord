"""Fase 8: estadísticas del servidor, plantillas y asistente de configuración (Quick Setup)."""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.models import (
    GuildConfig,
    GuildDailyStats,
    MemberXP,
    ModerationCase,
    ModuleConfig,
    Suggestion,
    Ticket,
)
from nexus_core.db.repo import add_audit, utcnow
from nexus_core.modules import REGISTRY
from nexus_core.sync import publish
from nexus_core.templates import CHANNEL_SLOTS, TEMPLATES, build_configs

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.errors import ApiError

router = APIRouter(prefix="/guilds/{guild_id}", tags=["insights"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])


@router.get("/analytics")
async def analytics(access: GuildAccess = Depends(guild_access(1)), db: AsyncSession = Depends(get_db),
                    days: int = Query(30)) -> dict:
    if days not in (7, 30, 90):
        raise ApiError(400, "validation_error", fields={"days": "must_be_7_30_or_90"})
    gid = access.guild_id
    start = utcnow().date() - timedelta(days=days - 1)
    rows = {r.day: r for r in (await db.scalars(select(GuildDailyStats).where(
        GuildDailyStats.guild_id == gid, GuildDailyStats.day >= start))).all()}
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        r = rows.get(d)
        series.append({"day": d.isoformat(), "joined": r.members_joined if r else 0, "left": r.members_left if r else 0,
                       "commands": r.commands_used if r else 0, "welcome": r.welcome_sent if r else 0,
                       "mod": r.mod_actions if r else 0})
    since = utcnow() - timedelta(days=days)
    mod_by_action = dict((await db.execute(select(ModerationCase.action, func.count()).where(
        ModerationCase.guild_id == gid, ModerationCase.created_at >= since).group_by(ModerationCase.action))).all())
    mod_by_source = dict((await db.execute(select(ModerationCase.source, func.count()).where(
        ModerationCase.guild_id == gid, ModerationCase.created_at >= since).group_by(ModerationCase.source))).all())
    tickets_opened = await db.scalar(select(func.count()).select_from(Ticket).where(
        Ticket.guild_id == gid, Ticket.opened_at >= since))
    suggestions = await db.scalar(select(func.count()).select_from(Suggestion).where(
        Suggestion.guild_id == gid, Suggestion.created_at >= since))
    active_members = await db.scalar(select(func.count()).select_from(MemberXP).where(
        MemberXP.guild_id == gid, MemberXP.last_xp_at >= since))
    totals = {k: sum(s[k] for s in series) for k in ("joined", "left", "commands", "welcome", "mod")}
    return {"days": days, "series": series, "totals": {**totals, "net_growth": totals["joined"] - totals["left"],
                                                       "tickets": tickets_opened or 0, "suggestions": suggestions or 0,
                                                       "active_members": active_members or 0},
            "moderation": {"by_action": mod_by_action, "by_source": mod_by_source}}


# --- Plantillas y Quick Setup ---------------------------------------------------

@router.get("/templates")
async def list_templates(access: GuildAccess = Depends(guild_access(1)), db: AsyncSession = Depends(get_db)) -> dict:
    existing = {m.module: m for m in (await db.scalars(select(ModuleConfig).where(
        ModuleConfig.guild_id == access.guild_id))).all()}
    return {
        "templates": [{"key": k, "modules": list(v)} for k, v in TEMPLATES.items()],
        "configured": [m for m, row in existing.items() if row.enabled],
        "slots": list(CHANNEL_SLOTS),
        "can_apply": access.level >= 3,
    }


class SetupIn(BaseModel):
    template: Literal["gaming", "support", "creator", "study", "professional", "minimal"]
    modules: list[str] | None = Field(None, max_length=30)  # subconjunto elegido en el asistente (None = todos)
    channels: dict[str, str | None] = Field(default_factory=dict)
    overwrite: bool = False


@router.post("/setup", dependencies=[Depends(rate_limit("setup", 5, per="guild"))])
async def apply_setup(body: SetupIn, request: Request, access: GuildAccess = Depends(guild_access(3, module="*")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    cfg = await db.get(GuildConfig, access.guild_id)
    locale = cfg.locale if cfg else "es"
    channels = {k: v for k, v in body.channels.items() if k in CHANNEL_SLOTS and (v is None or v.isdigit())}
    try:
        configs = build_configs(body.template, locale, channels)
    except ValueError as exc:
        raise ApiError(400, "validation_error", fields={"channels": "invalid"}) from exc
    if body.modules is not None:
        configs = {m: c for m, c in configs.items() if m in set(body.modules)}
    existing = {m.module: m for m in (await db.scalars(select(ModuleConfig).where(
        ModuleConfig.guild_id == access.guild_id, ModuleConfig.module.in_(list(configs))))).all()}
    applied, skipped = [], []
    now = utcnow()
    for module, data in configs.items():
        info = REGISTRY.get(module)
        if info is None or not info.available:
            continue
        row = existing.get(module)
        if row is not None and row.config and not body.overwrite:
            # Ya configurado: solo se activa, sin tocar su configuración.
            if not row.enabled:
                row.enabled, row.version, row.updated_at = True, row.version + 1, now
                applied.append(module)
            else:
                skipped.append(module)
            continue
        await db.execute(insert(ModuleConfig).values(
            guild_id=access.guild_id, module=module, enabled=info.toggleable, config=data, version=1,
            updated_at=now, updated_by=access.auth.user.id,
        ).on_conflict_do_update(index_elements=[ModuleConfig.guild_id, ModuleConfig.module], set_={
            "enabled": info.toggleable, "config": data, "version": ModuleConfig.version + 1, "updated_at": now,
            "updated_by": access.auth.user.id}))
        applied.append(module)
    await add_audit(db, guild_id=access.guild_id, action="setup.apply", source="dashboard",
                    actor_id=access.auth.user.id,
                    changes={"template": {"old": None, "new": body.template}, "modules": {"old": None, "new": applied}})
    await db.commit()
    try:
        await publish(request.app.state.redis, "guild.reload", access.guild_id)
    except Exception:
        pass
    return {"applied": applied, "skipped": skipped}

