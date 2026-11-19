"""Protocolo de sincronización API → Redis → bot (docs/NEXUS_API_SPEC.md §7)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from redis.asyncio import Redis

SYNC_CHANNEL = "nexus:sync"
HEARTBEAT_KEY = "nexus:bot:heartbeat"
HEARTBEAT_TTL = 30

EventType = Literal[
    "module.updated", "module.toggled", "settings.updated", "guild.reload", "commands.sync"
]


def user_guilds_key(user_id: int) -> str:
    return f"nexus:user_guilds:{user_id}"


def guild_channels_key(guild_id: int) -> str:
    return f"nexus:guild:{guild_id}:channels"


def guild_roles_key(guild_id: int) -> str:
    return f"nexus:guild:{guild_id}:roles"


def guild_member_key(guild_id: int, user_id: int) -> str:
    return f"nexus:guild:{guild_id}:member:{user_id}"


def guild_alerts_key(guild_id: int) -> str:
    return f"nexus:guild:{guild_id}:alerts"


def make_event(type_: EventType, guild_id: int, *, module: str | None = None,
               version: int | None = None) -> dict[str, Any]:
    return {
        "type": type_,
        "guild_id": str(guild_id),
        "module": module,
        "version": version,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }


async def publish(redis: Redis, type_: EventType, guild_id: int, *, module: str | None = None,
                  version: int | None = None) -> None:
    event = make_event(type_, guild_id, module=module, version=version)
    await redis.publish(SYNC_CHANNEL, json.dumps(event))


def parse_event(raw: str | bytes) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
        data["guild_id"] = int(data["guild_id"])
        return data
    except (ValueError, KeyError, TypeError):
        return None
