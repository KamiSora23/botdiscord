"""Healthcheck de Docker para el bot: sano si su heartbeat sigue vivo en Redis.

El bot lo renueva cada pocos segundos con caducidad; si el proceso se cuelga o pierde Redis, la clave
desaparece y Docker marca el contenedor como «unhealthy». Uso: ``python -m nexus_bot.healthcheck``.
"""

from __future__ import annotations

import sys

import redis

from nexus_core.config import get_settings
from nexus_core.sync import HEARTBEAT_KEY


def main() -> int:
    try:
        client = redis.Redis.from_url(get_settings().redis_url, socket_timeout=3, protocol=2)
        return 0 if client.exists(HEARTBEAT_KEY) else 1
    except Exception:  # noqa: BLE001 — cualquier fallo = no sano
        return 1


if __name__ == "__main__":
    sys.exit(main())
