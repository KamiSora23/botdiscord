from __future__ import annotations

import json
import secrets
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select

from nexus_core.db.models import EconomyTransaction, Guild, MemberWallet, User, UserSession
from nexus_core.db.repo import upsert_guild, utcnow
from nexus_core.discord.permissions import ADMINISTRATOR
from nexus_core.economy import EconomyError, change_balance, transfer
from nexus_core.modules.progression import LevelsConfig, level_from_xp, total_xp_for, xp_for_next
from nexus_core.sync import user_guilds_key

from nexus_api.deps import hash_token

ADMIN = 171717171717171717
GUILD = 858585858585858585


def test_xp_curve():
    assert xp_for_next(0) == 100 and xp_for_next(1) == 155
    assert level_from_xp(99) == (0, 99, 100)
    assert level_from_xp(total_xp_for(5)) == (5, 0, xp_for_next(5))


def test_levels_config_validation():
    with pytest.raises(ValidationError, match="xp_min_gt_max"):
        LevelsConfig(xp_min=30, xp_max=10)
    with pytest.raises(ValidationError, match="channel_required"):
        LevelsConfig(announce="channel")
    cfg = LevelsConfig(rewards=[{"level": 10, "role_id": "111111111111111111"}, {"level": 5, "role_id": "222222222222222222"}])
    assert [r.level for r in cfg.rewards] == [5, 10]


@pytest.fixture
async def guild(app, db):
    await db.execute(delete(Guild).where(Guild.id == GUILD))
    await db.execute(delete(User).where(User.id == ADMIN))
    await db.commit()
    tok = secrets.token_urlsafe(32)
    db.add(User(id=ADMIN, username="admin", locale="es"))
    await db.flush()
    db.add(UserSession(user_id=ADMIN, token_hash=hash_token(tok), expires_at=utcnow() + timedelta(days=1)))
    await upsert_guild(db, guild_id=GUILD, name="Eco", icon=None, owner_id=ADMIN, bot_present=True)
    await db.commit()
    await app.state.redis.set(user_guilds_key(ADMIN), json.dumps([{"id": str(GUILD), "name": "Eco", "icon": None,
                                                                   "owner": True, "permissions": str(ADMINISTRATOR)}]),
                              ex=300)
    return tok


async def test_balances_never_go_negative(db, guild):
    await change_balance(db, GUILD, 1, 100, "daily")
    with pytest.raises(EconomyError, match="insufficient_funds"):
        await change_balance(db, GUILD, 1, -500, "buy")
    assert await change_balance(db, GUILD, 1, -500, "admin", clamp=True) == 0
    await db.commit()


async def test_transfer(db, guild):
    await change_balance(db, GUILD, 10, 300, "daily")
    left = await transfer(db, GUILD, 10, 20, 120, max_balance=10_000)
    await db.commit()
    assert left == 180
    assert (await db.get(MemberWallet, (GUILD, 20))).balance == 120
    with pytest.raises(EconomyError, match="self_transfer"):
        await transfer(db, GUILD, 10, 10, 5, max_balance=10_000)
    with pytest.raises(EconomyError, match="insufficient_funds"):
        await transfer(db, GUILD, 20, 10, 9999, max_balance=10_000)
    await db.rollback()
    kinds = (await db.scalars(select(EconomyTransaction.kind).where(EconomyTransaction.guild_id == GUILD))).all()
    assert {"transfer_in", "transfer_out"} <= set(kinds)


def kw(tok: str) -> dict:
    return {"cookies": {"nexus_session": tok, "nexus_csrf": "c"}, "headers": {"X-CSRF-Token": "c"}}


async def test_economy_api(client, db, guild):
    base = f"/api/v1/guilds/{GUILD}/economy"
    r = await client.post(f"{base}/items", json={"name": "Rol VIP", "price": 500, "stock": 3}, **kw(guild))
    assert r.status_code == 201, r.text
    assert (await client.get(f"{base}/items", **kw(guild))).json()["data"][0]["name"] == "Rol VIP"
    r = await client.post(f"{base}/wallets/42", json={"amount": 250, "reason": "premio"}, **kw(guild))
    assert r.json()["balance"] == 250
    r = await client.post(f"{base}/wallets/42", json={"amount": -1000}, **kw(guild))
    assert r.json()["balance"] == 0  # se ajusta a 0, nunca negativo
    assert (await client.post(f"{base}/wallets/42", json={"amount": 0}, **kw(guild))).status_code == 400
    count = await db.scalar(select(func.count()).select_from(EconomyTransaction).where(
        EconomyTransaction.guild_id == GUILD, EconomyTransaction.user_id == 42))
    assert count == 2
