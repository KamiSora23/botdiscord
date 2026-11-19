"""Healthcheck de Docker para la API: responde /api/v1/health y la base de datos está bien.

Uso: ``python -m nexus_api.healthcheck``.
"""

from __future__ import annotations

import json
import sys
import urllib.request


def main() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=5) as r:  # noqa: S310
            data = json.load(r)
        return 0 if data.get("api") == "ok" and data.get("database") == "ok" else 1
    except Exception:  # noqa: BLE001 — cualquier fallo = no sano
        return 1


if __name__ == "__main__":
    sys.exit(main())
