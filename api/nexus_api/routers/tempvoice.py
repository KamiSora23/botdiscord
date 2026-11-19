"""Salas de voz temporales: crear la categoría y el canal «➕ Crear sala» (lo hace el bot por RPC)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.repo import add_audit
from nexus_core.sync import guild_channels_key

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.routers.roles import rpc

router = APIRouter(prefix="/guilds/{guild_id}/tempvoice", tags=["tempvoice"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])


@router.post("/setup", dependencies=[Depends(rate_limit("write", 30, per="guild"))])
async def setup_hub(request: Request, access: GuildAccess = Depends(guild_access(3, module="tempvoice")),
                    db: AsyncSession = Depends(get_db)) -> dict:
    res = await rpc(request, "tempvoice.setup", {"guild_id": access.guild_id})
    await request.app.state.redis.delete(guild_channels_key(access.guild_id))  # que el panel vea lo recién creado
    await add_audit(db, guild_id=access.guild_id, action="tempvoice.hub_created", source="dashboard",
                    actor_id=access.auth.user.id, module="tempvoice",
                    changes={"hub_channel_id": {"old": None, "new": res.get("hub_channel_id")}})
    await db.commit()
    return res
