from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select

from nexus_core.db.models import Guild, ScheduledJob, User, UserSession
from nexus_core.db.repo import upsert_guild, utcnow
from nexus_core.discord.permissions import ADMINISTRATOR
from nexus_core.modules.community import CustomCommandIn, PollIn
from nexus_core.scheduling import next_run
from nexus_core.sync import user_guilds_key

from nexus_api.deps import hash_token
from nexus_bot.cogs.community import pick_winners

ADMIN = 161616161616161616
GUILD = 838383838383838383
CHANNEL = "848484848484848484"
UTC = timezone.utc


def test_next_run_once_and_repeats():
    after = datetime(2026, 11, 16, 20, 0, tzinfo=UTC)
    assert next_run("2026-11-20T09:00", "UTC", "none", after) == datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    assert next_run("2026-11-01T09:00", "UTC", "none", after) is None
    assert next_run("2026-11-01T09:00", "UTC", "daily", after) == datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
    assert next_run("2026-11-02T09:00", "UTC", "weekly", after) == datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
    assert next_run("2026-01-31T09:00", "UTC", "monthly", after) == datetime(2026, 11, 30, 9, 0, tzinfo=UTC)


def test_daily_keeps_local_hour_across_dst():
    # Madrid cambia de horario el 25 oct 2026: las 9:00 locales pasan de 07:00 a 08:00 UTC.
    before = next_run("2026-10-20T09:00", "Europe/Madrid", "daily", datetime(2026, 10, 21, 0, 0, tzinfo=UTC))
    after = next_run("2026-10-20T09:00", "Europe/Madrid", "daily", datetime(2026, 10, 27, 0, 0, tzinfo=UTC))
    assert before.hour == 7 and after.hour == 8


def test_giveaway_winners_are_reproducible():
    entries = list(range(1, 101))
    a = pick_winners(entries, 3, "semilla")
    assert a == pick_winners(list(reversed(entries)), 3, "semilla")
    assert len(set(a)) == 3
    assert pick_winners([5], 3, "x") == [5]


def test_command_and_poll_validation():
    with pytest.raises(ValidationError, match="reserved_command_name"):
        CustomCommandIn(name="ban", description="x", response={"content": "hola"})
    with pytest.raises(ValidationError, match="invalid_command_name"):
        CustomCommandIn(name="Con Espacios", description="x", response={"content": "hola"})
    assert CustomCommandIn(name="Reglas", description="x", response={"content": "hola"}).name == "reglas"
    with pytest.raises(ValidationError, match="two_answers_required"):
        PollIn(channel_id=CHANNEL, question="¿?", answers=["sí", "  "])


@pytest.fixture
async def admin(app, db):
    await db.execute(delete(Guild).where(Guild.id == GUILD))
    await db.execute(delete(User).where(User.id == ADMIN))
    await db.commit()
    tok = secrets.token_urlsafe(32)
    db.add(User(id=ADMIN, username="admin", locale="es"))
    await db.flush()
    db.add(UserSession(user_id=ADMIN, token_hash=hash_token(tok), expires_at=utcnow() + timedelta(days=1)))
    await upsert_guild(db, guild_id=GUILD, name="Comunidad", icon=None, owner_id=ADMIN, bot_present=True)
    await db.commit()
    await app.state.redis.set(user_guilds_key(ADMIN), json.dumps([{"id": str(GUILD), "name": "C", "icon": None,
                                                                   "owner": True, "permissions": str(ADMINISTRATOR)}]),
                              ex=300)
    return tok


def kw(tok: str) -> dict:
    return {"cookies": {"nexus_session": tok, "nexus_csrf": "c"}, "headers": {"X-CSRF-Token": "c"}}


async def test_custom_commands_api(client, admin):
    base = f"/api/v1/guilds/{GUILD}/custom-commands"
    body = {"name": "reglas", "description": "Muestra las reglas", "response": {"content": "Lee #reglas, {user}"}}
    r = await client.post(base, json=body, **kw(admin))
    assert r.status_code == 201, r.text
    assert (await client.post(base, json=body, **kw(admin))).json()["error"]["fields"]["name"] == "name_taken"
    cmd = r.json()["data"]
    r = await client.put(f"{base}/{cmd['id']}", json={**body, "enabled": False, "version": cmd["version"]}, **kw(admin))
    assert r.status_code == 200 and r.json()["data"]["enabled"] is False
    assert (await client.delete(f"{base}/{cmd['id']}", **kw(admin))).status_code == 204


