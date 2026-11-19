from __future__ import annotations

import json
import secrets
from datetime import timedelta

import pytest
from sqlalchemy import delete

from nexus_core.cases import active_warn_count, create_case
from nexus_core.db.models import Guild, User, UserSession
from nexus_core.db.repo import upsert_guild, utcnow
from nexus_core.discord.permissions import ADMINISTRATOR, SEND_MESSAGES
from nexus_core.sync import guild_member_key, guild_roles_key, user_guilds_key

from nexus_api.deps import hash_token

ADMIN = 131313131313131313
MOD = 141414141414141414
GUILD = 818181818181818181
MOD_ROLE = "727272727272727272"


async def _session(db, uid: int) -> str:
    tok = secrets.token_urlsafe(32)
    db.add(User(id=uid, username=f"u{uid}", locale="es"))
    await db.flush()
    db.add(UserSession(user_id=uid, token_hash=hash_token(tok), expires_at=utcnow() + timedelta(days=1)))
    return tok


@pytest.fixture
async def tokens(app, db):
    await db.execute(delete(Guild).where(Guild.id == GUILD))
    await db.execute(delete(User).where(User.id.in_([ADMIN, MOD])))
    await db.commit()
    admin, mod = await _session(db, ADMIN), await _session(db, MOD)
    await upsert_guild(db, guild_id=GUILD, name="Mod test", icon=None, owner_id=ADMIN, bot_present=True)
    await db.commit()
    r = app.state.redis
    await r.set(user_guilds_key(ADMIN), json.dumps([{"id": str(GUILD), "name": "Mod test", "icon": None, "owner": True,
                                                     "permissions": str(ADMINISTRATOR)}]), ex=300)
    await r.set(user_guilds_key(MOD), json.dumps([{"id": str(GUILD), "name": "Mod test", "icon": None, "owner": False,
                                                   "permissions": str(SEND_MESSAGES)}]), ex=300)
    await r.set(guild_member_key(GUILD, MOD), json.dumps({"roles": [MOD_ROLE]}), ex=300)
    await r.set(guild_roles_key(GUILD), json.dumps([
        {"id": str(GUILD), "name": "@everyone", "permissions": "0", "position": 0},
        {"id": MOD_ROLE, "name": "Moderadores", "permissions": "0", "position": 3}]), ex=300)
    return admin, mod


def kw(tok: str) -> dict:
    return {"cookies": {"nexus_session": tok, "nexus_csrf": "c"}, "headers": {"X-CSRF-Token": "c"}}


RULE = {"name": "Palabrotas", "rule_type": "bad_words", "config": {"words": ["tonto"]},
        "actions": [{"type": "delete"}, {"type": "timeout", "duration_seconds": 600}]}


async def test_rules_crud_and_test(client, tokens):
    admin, _ = tokens
    base = f"/api/v1/guilds/{GUILD}/automod"
    r = await client.post(f"{base}/rules", json=RULE, **kw(admin))
    assert r.status_code == 201, r.text
    rule = r.json()["data"]
    r = await client.post(f"{base}/test", json={"text": "eres TONTO"}, **kw(admin))
    assert r.json()["match"]["rule_name"] == "Palabrotas"
    r = await client.post(f"{base}/test", json={"text": "hola"}, **kw(admin))
    assert r.json()["match"] is None
    upd = {**RULE, "enabled": False, "version": rule["version"]}
    r = await client.put(f"{base}/rules/{rule['id']}", json=upd, **kw(admin))
    assert r.status_code == 200 and r.json()["data"]["enabled"] is False
    r = await client.put(f"{base}/rules/{rule['id']}", json=upd, **kw(admin))
    assert r.status_code == 409
    r = await client.post(f"{base}/rules", json={**RULE, "actions": []}, **kw(admin))
    assert r.status_code == 400
    r = await client.delete(f"{base}/rules/{rule['id']}", **kw(admin))
    assert r.status_code == 204


async def test_cases_numbering_and_warn_count(client, db, tokens):
    admin, _ = tokens
    for _ in range(3):
        await create_case(db, guild_id=GUILD, target_id=999, target_name="malo", action="warn",
                          moderator_id=ADMIN, moderator_name="admin", reason="spam")
    await db.commit()
    assert await active_warn_count(db, GUILD, 999) == 3
    r = await client.get(f"/api/v1/guilds/{GUILD}/moderation/cases?target=malo", **kw(admin))
    assert [c["number"] for c in r.json()["data"]] == [3, 2, 1]
    r = await client.patch(f"/api/v1/guilds/{GUILD}/moderation/cases/2", json={"active": False}, **kw(admin))
    assert r.status_code == 200
    db.expire_all()
    assert await active_warn_count(db, GUILD, 999) == 2


async def test_role_permissions(client, tokens):
    admin, mod = tokens
    # Sin permisos por rol, el moderador no ve el servidor.
    r = await client.get(f"/api/v1/guilds/{GUILD}/moderation/cases", **kw(mod))
    assert r.status_code == 404
    rows = [{"role_id": MOD_ROLE, "module": "moderation", "level": 2}]
    r = await client.put(f"/api/v1/guilds/{GUILD}/permissions", json={"rows": rows}, **kw(admin))
    assert r.status_code == 200, r.text
    assert (await client.get(f"/api/v1/guilds/{GUILD}/moderation/cases", **kw(mod))).status_code == 200
    # Solo moderación: no puede leer otros módulos, ni cambiar permisos, ni la configuración general.
    assert (await client.get(f"/api/v1/guilds/{GUILD}/automod/rules", **kw(mod))).status_code == 404
    assert (await client.get(f"/api/v1/guilds/{GUILD}/permissions", **kw(mod))).status_code == 404
    r = await client.put(f"/api/v1/guilds/{GUILD}/modules/moderation/enabled", json={"enabled": True}, **kw(mod))
    assert r.status_code in (403, 405)
    # El servidor aparece en su lista con acceso por rol.
    data = (await client.get("/api/v1/guilds", **kw(mod))).json()["data"]
    assert data and data[0]["access"] == "role"
    # Un rol inexistente se rechaza.
    bad = [{"role_id": "111111111111111111", "module": "*", "level": 3}]
    assert (await client.put(f"/api/v1/guilds/{GUILD}/permissions", json={"rows": bad}, **kw(admin))).status_code == 400
