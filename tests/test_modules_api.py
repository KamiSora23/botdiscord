from __future__ import annotations

import json
import secrets
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from nexus_core.db.models import Guild, GuildAuditLog, ModuleConfig, User, UserSession
from nexus_core.db.repo import upsert_guild, utcnow
from nexus_core.discord.permissions import ADMINISTRATOR
from nexus_core.sync import user_guilds_key

from nexus_api.deps import hash_token

USER = 121212121212121212
GUILD = 676767676767676767
CHANNEL = "989898989898989898"


@pytest.fixture
async def token(app, db):
    await db.execute(delete(Guild).where(Guild.id == GUILD))
    await db.execute(delete(User).where(User.id == USER))
    await db.commit()
    tok = secrets.token_urlsafe(32)
    db.add(User(id=USER, username="mod", locale="en"))
    await db.flush()
    db.add(UserSession(user_id=USER, token_hash=hash_token(tok), expires_at=utcnow() + timedelta(days=1)))
    await upsert_guild(db, guild_id=GUILD, name="Mods", icon=None, owner_id=USER, bot_present=True)
    await db.commit()
    await app.state.redis.set(user_guilds_key(USER), json.dumps([
        {"id": str(GUILD), "name": "Mods", "icon": None, "owner": True, "permissions": str(ADMINISTRATOR)}]), ex=300)
    return tok


def kw(tok: str) -> dict:
    return {"cookies": {"nexus_session": tok, "nexus_csrf": "c"}, "headers": {"X-CSRF-Token": "c"}}


async def test_defaults_before_first_save(client, token):
    r = await client.get(f"/api/v1/guilds/{GUILD}/modules/welcome", **kw(token))
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["version"] == 0 and d["enabled"] is False
    assert d["config"]["join"]["message"]["embeds"][0]["title"].startswith("¡Bienvenido")  # idioma del servidor, no del usuario


async def test_unavailable_module_is_404(client, token):
    r = await client.get(f"/api/v1/guilds/{GUILD}/modules/does_not_exist", **kw(token))
    assert r.status_code == 404


async def test_save_validate_conflict_toggle(client, db, token):
    base = (await client.get(f"/api/v1/guilds/{GUILD}/modules/welcome", **kw(token))).json()["data"]
    cfg = base["config"]
    cfg["join"]["enabled"] = True  # sin canal → error con ruta del campo
    r = await client.put(f"/api/v1/guilds/{GUILD}/modules/welcome", json={"config": cfg, "version": 0}, **kw(token))
    assert r.status_code == 400
    assert any(k.startswith("config.join") for k in r.json()["error"]["fields"])

    cfg["join"]["channel_id"] = CHANNEL
    r = await client.put(f"/api/v1/guilds/{GUILD}/modules/welcome", json={"config": cfg, "version": 0}, **kw(token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["version"] == 1
    assert r.json()["data"]["config"]["join"]["channel_id"] == CHANNEL

    r = await client.put(f"/api/v1/guilds/{GUILD}/modules/welcome", json={"config": cfg, "version": 0}, **kw(token))
    assert r.status_code == 409

    r = await client.patch(f"/api/v1/guilds/{GUILD}/modules/welcome/enabled", json={"enabled": True}, **kw(token))
    assert r.status_code == 200 and r.json()["version"] == 2

    db.expire_all()
    row = await db.get(ModuleConfig, (GUILD, "welcome"))
    assert row.enabled and row.config["join"]["channel_id"] == CHANNEL
    actions = (await db.scalars(select(GuildAuditLog.action).where(GuildAuditLog.guild_id == GUILD))).all()
    assert "module.update" in actions and "module.enable" in actions

    ov = (await client.get(f"/api/v1/guilds/{GUILD}/overview", **kw(token))).json()
    assert ov["stats"]["modules_enabled"] == 1 and ov["stats"]["modules_total"] >= 1
