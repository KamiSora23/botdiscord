"""Login con Discord OAuth2 (docs/NEXUS_API_SPEC.md §3, §6.1)."""

from __future__ import annotations

import base64
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.config import get_settings
from nexus_core.db.models import User, UserSession
from nexus_core.db.repo import utcnow
from nexus_core.discord.rest import DiscordError, avatar_url
from nexus_core.i18n import normalize
from nexus_core.sync import user_guilds_key

from nexus_api.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    SESSION_LIFETIME,
    Auth,
    client_ip,
    current_auth,
    get_db,
    hash_token,
    new_token,
    rate_limit,
    require_csrf,
)
from nexus_api.errors import ApiError
from nexus_api.services.discord_user import store_tokens

router = APIRouter(prefix="/auth", tags=["auth"])

STATE_COOKIE = "nexus_oauth_state"
SCOPES = "identify guilds"


def _safe_next(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/dashboard"
    return value


def _cookie_opts() -> dict:
    return {"secure": get_settings().is_production, "samesite": "lax", "path": "/"}


def user_json(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "global_name": user.global_name,
        "avatar_url": avatar_url(user.id, user.avatar),
        "locale": user.locale,
        "timezone": user.timezone,
    }


@router.get("/login", dependencies=[Depends(rate_limit("auth", 20, per="ip"))])
async def login(next: str | None = None) -> Response:
    s = get_settings()
    if not s.discord_client_id or not s.discord_client_secret:
        raise ApiError(503, "discord_not_configured")
    state = secrets.token_urlsafe(24)
    params = urlencode({
        "client_id": s.discord_client_id,
        "redirect_uri": s.discord_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "prompt": "none",
    })
    resp = RedirectResponse(f"https://discord.com/oauth2/authorize?{params}", status_code=302)
    # La ruta va en base64 para que la cookie no necesite comillas (las "/" no son válidas sin ellas).
    encoded_next = base64.urlsafe_b64encode(_safe_next(next).encode()).decode()
    resp.set_cookie(STATE_COOKIE, f"{state}.{encoded_next}", max_age=600, httponly=True,
                    **_cookie_opts())
    return resp


@router.get("/callback", dependencies=[Depends(rate_limit("auth", 20, per="ip"))])
async def callback(request: Request, code: str | None = None, state: str | None = None,
                   error: str | None = None, db: AsyncSession = Depends(get_db)) -> Response:
    s = get_settings()
    stored = request.cookies.get(STATE_COOKIE, "")
    expected, _, encoded_next = stored.partition(".")
    try:
        next_path = base64.urlsafe_b64decode(encoded_next.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        next_path = "/dashboard"
    if error or not code or not state or not expected or not secrets.compare_digest(state, expected):
        resp = RedirectResponse(f"{s.dashboard_url}/?login_error={'denied' if error else 'state'}",
                                status_code=302)
        resp.delete_cookie(STATE_COOKIE, path="/")
        return resp

    rest = request.app.state.discord
    try:
        token = await rest.exchange_code(client_id=s.discord_client_id,
                                         client_secret=s.discord_client_secret,
                                         code=code, redirect_uri=s.discord_redirect_uri)
        me = await rest.request("GET", "/users/@me", bearer=token["access_token"])
    except DiscordError:
        return RedirectResponse(f"{s.dashboard_url}/?login_error=discord", status_code=302)

    uid = int(me["id"])
    now = utcnow()
    user = await db.get(User, uid)
    if user is None:
        user = User(id=uid, username=me["username"], locale=normalize(me.get("locale")))
        db.add(user)
    user.username = me["username"]
    user.global_name = me.get("global_name")
    user.avatar = me.get("avatar")
    user.last_login_at = now
    user.updated_at = now
    await db.flush()
    await store_tokens(db, uid, token)

    session_token = new_token()
    db.add(UserSession(
        user_id=uid,
        token_hash=hash_token(session_token),
        expires_at=now + SESSION_LIFETIME,
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
    ))
    await db.commit()
    try:
        await request.app.state.redis.delete(user_guilds_key(uid))
    except Exception:
        pass

    resp = RedirectResponse(f"{s.dashboard_url}{_safe_next(next_path)}", status_code=302)
    max_age = int(SESSION_LIFETIME.total_seconds())
    resp.set_cookie(SESSION_COOKIE, session_token, max_age=max_age, httponly=True, **_cookie_opts())
    resp.set_cookie(CSRF_COOKIE, new_token(), max_age=max_age, httponly=False, **_cookie_opts())
    resp.delete_cookie(STATE_COOKIE, path="/")
    return resp


@router.post("/logout", dependencies=[Depends(require_csrf)])
async def logout(auth: Auth = Depends(current_auth), db: AsyncSession = Depends(get_db)) -> Response:
    sess = await db.get(UserSession, auth.session.id)
    if sess is not None:
        sess.revoked_at = utcnow()
        await db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp


@router.get("/me")
async def me(auth: Auth = Depends(current_auth)) -> dict:
    return user_json(auth.user)


@router.get("/csrf")
async def csrf(request: Request, auth: Auth = Depends(current_auth)) -> Response:
    """Garantiza que exista la cookie CSRF para una sesión válida."""
    resp = Response(status_code=204)
    if not request.cookies.get(CSRF_COOKIE):
        resp.set_cookie(CSRF_COOKIE, new_token(), max_age=int(SESSION_LIFETIME.total_seconds()),
                        httponly=False, **_cookie_opts())
    return resp
