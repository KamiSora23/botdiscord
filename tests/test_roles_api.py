from __future__ import annotations

import asyncio
import json
import secrets
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import delete

from nexus_core.db.models import Guild, User, UserSession
from nexus_core.db.repo import upsert_guild, utcnow
from nexus_core.discord.permissions import ADMINISTRATOR
from nexus_core.modules.roles import RolePanelIn
from nexus_core.rpc import RPC_CHANNEL, RpcError, call, reply
from nexus_core.sync import guild_roles_key, user_guilds_key

from nexus_api.deps import hash_token

ADMIN = 151515151515151515
GUILD = 828282828282828282
ROLE_A, ROLE_B = "737373737373737373", "747474747474747474"
ROLE_STAFF = "757575757575757575"

PANEL = {"name": "Intereses", "channel_id": "999999999999999999", "panel_type": "buttons", "mode": "normal",
         "message": {"content": "Elige tus roles"},
         "options": [{"role_id": ROLE_A, "label": "Gaming", "emoji": "🎮"}, {"role_id": ROLE_B, "label": "Arte"}]}


@pytest.fixture
async def admin(app, db):
    await db.execute(delete(Guild).where(Guild.id == GUILD))
    await db.execute(delete(User).where(User.id == ADMIN))
    await db.commit()
    tok = secrets.token_urlsafe(32)
    db.add(User(id=ADMIN, username="admin", locale="es"))
    await db.flush()
    db.add(UserSession(user_id=ADMIN, token_hash=hash_token(tok), expires_at=utcnow() + timedelta(days=1)))
    await upsert_guild(db, guild_id=GUILD, name="Roles", icon=None, owner_id=ADMIN, bot_present=True)
    await db.commit()
    await app.state.redis.set(user_guilds_key(ADMIN), json.dumps([{"id": str(GUILD), "name": "Roles", "icon": None,
                                                                   "owner": True, "permissions": str(ADMINISTRATOR)}]),
                              ex=300)
    roles = [{"id": ROLE_A, "name": "Gaming", "permissions": "0"}, {"id": ROLE_B, "name": "Arte", "permissions": "0"},
             {"id": ROLE_STAFF, "name": "admin", "permissions": str(ADMINISTRATOR)}]
    await app.state.redis.set(guild_roles_key(GUILD), json.dumps(roles), ex=300)
    return tok


def kw(tok: str) -> dict:
    return {"cookies": {"nexus_session": tok, "nexus_csrf": "c"}, "headers": {"X-CSRF-Token": "c"}}


def test_panel_validation():
    p = RolePanelIn.model_validate(PANEL)
    assert len(p.options[0].id) == 8 and p.options[0].id != p.options[1].id
    with pytest.raises(ValidationError, match="duplicate_role"):
        RolePanelIn.model_validate({**PANEL, "options": [PANEL["options"][0], PANEL["options"][0] | {"id": "abcdef12"}]})
    with pytest.raises(ValidationError, match="emoji_required"):
        RolePanelIn.model_validate({**PANEL, "panel_type": "reactions"})
    with pytest.raises(ValidationError, match="invalid_emoji"):
        RolePanelIn.model_validate({**PANEL, "options": [{"role_id": ROLE_A, "label": "x", "emoji": "no es un emoji"}]})


async def test_panel_crud_and_publish_via_rpc(app, client, admin):
    base = f"/api/v1/guilds/{GUILD}/role-panels"
    r = await client.post(base, json=PANEL, **kw(admin))
    assert r.status_code == 201, r.text
    panel = r.json()["data"]

    # Bot simulado: responde a la petición de publicar.
    redis = app.state.redis
    pubsub = redis.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(RPC_CHANNEL)

    async def fake_bot():
        while True:
            msg = await pubsub.get_message(timeout=1.0)
            if msg:
                req = json.loads(msg["data"])
                assert req["method"] == "role_panel.publish"
                await reply(redis, req["id"], result={"message_id": "123"})
                return

    bot = asyncio.create_task(fake_bot())
    r = await client.post(f"{base}/{panel['id']}/publish", **kw(admin))
    await bot
    await pubsub.aclose()
    assert r.status_code == 200, r.text
    assert r.json()["result"] == {"message_id": "123"}

    upd = {**PANEL, "name": "Intereses 2", "version": panel["version"]}
    r = await client.put(f"{base}/{panel['id']}", json=upd, **kw(admin))
    assert r.status_code == 200 and r.json()["data"]["name"] == "Intereses 2"
    assert (await client.delete(f"{base}/{panel['id']}?delete_message=false", **kw(admin))).status_code == 204


async def test_rpc_errors(app):
    subs = dict(await app.state.redis.pubsub_numsub("nexus:rpc"))
    if any(subs.values()):
        pytest.skip("hay un bot real escuchando nexus:rpc")
    with pytest.raises(RpcError, match="bot_offline"):
        await call(app.state.redis, "x", {}, timeout=0.5)  # nadie escucha el canal


async def test_staff_roles_cannot_be_handed_out(client, admin):
    """Un rol con permisos de staff no puede ir en un panel ni en autoroles."""
    bad = {**PANEL, "options": [{"role_id": ROLE_STAFF, "label": "Admin"}]}
    r = await client.post(f"/api/v1/guilds/{GUILD}/role-panels", json=bad, **kw(admin))
    assert r.status_code == 400 and r.json()["error"]["code"] == "dangerous_role"
    r = await client.put(f"/api/v1/guilds/{GUILD}/modules/autoroles",
                         json={"config": {"human_role_ids": [ROLE_STAFF]}, "version": 0}, **kw(admin))
    assert r.status_code == 400 and r.json()["error"]["code"] == "dangerous_role"
    r = await client.put(f"/api/v1/guilds/{GUILD}/modules/autoroles",
                         json={"config": {"human_role_ids": [ROLE_A]}, "version": 0}, **kw(admin))
    assert r.status_code == 200
