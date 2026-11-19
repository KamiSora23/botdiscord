"""Anti-raid: publicar el panel de verificación y crear el rol de cuarentena (los ejecuta el bot por RPC)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.repo import add_audit
from nexus_core.sync import guild_channels_key, guild_roles_key

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.routers.roles import rpc

router = APIRouter(prefix="/guilds/{guild_id}/antiraid", tags=["antiraid"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])
write_limit = Depends(rate_limit("write", 30, per="guild"))


@router.post("/verification/publish", dependencies=[write_limit])
async def publish_verification(request: Request, access: GuildAccess = Depends(guild_access(2, module="antiraid")),
                               db: AsyncSession = Depends(get_db)) -> dict:
    res = await rpc(request, "antiraid.publish", {"guild_id": access.guild_id})
    await add_audit(db, guild_id=access.guild_id, action="antiraid.verification_published", source="dashboard",
                    actor_id=access.auth.user.id, module="antiraid")
    await db.commit()
    return res


@router.post("/quarantine-role", dependencies=[write_limit])
async def create_quarantine_role(request: Request,
                                 access: GuildAccess = Depends(guild_access(3, module="antiraid")),
                                 db: AsyncSession = Depends(get_db)) -> dict:
    res = await rpc(request, "antiraid.quarantine_role", {"guild_id": access.guild_id})
    await request.app.state.redis.delete(guild_roles_key(access.guild_id))  # que el panel vea lo recién creado
    await add_audit(db, guild_id=access.guild_id, action="antiraid.quarantine_role_created", source="dashboard",
                    actor_id=access.auth.user.id, module="antiraid",
                    changes={"role_id": {"old": None, "new": res.get("role_id")}})
    await db.commit()
    return res


class GateIn(BaseModel):
    action: Literal["apply", "undo"]


@router.post("/gate", dependencies=[write_limit])
async def channel_gate(body: GateIn, request: Request,
                       access: GuildAccess = Depends(guild_access(3, module="antiraid")),
                       db: AsyncSession = Depends(get_db)) -> dict:
    """Restringe (o deja como estaban) los canales que ven los miembros sin verificar."""
    res = await rpc(request, "antiraid.gate", {"guild_id": access.guild_id, "action": body.action}, timeout=90)
    await request.app.state.redis.delete(guild_channels_key(access.guild_id))
    await add_audit(db, guild_id=access.guild_id, action=f"antiraid.gate_{body.action}", source="dashboard",
                    actor_id=access.auth.user.id, module="antiraid",
                    changes={"channels": {"old": None, "new": res.get("changed")}})
    await db.commit()
    return res


# --- Canal trampa (honeypot) ---------------------------------------------------------

honeypot_router = APIRouter(prefix="/guilds/{guild_id}/honeypot", tags=["honeypot"],
                            dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])


@honeypot_router.post("/setup", dependencies=[write_limit])
async def honeypot_setup(request: Request, access: GuildAccess = Depends(guild_access(3, module="honeypot")),
                         db: AsyncSession = Depends(get_db)) -> dict:
    """Crea el canal trampa, publica el aviso y lo guarda en la configuración."""
    res = await rpc(request, "honeypot.setup", {"guild_id": access.guild_id})
    await request.app.state.redis.delete(guild_channels_key(access.guild_id))
    await add_audit(db, guild_id=access.guild_id, action="honeypot.channel_created", source="dashboard",
                    actor_id=access.auth.user.id, module="honeypot",
                    changes={"channel_id": {"old": None, "new": res.get("channel_id")}})
    await db.commit()
    return res


@honeypot_router.post("/publish", dependencies=[write_limit])
async def honeypot_publish(request: Request, access: GuildAccess = Depends(guild_access(2, module="honeypot")),
                           db: AsyncSession = Depends(get_db)) -> dict:
    res = await rpc(request, "honeypot.publish", {"guild_id": access.guild_id})
    await add_audit(db, guild_id=access.guild_id, action="honeypot.published", source="dashboard",
                    actor_id=access.auth.user.id, module="honeypot")
    await db.commit()
    return res
