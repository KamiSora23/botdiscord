"""Fase 7: integraciones (YouTube, Twitch, RSS, GitHub) e IA de moderación."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.ai import ai_configured
from nexus_core.db.models import AIModerationEvent, AIUsage, GuildConfig, Integration, ModuleConfig
from nexus_core.db.repo import add_audit, utcnow
from nexus_core.feeds import FeedError, fetch_items, normalize_source, twitch_configured
from nexus_core.modules import parse_config
from nexus_core.modules.integrations import AIModerationConfig, IntegrationIn, default_message

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.errors import ApiError
from nexus_api.routers.modules import validation_fields
from nexus_api.routers.roles import rpc

router = APIRouter(prefix="/guilds/{guild_id}", tags=["integrations"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])
write_limit = Depends(rate_limit("write", 20, per="guild"))
MAX_INTEGRATIONS = 25


def _json(i: Integration) -> dict[str, Any]:
    return {"id": str(i.id), "provider": i.provider, "external_id": i.external_id, "display_name": i.display_name,
            "channel_id": str(i.channel_id), "message": i.message, "enabled": i.enabled, "status": i.status,
            "last_error": i.last_error, "version": i.version,
            "last_checked_at": i.last_checked_at.isoformat() if i.last_checked_at else None,
            "last_event_at": i.last_event_at.isoformat() if i.last_event_at else None}


@router.get("/integrations")
async def list_integrations(access: GuildAccess = Depends(guild_access(1, module="integrations")),
                            db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.scalars(select(Integration).where(Integration.guild_id == access.guild_id)
                             .order_by(Integration.id))).all()
    cfg = await db.get(GuildConfig, access.guild_id)
    locale = cfg.locale if cfg else "es"
    return {"data": [_json(i) for i in rows], "can_edit": access.level >= 2,
            "twitch_available": twitch_configured(),
            "defaults": {p: default_message(p, locale).model_dump(mode="json")
                         for p in ("youtube", "twitch", "rss", "github")}}


async def _validated(body: dict[str, Any]) -> tuple[IntegrationIn, str, str]:
    try:
        data = IntegrationIn.model_validate(body)
    except ValidationError as exc:
        raise ApiError(400, "validation_error", fields=validation_fields(exc)) from exc
    try:
        external_id = normalize_source(data.provider, data.source)
        async with httpx.AsyncClient() as client:
            name, _ = await fetch_items(client, data.provider, external_id)
    except FeedError as exc:
        raise ApiError(400, "validation_error", fields={"source": exc.code}) from exc
    except httpx.HTTPError as exc:
        raise ApiError(400, "validation_error", fields={"source": "unreachable"}) from exc
    return data, external_id, (name or external_id)[:100]


@router.post("/integrations", status_code=201, dependencies=[write_limit])
async def create_integration(body: dict[str, Any], access: GuildAccess = Depends(guild_access(2, module="integrations")),
                             db: AsyncSession = Depends(get_db)) -> dict:
    if await db.scalar(select(func.count()).select_from(Integration).where(Integration.guild_id == access.guild_id)) \
            >= MAX_INTEGRATIONS:
        raise ApiError(400, "validation_error", fields={"_": "too_many_integrations"})
    data, external_id, name = await _validated(body)
    i = Integration(guild_id=access.guild_id, provider=data.provider, external_id=external_id, display_name=name,
                    channel_id=data.channel_id, message=data.message.model_dump(mode="json"), enabled=data.enabled)
    db.add(i)
    await db.flush()
    await add_audit(db, guild_id=access.guild_id, action="integration.create", source="dashboard",
                    actor_id=access.auth.user.id, module="integrations",
                    changes={"integration": {"old": None, "new": f"{data.provider}:{external_id}"}})
    await db.commit()
    return {"data": _json(i)}


@router.put("/integrations/{integration_id}", dependencies=[write_limit])
async def update_integration(integration_id: int, body: dict[str, Any],
                             access: GuildAccess = Depends(guild_access(2, module="integrations")),
                             db: AsyncSession = Depends(get_db)) -> dict:
    i = await db.get(Integration, integration_id)
    if i is None or i.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    if body.pop("version", None) != i.version:
        raise ApiError(409, "version_conflict", current_version=i.version)
    data, external_id, name = await _validated(body)
    if (data.provider, external_id) != (i.provider, i.external_id):
        i.initialized = False  # fuente nueva: no avisar de lo ya publicado
    i.provider, i.external_id, i.display_name = data.provider, external_id, name
    i.channel_id, i.message, i.enabled = data.channel_id, data.message.model_dump(mode="json"), data.enabled
    i.version += 1
    await db.commit()
    return {"data": _json(i)}


@router.delete("/integrations/{integration_id}", status_code=204, dependencies=[write_limit])
async def delete_integration(integration_id: int, access: GuildAccess = Depends(guild_access(3, module="integrations")),
                             db: AsyncSession = Depends(get_db)) -> Response:
    i = await db.get(Integration, integration_id)
    if i is None or i.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    await db.delete(i)
    await db.commit()
    return Response(status_code=204)


@router.post("/integrations/{integration_id}/test", dependencies=[Depends(rate_limit("integration_test", 5, per="guild"))])
async def test_integration(integration_id: int, request: Request,
                           access: GuildAccess = Depends(guild_access(2, module="integrations"))) -> dict:
    return await rpc(request, "integrations.test", {"guild_id": access.guild_id, "id": integration_id})


# --- IA de moderación ----------------------------------------------------------

def _month() -> str:
    return utcnow().strftime("%Y-%m")


@router.get("/ai-moderation/status")
async def ai_status(access: GuildAccess = Depends(guild_access(1, module="ai_moderation")),
                    db: AsyncSession = Depends(get_db)) -> dict:
    usage = await db.get(AIUsage, (access.guild_id, _month()))
    row = await db.get(ModuleConfig, (access.guild_id, "ai_moderation"))
    cfg: AIModerationConfig = parse_config("ai_moderation", row.config if row else {})  # type: ignore[assignment]
    pending = await db.scalar(select(func.count()).select_from(AIModerationEvent).where(
        AIModerationEvent.guild_id == access.guild_id, AIModerationEvent.review_status == "pending"))
    used = (usage.input_tokens + usage.output_tokens) if usage else 0
    return {"configured": ai_configured(), "month": _month(), "tokens_used": used,
            "token_limit": cfg.monthly_token_limit, "requests": usage.requests if usage else 0,
            "pending_reviews": pending}


@router.get("/ai-moderation/events")
async def ai_events(access: GuildAccess = Depends(guild_access(1, module="ai_moderation")),
                    db: AsyncSession = Depends(get_db), status: Literal["all", "pending"] = "all",
                    limit: int = Query(50, ge=1, le=100)) -> dict:
    q = select(AIModerationEvent).where(AIModerationEvent.guild_id == access.guild_id)
    if status == "pending":
        q = q.where(AIModerationEvent.review_status == "pending")
    rows = (await db.scalars(q.order_by(AIModerationEvent.id.desc()).limit(limit))).all()
    return {"data": [{
        "id": str(e.id), "user": {"id": str(e.user_id), "name": e.user_name}, "category": e.category,
        "score": round(e.score, 2), "reason": e.reason, "action": e.action, "review_status": e.review_status,
        "jump_url": f"https://discord.com/channels/{e.guild_id}/{e.channel_id}/{e.message_id}",
        "created_at": e.created_at.isoformat(),
    } for e in rows], "can_edit": access.level >= 2}


class ReviewIn(BaseModel):
    decision: Literal["confirm", "dismiss"]
    punishment: Literal["none", "warn", "timeout"] = "none"


@router.post("/ai-moderation/events/{event_id}/review", dependencies=[write_limit])
async def review_event(event_id: int, body: ReviewIn, request: Request,
                       access: GuildAccess = Depends(guild_access(2, module="ai_moderation")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    e = await db.get(AIModerationEvent, event_id)
    if e is None or e.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    case = None
    if body.decision == "confirm" and body.punishment != "none":
        res = await rpc(request, "mod.action", {
            "guild_id": access.guild_id, "user_id": e.user_id, "moderator_id": access.auth.user.id,
            "action": body.punishment, "reason": f"IA: {e.category} ({e.reason or ''})"[:300],
            "duration": 600 if body.punishment == "timeout" else None})
        case = res.get("case")
    e.review_status = "confirmed" if body.decision == "confirm" else "dismissed"
    e.reviewed_by = access.auth.user.id
    await db.commit()
    return {"review_status": e.review_status, "case": case}

