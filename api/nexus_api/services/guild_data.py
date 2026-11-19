"""Datos de un servidor leídos con el token del bot (canales, roles, permisos) y estado del bot."""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import Request

from nexus_core.config import get_settings
from nexus_core.discord import permissions as P
from nexus_core.sync import (
    HEARTBEAT_KEY,
    guild_alerts_key,
    guild_channels_key,
    guild_member_key,
    guild_roles_key,
)

CACHE_TTL = 60

# Tipos de canal de Discord que se muestran en los selectores.
CHANNEL_TYPES = {0: "text", 2: "voice", 4: "category", 5: "announcement", 15: "forum"}


def invite_url_for(guild_id: int | None = None) -> str | None:
    client_id = get_settings().discord_client_id
    return P.invite_url(client_id, guild_id) if client_id else None


def bot_user_id() -> int | None:
    """El ID del bot va codificado en la primera parte del token."""
    token = get_settings().discord_bot_token
    if not token:
        return None
    first = token.split(".")[0]
    try:
        return int(base64.b64decode(first + "=" * (-len(first) % 4)).decode())
    except (ValueError, UnicodeDecodeError):
        return None


async def _cached(request: Request, key: str, path: str) -> Any:
    redis = request.app.state.redis
    try:
        hit = await redis.get(key)
        if hit:
            return json.loads(hit)
    except Exception:
        pass
    data = await request.app.state.discord.request("GET", path)
    try:
        await redis.set(key, json.dumps(data), ex=CACHE_TTL)
    except Exception:
        pass
    return data


async def guild_roles(request: Request, guild_id: int) -> list[dict[str, Any]]:
    return await _cached(request, guild_roles_key(guild_id), f"/guilds/{guild_id}/roles")


async def reject_dangerous_roles(request: Request, guild_id: int, role_ids: list[int | str], field: str) -> None:
    """Error 400 si algún rol tiene permisos de staff (no se puede repartir automáticamente)."""
    from nexus_api.errors import ApiError

    wanted = {str(r) for r in role_ids}
    if not wanted:
        return
    try:
        roles = await guild_roles(request, guild_id)
    except Exception:  # Discord no responde: el bot vuelve a comprobarlo al repartir el rol
        return
    bad = [r["name"] for r in roles if r["id"] in wanted and P.is_dangerous(int(r["permissions"]))]
    if bad:
        raise ApiError(400, "dangerous_role", fields={field: "dangerous_role"}, roles=bad)


async def guild_channels_raw(request: Request, guild_id: int) -> list[dict[str, Any]]:
    return await _cached(request, guild_channels_key(guild_id), f"/guilds/{guild_id}/channels")


async def bot_member(request: Request, guild_id: int) -> dict[str, Any] | None:
    bot_id = bot_user_id()
    if bot_id is None:
        return None
    return await _cached(request, guild_member_key(guild_id, bot_id),
                         f"/guilds/{guild_id}/members/{bot_id}")


async def member_role_ids(request: Request, guild_id: int, user_id: int) -> set[int]:
    try:
        member = await _cached(request, guild_member_key(guild_id, user_id), f"/guilds/{guild_id}/members/{user_id}")
    except Exception:
        return set()
    return {int(r) for r in (member or {}).get("roles", [])}


async def bot_base_permissions(request: Request, guild_id: int, owner_id: int) -> tuple[int, list[int]]:
    roles = await guild_roles(request, guild_id)
    member = await bot_member(request, guild_id)
    role_ids = [int(r) for r in (member or {}).get("roles", [])]
    perms = P.base_permissions(
        guild_id=guild_id, owner_id=owner_id, member_id=bot_user_id() or 0,
        member_role_ids=role_ids, roles={int(r["id"]): int(r["permissions"]) for r in roles},
    )
    return perms, role_ids


async def channels_with_bot_perms(request: Request, guild_id: int, owner_id: int) -> list[dict[str, Any]]:
    raw = await guild_channels_raw(request, guild_id)
    base, role_ids = await bot_base_permissions(request, guild_id, owner_id)
    bot_id = bot_user_id() or 0
    out = []
    for ch in raw:
        ctype = CHANNEL_TYPES.get(int(ch["type"]))
        if ctype is None:
            continue
        perms = P.channel_permissions(
            base, guild_id=guild_id, member_id=bot_id, member_role_ids=role_ids,
            overwrites=ch.get("permission_overwrites", []),
        )
        out.append({
            "id": str(ch["id"]),
            "name": ch["name"],
            "type": ctype,
            "parent_id": str(ch["parent_id"]) if ch.get("parent_id") else None,
            "position": ch.get("position", 0),
            "bot_can_view": P.has(perms, P.VIEW_CHANNEL),
            "bot_can_send": P.has(perms, P.VIEW_CHANNEL | P.SEND_MESSAGES),
            "bot_can_embed": P.has(perms, P.VIEW_CHANNEL | P.SEND_MESSAGES | P.EMBED_LINKS),
        })
    out.sort(key=lambda c: (c["type"] == "category", c["position"]))
    return out


async def bot_status(request: Request) -> dict[str, Any]:
    try:
        raw = await request.app.state.redis.get(HEARTBEAT_KEY)
    except Exception:
        raw = None
    if not raw:
        return {"online": False, "latency_ms": None, "last_heartbeat": None, "intents": {}}
    data = json.loads(raw)
    return {
        "online": True,
        "latency_ms": data.get("latency_ms"),
        "last_heartbeat": data.get("at"),
        "intents": data.get("intents", {}),
    }


async def guild_alerts(request: Request, guild_id: int) -> list[dict[str, Any]]:
    try:
        raw = await request.app.state.redis.lrange(guild_alerts_key(guild_id), 0, 19)
    except Exception:
        return []
    return [json.loads(x) for x in raw]


def missing_permissions(base: int) -> list[dict[str, Any]]:
    out = []
    for name, modules in P.REQUIRED_PERMISSIONS.items():
        granted = P.has(base, P.NAMES[name])
        out.append({"permission": name, "granted": granted, "required_by": modules})
    return out
