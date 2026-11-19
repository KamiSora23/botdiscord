"""Dependencias comunes: base de datos, Redis, sesión, CSRF, rate limits y acceso a servidores."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.config import get_settings
from nexus_core.db import sessionmaker
from nexus_core.db.models import Guild, User, UserSession
from nexus_core.db.repo import utcnow
from nexus_core.discord.permissions import can_manage_guild

from nexus_api.errors import ApiError

SESSION_COOKIE = "nexus_session"
CSRF_COOKIE = "nexus_csrf"
CSRF_HEADER = "x-csrf-token"
SESSION_LIFETIME = timedelta(days=30)
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def get_db() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as session:
        yield session


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass
class Auth:
    user: User
    session: UserSession


async def current_auth(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Auth:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise ApiError(401, "unauthenticated")
    now = utcnow()
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.token_hash == hash_token(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        )
    ).first()
    if row is None:
        raise ApiError(401, "unauthenticated")
    sess, user = row
    request.state.locale = user.locale
    # Sesión deslizante: como mucho una escritura por minuto.
    if (now - sess.last_seen_at) > timedelta(minutes=1):
        sess.last_seen_at = now
        if sess.expires_at - now < SESSION_LIFETIME / 2:
            sess.expires_at = now + SESSION_LIFETIME
        await db.commit()
    return Auth(user=user, session=sess)


async def require_csrf(request: Request) -> None:
    if request.method not in UNSAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise ApiError(403, "csrf_failed")


def client_ip(request: Request) -> str:
    """IP del visitante. Con TRUST_CLOUDFLARE=true se usa CF-Connecting-IP
    (Cloudflare la sobrescribe en su borde, el cliente no puede falsearla)."""
    if get_settings().trust_cloudflare:
        cf = request.headers.get("cf-connecting-ip")
        if cf:
            return cf.strip()[:64]
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, limit: int, window: int = 60, *, per: str = "session"):
    """Ventana fija en Redis. ``per``: session | ip | guild."""

    async def _dep(request: Request) -> None:
        if per == "ip":
            key = client_ip(request)
        elif per == "guild":
            key = request.path_params.get("guild_id", "none")
        else:
            cookie = request.cookies.get(SESSION_COOKIE)
            if cookie:
                key = hash_token(cookie).hex()[:16]
            else:
                key = client_ip(request)
        redis: Redis = request.app.state.redis
        rkey = f"nexus:ratelimit:{scope}:{key}"
        try:
            count = await redis.incr(rkey)
            if count == 1:
                await redis.expire(rkey, window)
        except Exception:  # Redis caído: no bloquear la API por el rate limit
            return
        if count > limit:
            ttl = await redis.ttl(rkey)
            raise ApiError(429, "rate_limited", retry_after=max(ttl, 1))

    return _dep


@dataclass
class GuildAccess:
    auth: Auth
    guild_id: int
    level: int  # 1 ver, 2 editar, 3 administrar
    guild: Guild | None
    discord_guild: dict


async def module_levels(request: Request, db: AsyncSession, guild_id: int, user_id: int) -> dict[str, int]:
    """Nivel por roles de este usuario en cada sección del panel ({módulo: 1..3}, «*» = todas)."""
    from sqlalchemy import func

    from nexus_core.db.models import DashboardRolePermission
    from nexus_api.services.guild_data import member_role_ids

    try:
        roles = await member_role_ids(request, guild_id, user_id)
    except Exception:
        return {}
    if not roles:
        return {}
    rows = (await db.execute(select(DashboardRolePermission.module, func.max(DashboardRolePermission.level))
                             .where(DashboardRolePermission.guild_id == guild_id,
                                    DashboardRolePermission.role_id.in_(roles))
                             .group_by(DashboardRolePermission.module))).all()
    return {m: int(lv) for m, lv in rows}


async def role_level(request: Request, db: AsyncSession, guild_id: int, user_id: int,
                     module: str | tuple[str, ...] | None) -> int:
    """Nivel por roles del dashboard (fase 3): el más alto entre el módulo concreto y '*'.

    ``module`` puede ser varios módulos: vale el más alto de ellos (p. ej. imágenes, que usan muchas secciones).
    """
    from sqlalchemy import func

    from nexus_core.db.models import DashboardRolePermission

    has_rows = await db.scalar(select(func.count()).select_from(DashboardRolePermission)
                               .where(DashboardRolePermission.guild_id == guild_id))
    if not has_rows:
        return 0
    from nexus_api.services.guild_data import member_role_ids

    try:
        roles = await member_role_ids(request, guild_id, user_id)
    except Exception:
        return 0
    if not roles:
        return 0
    base = select(func.max(DashboardRolePermission.level)).where(
        DashboardRolePermission.guild_id == guild_id, DashboardRolePermission.role_id.in_(roles))
    if module:
        mods = [module] if isinstance(module, str) else list(module)
        level = await db.scalar(base.where(DashboardRolePermission.module.in_(["*", *mods])))
        return int(level or 0)
    # Páginas generales (Overview, canales, roles): cualquier permiso da lectura; más solo con '*'.
    star = await db.scalar(base.where(DashboardRolePermission.module == "*"))
    anything = await db.scalar(base)
    return max(int(star or 0), 1 if anything else 0)


def guild_access(min_level: int = 1, *, require_bot: bool = True, module: str | tuple[str, ...] | None = None,
                 managers_only: bool = False):
    """``module``: módulo para los permisos por rol; si no se da, se usa el de la URL (/modules/{module})."""
    from nexus_api.services.discord_user import get_user_guilds  # evita import circular

    async def _dep(
        guild_id: str,
        request: Request,
        auth: Auth = Depends(current_auth),
        db: AsyncSession = Depends(get_db),
    ) -> GuildAccess:
        if not guild_id.isdigit() or not 17 <= len(guild_id) <= 20:
            raise ApiError(404, "guild_not_found")
        gid = int(guild_id)
        guilds = await get_user_guilds(request, db, auth.user)
        dg = next((g for g in guilds if int(g["id"]) == gid), None)
        if dg is None:
            raise ApiError(404, "guild_not_found")
        level = 3 if can_manage_guild(int(dg.get("permissions", 0)), is_owner=dg.get("owner", False)) else 0
        if level == 0 and not managers_only:
            level = await role_level(request, db, gid, auth.user.id,
                                     module or request.path_params.get("module"))
        if level < min_level:
            if level == 0:
                raise ApiError(404, "guild_not_found")
            raise ApiError(403, "forbidden", required_level=min_level)
        guild = await db.get(Guild, gid)
        if require_bot and (guild is None or not guild.bot_present):
            from nexus_api.services.guild_data import invite_url_for

            raise ApiError(409, "bot_not_in_guild", invite_url=invite_url_for(gid))
        return GuildAccess(auth=auth, guild_id=gid, level=level, guild=guild, discord_guild=dg)

    return _dep
