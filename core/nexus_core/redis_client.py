from __future__ import annotations

from redis.asyncio import Redis

from nexus_core.config import get_settings


def make_redis(**kw: object) -> Redis:
    """Cliente Redis compartido. protocol=2 (RESP2): el Redis 5 de Laragon no soporta RESP3."""
    opts: dict[str, object] = {
        "decode_responses": True,
        "protocol": 2,
        "socket_connect_timeout": 2,
        "health_check_interval": 30,
    }
    opts.update(kw)
    return Redis.from_url(get_settings().redis_url, **opts)  # type: ignore[arg-type]
