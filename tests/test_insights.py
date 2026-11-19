from __future__ import annotations

import json
import secrets
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from nexus_core.db.models import Guild, ModuleConfig, User, UserSession
from nexus_core.db.repo import add_daily_stats, upsert_guild, utcnow
from nexus_core.discord.permissions import ADMINISTRATOR
from nexus_core.sync import user_guilds_key

from nexus_api.deps import hash_token

ADMIN, GUILD = 191919191919191919, 888888888888888881
WELCOME_CH, LOG_CH = "898989898989898989", "909090909090909090"


@pytest.fixture
async def admin(app, db):
    await db.execute(delete(Guild).where(Guild.id == GUILD))
    await db.execute(delete(User).where(User.id == ADMIN))
    await db.commit()
    tok = secrets.token_urlsafe(32)
    db.add(User(id=ADMIN, username="admin", locale="es"))
    await db.flush()
    db.add(UserSession(user_id=ADMIN, token_hash=hash_token(tok), expires_at=utcnow() + timedelta(days=1)))
    await upsert_guild(db, guild_id=GUILD, name="Setup", icon=None, owner_id=ADMIN, bot_present=True)
    await db.commit()
    await app.state.redis.set(user_guilds_key(ADMIN), json.dumps([{"id": str(GUILD), "name": "S", "icon": None,
                                                                   "owner": True, "permissions": str(ADMINISTRATOR)}]),
                              ex=300)
    return tok


def kw(tok: str) -> dict:
    return {"cookies": {"nexus_session": tok, "nexus_csrf": "c"}, "headers": {"X-CSRF-Token": "c"}}


async def test_quick_setup_applies_and_respects_existing(client, db, admin):
    body = {"template": "support", "channels": {"welcome": WELCOME_CH, "logs": LOG_CH}}
    r = await client.post(f"/api/v1/guilds/{GUILD}/setup", json=body, **kw(admin))
    assert r.status_code == 200, r.text
    assert {"welcome", "tickets", "logging", "moderation", "suggestions"} <= set(r.json()["applied"])
    welcome = await db.get(ModuleConfig, (GUILD, "welcome"))
    assert welcome.enabled and welcome.config["join"]["channel_id"] == WELCOME_CH and welcome.config["join"]["enabled"]
    logging_cfg = await db.get(ModuleConfig, (GUILD, "logging"))
    assert all(c["channel_id"] == LOG_CH for c in logging_cfg.config["categories"].values())

    # Segunda vez con otro canal: sin overwrite no se toca lo ya configurado.
    r = await client.post(f"/api/v1/guilds/{GUILD}/setup",
                          json={**body, "channels": {"welcome": "919191919191919191"}}, **kw(admin))
    assert "welcome" in r.json()["skipped"]
    db.expire_all()
    assert (await db.get(ModuleConfig, (GUILD, "welcome"))).config["join"]["channel_id"] == WELCOME_CH
    r = await client.post(f"/api/v1/guilds/{GUILD}/setup",
                          json={**body, "channels": {"welcome": "919191919191919191"}, "overwrite": True,
                                "modules": ["welcome"]}, **kw(admin))
    assert r.json()["applied"] == ["welcome"]
    db.expire_all()
    assert (await db.get(ModuleConfig, (GUILD, "welcome"))).config["join"]["channel_id"] == "919191919191919191"
    enabled = (await db.scalars(select(ModuleConfig.module).where(ModuleConfig.guild_id == GUILD,
                                                                  ModuleConfig.enabled.is_(True)))).all()
    assert "tickets" in enabled


async def test_analytics(client, db, admin):
    today = utcnow().date()
    await add_daily_stats(db, GUILD, today, {"members_joined": 10, "members_left": 3, "commands_used": 7})
    await add_daily_stats(db, GUILD, today - timedelta(days=40), {"members_joined": 99})
    await db.commit()
    r = await client.get(f"/api/v1/guilds/{GUILD}/analytics?days=30", **kw(admin))
    data = r.json()
    assert len(data["series"]) == 30
    assert data["totals"]["joined"] == 10 and data["totals"]["net_growth"] == 7 and data["totals"]["commands"] == 7
    assert (await client.get(f"/api/v1/guilds/{GUILD}/analytics?days=12", **kw(admin))).status_code == 400
