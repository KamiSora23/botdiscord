"""Fase 6: ranking de niveles, tienda y monederos."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.models import EconomyItem, EconomyTransaction, MemberWallet, MemberXP, ModuleConfig
from nexus_core.db.repo import add_audit
from nexus_core.discord.rest import avatar_url
from nexus_core.economy import EconomyError, change_balance
from nexus_core.modules import parse_config
from nexus_core.modules.progression import BalanceAdjustIn, EconomyConfig, ItemIn, level_from_xp

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.errors import ApiError
from nexus_api.routers.modules import validation_fields

router = APIRouter(prefix="/guilds/{guild_id}", tags=["progression"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])
write_limit = Depends(rate_limit("write", 30, per="guild"))


def _validate(model: type[BaseModel], body: dict[str, Any]) -> Any:
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        raise ApiError(400, "validation_error", fields=validation_fields(exc)) from exc


@router.get("/levels/leaderboard")
async def leaderboard(access: GuildAccess = Depends(guild_access(1, module="levels")),
                      db: AsyncSession = Depends(get_db), limit: int = Query(50, ge=1, le=100),
                      offset: int = Query(0, ge=0)) -> dict:
    rows = (await db.scalars(select(MemberXP).where(MemberXP.guild_id == access.guild_id)
                             .order_by(MemberXP.xp.desc()).offset(offset).limit(limit))).all()
    total = await db.scalar(select(func.count()).select_from(MemberXP).where(MemberXP.guild_id == access.guild_id))
    out = []
    for i, m in enumerate(rows):
        level, into, need = level_from_xp(m.xp)
        out.append({"rank": offset + i + 1, "user_id": str(m.user_id), "name": m.user_name or str(m.user_id),
                    "avatar_url": avatar_url(m.user_id, m.avatar), "xp": m.xp, "level": level, "progress": into,
                    "needed": need, "messages": m.message_count})
    return {"data": out, "total": total}


@router.delete("/levels/members/{user_id}", status_code=204, dependencies=[write_limit])
async def reset_xp(user_id: int, access: GuildAccess = Depends(guild_access(3, module="levels")),
                   db: AsyncSession = Depends(get_db)) -> Response:
    await db.execute(delete(MemberXP).where(MemberXP.guild_id == access.guild_id, MemberXP.user_id == user_id))
    await add_audit(db, guild_id=access.guild_id, action="levels.reset_member", source="dashboard",
                    actor_id=access.auth.user.id, module="levels", changes={"user": {"old": str(user_id), "new": None}})
    await db.commit()
    return Response(status_code=204)


# --- Economía ----------------------------------------------------------------

def _item_json(i: EconomyItem) -> dict[str, Any]:
    return {"id": str(i.id), "name": i.name, "description": i.description, "price": i.price, "stock": i.stock,
            "role_id": str(i.role_id) if i.role_id else None, "enabled": i.enabled}


@router.get("/economy/items")
async def list_items(access: GuildAccess = Depends(guild_access(1, module="economy")),
                     db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.scalars(select(EconomyItem).where(EconomyItem.guild_id == access.guild_id)
                             .order_by(EconomyItem.price))).all()
    return {"data": [_item_json(i) for i in rows], "can_edit": access.level >= 2}


def _item_values(body: dict[str, Any]) -> dict[str, Any]:
    d = _validate(ItemIn, body).model_dump(mode="json")
    d["role_id"] = int(d["role_id"]) if d["role_id"] else None
    return d


@router.post("/economy/items", status_code=201, dependencies=[write_limit])
async def create_item(body: dict[str, Any], access: GuildAccess = Depends(guild_access(2, module="economy")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    if await db.scalar(select(func.count()).select_from(EconomyItem).where(EconomyItem.guild_id == access.guild_id)) >= 50:
        raise ApiError(400, "validation_error", fields={"_": "too_many_items"})
    item = EconomyItem(guild_id=access.guild_id, **_item_values(body))
    db.add(item)
    await db.flush()
    await add_audit(db, guild_id=access.guild_id, action="economy.item_create", source="dashboard",
                    actor_id=access.auth.user.id, module="economy", changes={"item": {"old": None, "new": item.name}})
    await db.commit()
    return {"data": _item_json(item)}


@router.put("/economy/items/{item_id}", dependencies=[write_limit])
async def update_item(item_id: int, body: dict[str, Any], access: GuildAccess = Depends(guild_access(2, module="economy")),
                      db: AsyncSession = Depends(get_db)) -> dict:
    item = await db.get(EconomyItem, item_id)
    if item is None or item.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    for k, v in _item_values(body).items():
        setattr(item, k, v)
    await db.commit()
    return {"data": _item_json(item)}


@router.delete("/economy/items/{item_id}", status_code=204, dependencies=[write_limit])
async def delete_item(item_id: int, access: GuildAccess = Depends(guild_access(3, module="economy")),
                      db: AsyncSession = Depends(get_db)) -> Response:
    item = await db.get(EconomyItem, item_id)
    if item is None or item.guild_id != access.guild_id:
        raise ApiError(404, "not_found")
    await db.delete(item)
    await db.commit()
    return Response(status_code=204)


@router.get("/economy/wallets")
async def wallets(access: GuildAccess = Depends(guild_access(1, module="economy")), db: AsyncSession = Depends(get_db),
                  limit: int = Query(50, ge=1, le=100)) -> dict:
    rows = (await db.scalars(select(MemberWallet).where(MemberWallet.guild_id == access.guild_id)
                             .order_by(MemberWallet.balance.desc()).limit(limit))).all()
    total = await db.scalar(select(func.coalesce(func.sum(MemberWallet.balance), 0)).where(
        MemberWallet.guild_id == access.guild_id))
    return {"data": [{"user_id": str(w.user_id), "name": w.user_name or str(w.user_id), "balance": w.balance}
                     for w in rows], "total_supply": int(total or 0)}


@router.get("/economy/transactions")
async def transactions(access: GuildAccess = Depends(guild_access(1, module="economy")),
                       db: AsyncSession = Depends(get_db), user_id: int | None = None,
                       limit: int = Query(50, ge=1, le=100)) -> dict:
    q = select(EconomyTransaction).where(EconomyTransaction.guild_id == access.guild_id)
    if user_id:
        q = q.where(EconomyTransaction.user_id == user_id)
    rows = (await db.scalars(q.order_by(EconomyTransaction.id.desc()).limit(limit))).all()
    return {"data": [{"id": str(x.id), "user_id": str(x.user_id), "amount": x.amount, "kind": x.kind,
                      "reference": x.reference, "created_at": x.created_at.isoformat()} for x in rows]}


@router.post("/economy/wallets/{user_id}", dependencies=[write_limit])
async def adjust_balance(user_id: int, body: dict[str, Any],
                         access: GuildAccess = Depends(guild_access(3, module="economy")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    data: BalanceAdjustIn = _validate(BalanceAdjustIn, body)
    row = await db.get(ModuleConfig, (access.guild_id, "economy"))
    cfg: EconomyConfig = parse_config("economy", row.config if row else {})  # type: ignore[assignment]
    try:
        balance = await change_balance(db, access.guild_id, user_id, data.amount, "admin",
                                       reference=(data.reason or "")[:200] or None, max_balance=cfg.max_balance,
                                       start_balance=cfg.start_balance, clamp=True)
    except EconomyError as exc:
        raise ApiError(400, "validation_error", fields={"amount": exc.code}) from exc
    await add_audit(db, guild_id=access.guild_id, action="economy.adjust", source="dashboard",
                    actor_id=access.auth.user.id, module="economy",
                    changes={f"user_{user_id}": {"old": None, "new": data.amount}})
    await db.commit()
    return {"balance": balance}
