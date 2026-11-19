"""Pruebas de la API contra nexus_test (docs/NEXUS_API_SPEC.md §11)."""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from nexus_core.db.models import Guild, GuildAuditLog, GuildConfig, User, UserSession
from nexus_core.db.repo import upsert_guild, utcnow
from nexus_core.discord.permissions import ADMINISTRATOR, SEND_MESSAGES
from nexus_core.sync import SYNC_CHANNEL, user_guilds_key

from nexus_api.deps import hash_token

USER = 111111111111111111
MANAGED = 222222222222222222  # el usuario es administrador, el bot está dentro
NO_BOT = 333333333333333333  # el usuario es administrador, el bot NO está
MEMBER_ONLY = 444444444444444444  # el usuario es miembro normal
FOREIGN = 555555555555555555  # el usuario no está


@pytest.fixture
async def session_token(app, db):
    await db.execute(delete(Guild).where(Guild.id.in_([MANAGED, NO_BOT, MEMBER_ONLY])))
    await db.execute(delete(User).where(User.id == USER))
    await db.commit()
    token = secrets.token_urlsafe(32)
    db.add(User(id=USER, username="tester", locale="es"))
    await db.flush()
    db.add(UserSession(user_id=USER, token_hash=hash_token(token), expires_at=utcnow() + timedelta(days=1)))
    await upsert_guild(db, guild_id=MANAGED, name="Managed", icon=None, owner_id=USER, bot_present=True)
    await upsert_guild(db, guild_id=MEMBER_ONLY, name="Member", icon=None, owner_id=1, bot_present=True)
    await db.commit()
    await app.state.redis.set(user_guilds_key(USER), json.dumps([
        {"id": str(MANAGED), "name": "Managed", "icon": None, "owner": False, "permissions": str(ADMINISTRATOR)},
        {"id": str(NO_BOT), "name": "No bot", "icon": None, "owner": False, "permissions": str(ADMINISTRATOR)},
        {"id": str(MEMBER_ONLY), "name": "Member", "icon": None, "owner": False, "permissions": str(SEND_MESSAGES)},
    ]), ex=300)
    return token


def auth(token: str, csrf: str | None = "csrf123") -> dict:
    cookies = {"nexus_session": token}
    headers = {}
    if csrf:
        cookies["nexus_csrf"] = csrf
        headers["X-CSRF-Token"] = csrf
    return {"cookies": cookies, "headers": headers}


async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


async def test_requires_session(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


async def test_session_token_is_stored_hashed(client, db, session_token):
    rows = (await db.scalars(select(UserSession.token_hash).where(UserSession.user_id == USER))).all()
    assert rows and all(h != session_token.encode() for h in rows)
    client.cookies.clear()
    r = await client.get("/api/v1/auth/me", cookies={"nexus_session": session_token})
    assert r.status_code == 200 and r.json()["id"] == str(USER)


async def test_guild_list_only_manageable(client, session_token):
    r = await client.get("/api/v1/guilds", **auth(session_token, None))
    ids = [g["id"] for g in r.json()["data"]]
    assert ids == [str(MANAGED), str(NO_BOT)]  # con bot primero; sin el servidor donde solo es miembro
    no_bot = r.json()["data"][1]
    assert no_bot["bot_present"] is False and "guild_id=" + str(NO_BOT) in no_bot["invite_url"]


@pytest.mark.parametrize("guild_id", [FOREIGN, MEMBER_ONLY, "abc"])
async def test_cannot_read_other_guilds(client, session_token, guild_id):
    r = await client.get(f"/api/v1/guilds/{guild_id}/settings", **auth(session_token, None))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "guild_not_found"


async def test_bot_not_in_guild(client, session_token):
    r = await client.get(f"/api/v1/guilds/{NO_BOT}/settings", **auth(session_token, None))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "bot_not_in_guild"
    assert r.json()["error"]["invite_url"]


async def test_write_requires_csrf(client, session_token):
    body = {"locale": "en", "timezone": "UTC", "embed_color": 1, "version": 1}
    r = await client.put(f"/api/v1/guilds/{MANAGED}/settings", json=body, cookies={"nexus_session": session_token})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


async def test_settings_save_conflict_audit_and_sync(app, client, db, session_token):
    pubsub = app.state.redis.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(SYNC_CHANNEL)

    current = (await client.get(f"/api/v1/guilds/{MANAGED}/settings", **auth(session_token, None))).json()["data"]
    body = {"locale": "en", "timezone": "Europe/Madrid", "embed_color": 0x22C55E, "version": current["version"]}
    r = await client.put(f"/api/v1/guilds/{MANAGED}/settings", json=body, **auth(session_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["version"] == current["version"] + 1

    # Mismo cuerpo (versión vieja) → conflicto, como dos admins editando a la vez.
    r = await client.put(f"/api/v1/guilds/{MANAGED}/settings", json=body, **auth(session_token))
    assert r.status_code == 409
    assert r.json()["error"]["current_version"] == current["version"] + 1

    db.expire_all()
    cfg = await db.get(GuildConfig, MANAGED)
    assert cfg.locale == "en" and cfg.timezone == "Europe/Madrid"
    audit = (await db.scalars(select(GuildAuditLog).where(GuildAuditLog.guild_id == MANAGED,
                                                          GuildAuditLog.action == "settings.update"))).all()
    assert audit and set(audit[-1].changes) == {"locale", "timezone", "embed_color"}

    msg = None
    for _ in range(20):
        msg = await pubsub.get_message(timeout=0.1)
        if msg:
            break
        await asyncio.sleep(0.05)
    await pubsub.aclose()
    assert msg is not None
    event = json.loads(msg["data"])
    assert event["type"] == "settings.updated" and event["guild_id"] == str(MANAGED)


async def test_validation_errors_have_fields(client, session_token):
    body = {"locale": "fr", "timezone": "Mars/Base", "embed_color": -1, "version": 1}
    r = await client.put(f"/api/v1/guilds/{MANAGED}/settings", json=body, **auth(session_token))
    assert r.status_code == 400
    fields = r.json()["error"]["fields"]
    assert {"locale", "timezone", "embed_color"} <= set(fields)


async def test_login_redirect_rejects_external_next(client):
    r = await client.get("/api/v1/auth/login?next=//evil.example", follow_redirects=False)
    assert r.status_code == 302
    assert "discord.com/oauth2/authorize" in r.headers["location"]
    state, _, encoded = r.cookies.get("nexus_oauth_state", "").partition(".")
    assert state and base64.urlsafe_b64decode(encoded).decode() == "/dashboard"


async def test_callback_rejects_bad_state(client):
    client.cookies.set("nexus_oauth_state", "expected." + base64.urlsafe_b64encode(b"/dashboard").decode())
    r = await client.get("/api/v1/auth/callback?code=x&state=other", follow_redirects=False)
    assert r.status_code == 302
    assert "login_error=state" in r.headers["location"]