async def test_scheduled_messages_create_job(client, db, admin):
    base = f"/api/v1/guilds/{GUILD}/scheduled-messages"
    future = (utcnow() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    body = {"name": "Recordatorio", "channel_id": CHANNEL, "message": {"content": "¡Evento hoy!"},
            "local_time": future, "repeat": "daily"}
    r = await client.post(base, json=body, **kw(admin))
    assert r.status_code == 201, r.text
    m = r.json()["data"]
    assert m["next_run_at"]
    jobs = (await db.scalars(select(ScheduledJob).where(ScheduledJob.job_type == "scheduled_message.send",
                                                        ScheduledJob.status == "pending",
                                                        ScheduledJob.guild_id == GUILD))).all()
    assert len(jobs) == 1
    # Pausar cancela la tarea pendiente.
    r = await client.put(f"{base}/{m['id']}", json={**body, "paused": True, "version": m["version"]}, **kw(admin))
    assert r.status_code == 200 and r.json()["data"]["next_run_at"] is None
    db.expire_all()
    pending = (await db.scalars(select(ScheduledJob).where(ScheduledJob.guild_id == GUILD,
                                                           ScheduledJob.status == "pending"))).all()
    assert pending == []
    past = {**body, "local_time": "2020-01-01T09:00", "repeat": "none"}
    r = await client.post(base, json=past, **kw(admin))
    assert r.json()["error"]["fields"]["local_time"] == "in_the_past"


async def test_scheduled_messages_use_browser_timezone(client, db, admin):
    """La hora se interpreta en la zona del navegador que la programa (no en la del servidor)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    base = f"/api/v1/guilds/{GUILD}/scheduled-messages"
    lima = ZoneInfo("America/Lima")
    local = (datetime.now(lima) + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    body = {"name": "Hora Lima", "channel_id": CHANNEL, "message": {"content": "Hola"},
            "local_time": local.strftime("%Y-%m-%dT%H:%M"), "timezone": "America/Lima", "repeat": "none"}
    r = await client.post(base, json=body, **kw(admin))
    assert r.status_code == 201, r.text
    m = r.json()["data"]
    assert m["timezone"] == "America/Lima"
    run = datetime.fromisoformat(m["next_run_at"])
    assert run == local  # 09:00 en Lima = 14:00 UTC, no 09:00 UTC
    # Una hora que ya pasó en Lima se rechaza aunque en otra zona aún no hubiera pasado.
    past = (datetime.now(lima) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
    r = await client.post(base, json={**body, "local_time": past}, **kw(admin))
    assert r.json()["error"]["fields"]["local_time"] == "in_the_past"
    # Zona inválida → error de validación.
    r = await client.post(base, json={**body, "timezone": "Marte/Base"}, **kw(admin))
    assert r.status_code == 400


async def test_voice_activity_stats_and_history(client, db, admin):
    from nexus_core.db.models import ModuleConfig, VoiceSession

    db.add(ModuleConfig(guild_id=GUILD, module="voice_activity", enabled=True, config={}))
    now = utcnow()
    db.add_all([
        VoiceSession(guild_id=GUILD, user_id=111111111111111111, user_name="Ana", channel_id=222222222222222222,
                     channel_name="Juegos", joined_at=now - timedelta(hours=2), left_at=now - timedelta(hours=1),
                     last_seen_at=now - timedelta(hours=1), duration_seconds=3600),
        VoiceSession(guild_id=GUILD, user_id=111111111111111111, user_name="Ana", channel_id=222222222222222222,
                     channel_name="Juegos", joined_at=now - timedelta(minutes=10), last_seen_at=now),  # sigue en voz
        VoiceSession(guild_id=GUILD, user_id=333333333333333333, user_name="Beto", channel_id=444444444444444444,
                     channel_name="Charla", joined_at=now - timedelta(hours=3), left_at=now - timedelta(hours=2, minutes=30),
                     last_seen_at=now, duration_seconds=1800),
    ])
    await db.commit()
    r = await client.get(f"/api/v1/guilds/{GUILD}/voice/stats?days=7", **kw(admin))
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["sessions"] == 3 and s["members"] == 2 and s["in_voice_now"] == 1
    assert s["top_users"][0]["name"] == "Ana" and s["top_users"][0]["seconds"] >= 3600 + 600 - 5
    assert s["top_channels"][0]["name"] == "Juegos"
    r = await client.get(f"/api/v1/guilds/{GUILD}/voice/sessions?user_id=333333333333333333", **kw(admin))
    rows = r.json()["data"]
    assert len(rows) == 1 and rows[0]["seconds"] == 1800 and rows[0]["open"] is False
