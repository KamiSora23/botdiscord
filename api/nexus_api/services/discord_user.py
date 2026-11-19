"""Tokens OAuth del usuario y su lista de servidores (con caché de 60 s)."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core import crypto
from nexus_core.config import get_settings
from nexus_core.db.models import OAuthAccount, User, UserSession
from nexus_core.db.repo import utcnow
from nexus_core.discord.rest import DiscordError, DiscordREST
from nexus_core.sync import user_guilds_key

from nexus_api.errors import ApiError

USER_GUILDS_TTL = 60
REFRESH_MARGIN = timedelta(days=1)


def rest(request: Request) -> DiscordREST:
    return request.app.state.discord


async def store_tokens(db: AsyncSession, user_id: int, token: dict[str, Any]) -> None:
    acc = await db.get(OAuthAccount, user_id)
    values = dict(
        access_token_enc=crypto.encrypt(token["access_token"]),
        refresh_token_enc=crypto.encrypt(token["refresh_token"]),
        scopes=str(token.get("scope", "")).split(),
        expires_at=utcnow() + timedelta(seconds=int(token.get("expires_in", 604800))),
        updated_at=utcnow(),
    )
    if acc is None:
        db.add(OAuthAccount(user_id=user_id, **values))
    else:
        for k, v in values.items():
            setattr(acc, k, v)


async def _revoke_all(db: AsyncSession, user_id: int) -> None:
    from sqlalchemy import update

    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await db.commit()


async def access_token(request: Request, db: AsyncSession, user: User) -> str:
    acc = await db.get(OAuthAccount, user.id)
    if acc is None:
        raise ApiError(401, "reauth_required")
    if acc.expires_at - utcnow() > REFRESH_MARGIN:
        return crypto.decrypt(acc.access_token_enc)
    s = get_settings()
    try:
        token = await rest(request).refresh_token(
            client_id=s.discord_client_id,
            client_secret=s.discord_client_secret,
            refresh_token=crypto.decrypt(acc.refresh_token_enc),
        )
    except DiscordError as exc:
        if exc.status in (400, 401):
            await _revoke_all(db, user.id)
            raise ApiError(401, "reauth_required") from exc
        raise
    await store_tokens(db, user.id, token)
    await db.commit()
    return token["access_token"]


async def get_user_guilds(request: Request, db: AsyncSession, user: User,
                          *, fresh: bool = False) -> list[dict[str, Any]]:
    redis = request.app.state.redis
    key = user_guilds_key(user.id)
    if not fresh:
        try:
            cached = await redis.get(key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
    token = await access_token(request, db, user)
    try:
        guilds = await rest(request).request("GET", "/users/@me/guilds", bearer=token)
    except DiscordError as exc:
        if exc.status == 401:
            await _revoke_all(db, user.id)
            raise ApiError(401, "reauth_required") from exc
        raise
    slim = [
        {"id": g["id"], "name": g["name"], "icon": g.get("icon"), "owner": g.get("owner", False),
         "permissions": g.get("permissions", "0")}
        for g in guilds
    ]
    try:
        await redis.set(key, json.dumps(slim), ex=USER_GUILDS_TTL)
    except Exception:
        pass
    return slim
