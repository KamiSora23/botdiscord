"""Aplicación FastAPI de NEXUS BOT. Arranque: uvicorn nexus_api.main:app --reload"""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from sqlalchemy import text

from nexus_core.config import get_settings
from nexus_core.db import dispose_engine, get_engine
from nexus_core.discord.rest import DiscordREST
from nexus_core.logsetup import request_id_var, setup_logging
from nexus_core.redis_client import make_redis

from nexus_api.errors import install_error_handlers
from nexus_api.routers import (
    antiraid,
    auth,
    community,
    events,
    guilds,
    insights,
    integrations,
    me,
    media,
    moderation,
    modules,
    progression,
    roles,
    tempvoice,
    voice,
)
from nexus_api.services.guild_data import bot_status, invite_url_for

setup_logging()

MAX_BODY = 64 * 1024
MAX_UPLOAD = 11 * 1024 * 1024  # subida de imágenes (8 MB, o 10 MB por envío, + cabeceras multipart)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    s.check_production()
    get_engine()
    app.state.redis = make_redis(socket_timeout=2)
    app.state.discord = DiscordREST(s.discord_bot_token or None)
    yield
    await app.state.discord.aclose()
    await app.state.redis.aclose()
    await dispose_engine()


# La documentación interactiva solo en desarrollo: en producción no se publica la lista de endpoints.
_docs = not get_settings().is_production
app = FastAPI(title="NEXUS BOT API", version="0.1.0", lifespan=lifespan,
              docs_url="/api/docs" if _docs else None, openapi_url="/api/openapi.json" if _docs else None,
              redoc_url=None)
install_error_handlers(app)


@app.middleware("http")
async def security(request: Request, call_next):  # type: ignore[no-untyped-def]
    length = request.headers.get("content-length")
    uploads = request.method == "POST" and request.url.path.endswith(("/media", "/embeds/send"))
    limit = MAX_UPLOAD if uploads else MAX_BODY
    if length and length.isdigit() and int(length) > limit:
        from fastapi.responses import JSONResponse

        from nexus_api.errors import error_body

        return JSONResponse(error_body(request, "validation_error", {"_": "body_too_large"}),
                            status_code=413)
    rid = request.headers.get("x-request-id") or ""
    if not (rid.isalnum() and len(rid) <= 64):
        rid = secrets.token_hex(8)
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = rid
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


PREFIX = "/api/v1"
app.include_router(auth.router, prefix=PREFIX)
app.include_router(me.router, prefix=PREFIX)
app.include_router(guilds.router, prefix=PREFIX)
app.include_router(modules.router, prefix=PREFIX)
app.include_router(modules.tools, prefix=PREFIX)
app.include_router(moderation.router, prefix=PREFIX)
app.include_router(roles.router, prefix=PREFIX)
app.include_router(community.router, prefix=PREFIX)
app.include_router(progression.router, prefix=PREFIX)
app.include_router(integrations.router, prefix=PREFIX)
app.include_router(insights.router, prefix=PREFIX)
app.include_router(antiraid.router, prefix=PREFIX)
app.include_router(antiraid.honeypot_router, prefix=PREFIX)
app.include_router(tempvoice.router, prefix=PREFIX)
app.include_router(voice.router, prefix=PREFIX)
app.include_router(events.router, prefix=PREFIX)
app.include_router(media.router, prefix=PREFIX)


@app.get(f"{PREFIX}/invite", tags=["health"])
async def invite() -> dict:
    """Enlace de invitación general (página de inicio)."""
    return {"invite_url": invite_url_for(None)}


@app.get(f"{PREFIX}/health", tags=["health"])
async def health(request: Request) -> dict:
    out = {"api": "ok", "database": "ok", "redis": "ok", "bot": "offline",
           "discord_configured": get_settings().discord_configured}
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("select 1"))
    except Exception:
        out["database"] = "error"
    try:
        await request.app.state.redis.ping()
        out["bot"] = "online" if (await bot_status(request))["online"] else "offline"
    except Exception:
        logging.getLogger("nexus.api").exception("Redis no disponible")
        out["redis"] = "error"
    return out
