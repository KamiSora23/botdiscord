"""Las pruebas usan la base de datos nexus_test y Redis db 15, nunca los datos reales."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_env = (ROOT / ".env").read_text(encoding="utf-8")
_db = re.search(r"^DATABASE_URL=(.+)$", _env, re.M)
assert _db, "DATABASE_URL no está en .env"
os.environ["DATABASE_URL"] = _db.group(1).strip().rsplit("/", 1)[0] + "/nexus_test"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/15"
os.environ.setdefault("DISCORD_CLIENT_ID", "1234567890123456789")
os.environ.setdefault("DISCORD_CLIENT_SECRET", "test")
os.environ.setdefault("DISCORD_BOT_TOKEN", "")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True,
               capture_output=True, env=os.environ.copy())


@pytest.fixture(scope="session")
async def app():
    from nexus_api.main import app as fastapi_app

    async with fastapi_app.router.lifespan_context(fastapi_app):
        await fastapi_app.state.redis.flushdb()
        yield fastapi_app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def db():
    from nexus_core.db import sessionmaker

    async with sessionmaker()() as session:
        yield session
