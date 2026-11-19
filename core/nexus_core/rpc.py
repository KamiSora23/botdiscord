"""Peticiones API → bot por Redis (publicar paneles, moderar desde el panel…).

La API publica la petición en ``nexus:rpc`` y espera la respuesta en ``nexus:rpc:result:{id}``.
Así toda la lógica que usa Discord (jerarquía de roles, vistas persistentes, casos) vive solo en el bot.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from redis.asyncio import Redis

RPC_CHANNEL = "nexus:rpc"
RESULT_TTL = 60


def result_key(request_id: str) -> str:
    return f"nexus:rpc:result:{request_id}"


class RpcError(Exception):
    def __init__(self, code: str, **extra: Any):
        super().__init__(code)
        self.code = code
        self.extra = extra


async def call(redis: Redis, method: str, params: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    rid = uuid.uuid4().hex
    receivers = await redis.publish(RPC_CHANNEL, json.dumps({"id": rid, "method": method, "params": params}))
    if not receivers:
        raise RpcError("bot_offline")
    key = result_key(rid)
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        raw = await redis.get(key)
        if raw:
            await redis.delete(key)
            data = json.loads(raw)
            if data.get("error"):
                raise RpcError(data["error"], **data.get("extra", {}))
            return data.get("result") or {}
        await asyncio.sleep(0.1)
    raise RpcError("bot_timeout")


async def reply(redis: Redis, request_id: str, *, result: dict[str, Any] | None = None,
                error: str | None = None, extra: dict[str, Any] | None = None) -> None:
    payload = {"result": result} if error is None else {"error": error, "extra": extra or {}}
    await redis.set(result_key(request_id), json.dumps(payload), ex=RESULT_TTL)
