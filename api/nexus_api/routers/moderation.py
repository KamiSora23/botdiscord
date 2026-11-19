"""Fase 3: casos de moderación, reglas de AutoMod y permisos del dashboard por rol."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.automod import MessageInfo, check_message
from nexus_core.cases import case_json
from nexus_core.db.models import AutomodEvent, AutomodRule, DashboardRolePermission, ModerationCase
from nexus_core.db.repo import add_audit, diff_changes, utcnow
from nexus_core.modules import REGISTRY
from nexus_core.modules.moderation import AutomodRuleIn
from nexus_core.sync import publish

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.errors import ApiError
from nexus_api.routers.modules import validation_fields
from nexus_api.services import guild_data as G

router = APIRouter(prefix="/guilds/{guild_id}", tags=["moderation"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])
write_limit = Depends(rate_limit("write", 30, per="guild"))


async def _sync(request: Request, guild_id: int, module: str) -> None:
    try:
        await publish(request.app.state.redis, "module.updated", guild_id, module=module)
    except Exception:
        pass


# --- Casos -------------------------------------------------------------------

@router.get("/moderation/cases")
async def list_cases(access: GuildAccess = Depends(guild_access(1, module="moderation")),
                     db: AsyncSession = Depends(get_db), target: str | None = None,
                     action: str | None = None, active: bool | None = None,
                     cursor: int | None = None, limit: int = Query(50, ge=1, le=100)) -> dict:
    q = select(ModerationCase).where(ModerationCase.guild_id == access.guild_id)
    if target:
        q = q.where(ModerationCase.target_id == int(target)) if target.isdigit() else \
            q.where(ModerationCase.target_name.ilike(f"%{target.replace('%', '')}%"))
    if action:
        q = q.where(ModerationCase.action == action)
    if active is not None:
        q = q.where(ModerationCase.active.is_(active))
    if cursor:
        q = q.where(ModerationCase.case_number < cursor)
    rows = (await db.scalars(q.order_by(ModerationCase.case_number.desc()).limit(limit + 1))).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"data": [case_json(c) for c in rows], "next_cursor": rows[-1].case_number if more and rows else None}


async def _case(db: AsyncSession, guild_id: int, number: int) -> ModerationCase:
    c = await db.scalar(select(ModerationCase).where(ModerationCase.guild_id == guild_id,
                                                     ModerationCase.case_number == number))
    if c is None:
        raise ApiError(404, "not_found")
    return c


@router.get("/moderation/cases/{number}")
async def get_case(number: int, access: GuildAccess = Depends(guild_access(1, module="moderation")),
                   db: AsyncSession = Depends(get_db)) -> dict:
    c = await _case(db, access.guild_id, number)
    history = (await db.scalars(select(ModerationCase).where(
        ModerationCase.guild_id == access.guild_id, ModerationCase.target_id == c.target_id)
        .order_by(ModerationCase.case_number.desc()).limit(25))).all()
    return {"data": case_json(c), "history": [case_json(h) for h in history]}


class CasePatch(BaseModel):
    reason: str | None = Field(None, max_length=1000)
    active: bool | None = None


@router.patch("/moderation/cases/{number}", dependencies=[write_limit])
async def patch_case(number: int, body: CasePatch, access: GuildAccess = Depends(guild_access(2, module="moderation")),
                     db: AsyncSession = Depends(get_db)) -> dict:
    c = await _case(db, access.guild_id, number)
    old = {"reason": c.reason, "active": c.active}
    if body.reason is not None:
        c.reason = body.reason.strip() or None
    if body.active is not None:
        if c.action not in ("warn", "note") and body.active:
            raise ApiError(400, "validation_error", fields={"active": "only_warns"})
        c.active = body.active
    changes = diff_changes(old, {"reason": c.reason, "active": c.active})
    if changes:
        await add_audit(db, guild_id=access.guild_id, action="case.update", source="dashboard",
                        actor_id=access.auth.user.id, module="moderation",
                        changes={f"case_{number}.{k}": v for k, v in changes.items()})
    await db.commit()
    return {"data": case_json(c)}


# --- AutoMod -----------------------------------------------------------------

def _rule_json(r: AutomodRule) -> dict[str, Any]:
    return {
        "id": str(r.id), "name": r.name, "enabled": r.enabled, "rule_type": r.rule_type, "config": r.config,
        "actions": r.actions, "exempt_role_ids": [str(x) for x in r.exempt_role_ids],
        "exempt_channel_ids": [str(x) for x in r.exempt_channel_ids], "priority": r.priority,
        "test_mode": r.test_mode, "version": r.version, "updated_at": r.updated_at.isoformat(),
    }


MAX_RULES = 50


@router.get("/automod/rules")
async def list_rules(access: GuildAccess = Depends(guild_access(1, module="automod")),
                     db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.scalars(select(AutomodRule).where(AutomodRule.guild_id == access.guild_id)
                             .order_by(AutomodRule.priority.desc(), AutomodRule.id))).all()
    return {"data": [_rule_json(r) for r in rows], "can_edit": access.level >= 2}


def _parse_rule(body: dict[str, Any]) -> AutomodRuleIn:
    try:
        return AutomodRuleIn.model_validate(body)
    except ValidationError as exc:
        raise ApiError(400, "validation_error", fields=validation_fields(exc)) from exc


def _rule_values(r: AutomodRuleIn) -> dict[str, Any]:
    d = r.model_dump(mode="json")
    d["exempt_role_ids"] = [int(x) for x in d["exempt_role_ids"]]
    d["exempt_channel_ids"] = [int(x) for x in d["exempt_channel_ids"]]
    return d


@router.post("/automod/rules", status_code=201, dependencies=[write_limit])
async def create_rule(body: dict[str, Any], request: Request,
                      access: GuildAccess = Depends(guild_access(2, module="automod")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    data = _rule_values(_parse_rule(body))
    count = len((await db.scalars(select(AutomodRule.id).where(AutomodRule.guild_id == access.guild_id))).all())
    if count >= MAX_RULES:
        raise ApiError(400, "validation_error", fields={"_": "too_many_rules"})
    rule = AutomodRule(guild_id=access.guild_id, **data)
    db.add(rule)
    await db.flush()
    await add_audit(db, guild_id=access.guild_id, action="automod.rule_create", source="dashboard",
                    actor_id=access.auth.user.id, module="automod",
                    changes={"rule": {"old": None, "new": rule.name}})
    await db.commit()
    await _sync(request, access.guild_id, "automod")
    return {"data": _rule_json(rule)}


@router.put("/automod/rules/{rule_id}", dependencies=[write_limit])
async def update_rule(rule_id: int, body: dict[str, Any], request: Request,
                      access: GuildAccess = Depends(guild_access(2, module="automod")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    rule = await db.get(AutomodRule, rule_id)
    if rule is None or rule.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    version = body.pop("version", None)
    if version != rule.version:
        raise ApiError(409, "version_conflict", current_version=rule.version)
    data = _rule_values(_parse_rule(body))
    old = _rule_json(rule)
    for k, v in data.items():
        setattr(rule, k, v)
    rule.version += 1
    rule.updated_at = utcnow()
    changes = diff_changes({k: old[k] for k in data}, {k: _rule_json(rule)[k] for k in data})
    if changes:
        await add_audit(db, guild_id=access.guild_id, action="automod.rule_update", source="dashboard",
                        actor_id=access.auth.user.id, module="automod",
                        changes={f"{rule.name}.{k}": v for k, v in changes.items()})
    await db.commit()
    await _sync(request, access.guild_id, "automod")
    return {"data": _rule_json(rule)}


@router.delete("/automod/rules/{rule_id}", status_code=204, dependencies=[write_limit])
async def delete_rule(rule_id: int, request: Request, access: GuildAccess = Depends(guild_access(3, module="automod")),
                      db: AsyncSession = Depends(get_db)) -> Response:
    rule = await db.get(AutomodRule, rule_id)
    if rule is None or rule.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    await add_audit(db, guild_id=access.guild_id, action="automod.rule_delete", source="dashboard",
                    actor_id=access.auth.user.id, module="automod", changes={"rule": {"old": rule.name, "new": None}})
    await db.delete(rule)
    await db.commit()
    await _sync(request, access.guild_id, "automod")
    return Response(status_code=204)


class TestIn(BaseModel):
    text: str = Field(max_length=4000)
    rule: dict[str, Any] | None = None  # si se da, se prueba solo esta regla (aún sin guardar)


@router.post("/automod/test")
async def test_rules(body: TestIn, access: GuildAccess = Depends(guild_access(1, module="automod")),
                     db: AsyncSession = Depends(get_db)) -> dict:
    if body.rule is not None:
        rules = [{**_parse_rule(body.rule).model_dump(), "id": None}]
    else:
        rules = [_rule_json(r) for r in (await db.scalars(select(AutomodRule).where(
            AutomodRule.guild_id == access.guild_id, AutomodRule.enabled.is_(True)))).all()]
    static = [r for r in rules if r["rule_type"] not in ("spam", "duplicates")]
    hit = check_message(static, MessageInfo(body.text))
    if not hit:
        return {"match": None}
    rule, m = hit
    return {"match": {"rule_id": rule.get("id"), "rule_name": rule["name"], "reason": m.reason, "detail": m.detail,
                      "actions": rule["actions"]}}


@router.get("/automod/events")
async def automod_events(access: GuildAccess = Depends(guild_access(1, module="automod")),
                         db: AsyncSession = Depends(get_db), limit: int = Query(50, ge=1, le=100)) -> dict:
    rows = (await db.execute(select(AutomodEvent, AutomodRule.name).outerjoin(
        AutomodRule, AutomodRule.id == AutomodEvent.rule_id).where(AutomodEvent.guild_id == access.guild_id)
        .order_by(AutomodEvent.id.desc()).limit(limit))).all()
    return {"data": [{"id": str(e.id), "rule": name, "user_id": str(e.user_id), "channel_id": str(e.channel_id),
                      "action": e.action_taken, "test_mode": e.test_mode, "excerpt": e.excerpt,
                      "created_at": e.created_at.isoformat()} for e, name in rows]}


# --- Permisos del dashboard por rol -------------------------------------------

PERMISSION_MODULES = ["*", "settings"] + [m.key for m in REGISTRY.values() if m.available]


class PermRow(BaseModel):
    role_id: str
    module: str
    level: Literal[1, 2, 3]


class PermsIn(BaseModel):
    rows: list[PermRow] = Field(max_length=500)


@router.get("/permissions")
async def get_permissions(request: Request, access: GuildAccess = Depends(guild_access(3, managers_only=True)),
                          db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.scalars(select(DashboardRolePermission).where(
        DashboardRolePermission.guild_id == access.guild_id))).all()
    roles = await G.guild_roles(request, access.guild_id)
    return {
        "rows": [{"role_id": str(r.role_id), "module": r.module, "level": r.level} for r in rows],
        "modules": PERMISSION_MODULES,
        "roles": sorted([{"id": str(r["id"]), "name": r["name"], "color": r.get("color", 0),
                          "position": r.get("position", 0)} for r in roles
                         if str(r["id"]) != str(access.guild_id) and not r.get("managed")],
                        key=lambda r: -r["position"]),
    }


@router.put("/permissions", dependencies=[write_limit])
async def put_permissions(body: PermsIn, request: Request,
                          access: GuildAccess = Depends(guild_access(3, managers_only=True)),
                          db: AsyncSession = Depends(get_db)) -> dict:
    roles = {str(r["id"]) for r in await G.guild_roles(request, access.guild_id)}
    clean: dict[tuple[int, str], int] = {}
    for r in body.rows:
        if r.module not in PERMISSION_MODULES or r.role_id not in roles or r.role_id == str(access.guild_id):
            raise ApiError(400, "validation_error", fields={"rows": "invalid_role_or_module"})
        clean[(int(r.role_id), r.module)] = r.level
    old = {f"{x.role_id}:{x.module}": x.level for x in (await db.scalars(select(DashboardRolePermission).where(
        DashboardRolePermission.guild_id == access.guild_id))).all()}
    await db.execute(delete(DashboardRolePermission).where(DashboardRolePermission.guild_id == access.guild_id))
    for (role_id, module), level in clean.items():
        db.add(DashboardRolePermission(guild_id=access.guild_id, role_id=role_id, module=module, level=level))
    new = {f"{k[0]}:{k[1]}": v for k, v in clean.items()}
    changes = diff_changes(old, new)
    if changes:
        await add_audit(db, guild_id=access.guild_id, action="permissions.update", source="dashboard",
                        actor_id=access.auth.user.id, changes=changes)
    await db.commit()
    return {"rows": [{"role_id": str(k[0]), "module": k[1], "level": v} for k, v in clean.items()]}
