from __future__ import annotations

import json
import secrets
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import delete

from nexus_core import ai
from nexus_core.db.models import Guild, User, UserSession
from nexus_core.db.repo import upsert_guild, utcnow
from nexus_core.discord.permissions import ADMINISTRATOR
from nexus_core.feeds import FeedError, FeedItem, fetch_text, normalize_source, parse_feed
from nexus_core.messages import MessageTemplate, RenderContext, render_payload
from nexus_core.modules.integrations import AIModerationConfig
from nexus_core.sync import user_guilds_key

from nexus_api.deps import hash_token

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Mi blog</title>
<item><title>Post 2</title><link>https://blog.example/2</link><guid>p2</guid></item>
<item><title>Post 1</title><link>https://blog.example/1</link><guid>p1</guid></item></channel></rss>"""

YOUTUBE = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
<title>Canal X</title><entry><id>yt:video:abc</id><title>Vídeo nuevo</title>
<link rel="alternate" href="https://www.youtube.com/watch?v=abc"/><author><name>Canal X</name></author>
<media:group><media:thumbnail url="https://i.ytimg.com/vi/abc/hq.jpg"/></media:group></entry></feed>"""


def test_parse_rss_and_youtube():
    title, items = parse_feed(RSS)
    assert title == "Mi blog" and [i.id for i in items] == ["p2", "p1"]
    title, items = parse_feed(YOUTUBE)
    assert title == "Canal X"
    assert items[0] == FeedItem(id="yt:video:abc", title="Vídeo nuevo", url="https://www.youtube.com/watch?v=abc",
                                author="Canal X", thumbnail="https://i.ytimg.com/vi/abc/hq.jpg")


def test_malicious_xml_is_rejected():
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><rss><channel>&b;</channel></rss>'
    with pytest.raises(FeedError, match="invalid_feed"):
        parse_feed(bomb)


def test_source_validation():
    with pytest.raises(FeedError, match="youtube_channel_id_required"):
        normalize_source("youtube", "https://youtube.com/@alguien")
    with pytest.raises(FeedError, match="invalid_url"):
        normalize_source("rss", "file:///etc/passwd")


async def test_private_addresses_are_blocked():
    async with httpx.AsyncClient() as client:
        for url in ("http://127.0.0.1:8000/api/v1/health", "http://localhost:6379/", "http://10.0.0.5/feed"):
            with pytest.raises(FeedError, match="private_address"):
                await fetch_text(client, url)


def test_integration_variables_render():
    ctx = RenderContext(user_id=1, user_name="bot", user_display_name="NEXUS", user_avatar_url="", user_created_at=None,
                        user_joined_at=None, server_id=2, server_name="S", server_icon_url=None, member_count=3)
    p = render_payload(MessageTemplate(content="{name}: {title} {url}"), ctx, 0,
                       extra={"name": "Canal", "title": "Hola", "url": "https://x.example"})
    assert p["content"] == "Canal: Hola https://x.example"


def test_ai_config_validation():
    cfg = AIModerationConfig()
    assert cfg.categories["scam"] is True and cfg.categories["off_rules"] is False
    with pytest.raises(ValidationError, match="review_gt_action"):
        AIModerationConfig(review_threshold=0.95, action_threshold=0.9)


class FakeMessages:
    def __init__(self, text: str, stop: str = "end_turn"):
        self.text, self.stop, self.kwargs = text, stop, None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.text)],
                               usage=SimpleNamespace(input_tokens=120, output_tokens=30))


async def test_ai_classify_parses_structured_output(monkeypatch):
    fake = FakeMessages(json.dumps({"category": "scam", "score": 0.97, "reason": "Enlace de phishing."}))
    monkeypatch.setattr(ai, "_get_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=fake)))
    v = await ai.classify("Gana Nitro gratis en http://n1tro.example", "No spam.", "es")
    assert (v.category, v.score, v.input_tokens) == ("scam", 0.97, 120)
    sent = fake.kwargs
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in sent["betas"]
    assert "<message>" in sent["messages"][0]["content"] and "No spam." in sent["messages"][0]["content"]


async def test_ai_refusal_and_bad_output(monkeypatch):
    fake = FakeMessages("", stop="refusal")
    monkeypatch.setattr(ai, "_get_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=fake)))
    v = await ai.classify("algo", "", "en")
    assert v.refused and v.category == "none"
    fake2 = FakeMessages(json.dumps({"category": "nonsense", "score": 7}))
    monkeypatch.setattr(ai, "_get_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=fake2)))
    v = await ai.classify("algo", "", "en")
    assert v.category == "none" and v.score == 1.0


ADMIN, GUILD = 181818181818181818, 868686868686868686


@pytest.fixture
async def admin(app, db):
    await db.execute(delete(Guild).where(Guild.id == GUILD))
    await db.execute(delete(User).where(User.id == ADMIN))
    await db.commit()
    tok = secrets.token_urlsafe(32)
    db.add(User(id=ADMIN, username="admin", locale="es"))
    await db.flush()
    db.add(UserSession(user_id=ADMIN, token_hash=hash_token(tok), expires_at=utcnow() + timedelta(days=1)))
    await upsert_guild(db, guild_id=GUILD, name="Int", icon=None, owner_id=ADMIN, bot_present=True)
    await db.commit()
    await app.state.redis.set(user_guilds_key(ADMIN), json.dumps([{"id": str(GUILD), "name": "Int", "icon": None,
                                                                   "owner": True, "permissions": str(ADMINISTRATOR)}]),
                              ex=300)
    return tok


async def test_integration_api(client, admin, monkeypatch):
    from nexus_api.routers import integrations as router_mod

    async def fake_fetch(_client, provider, external_id):
        return "Canal X", [FeedItem(id="1", title="t", url="https://x.example")]

    monkeypatch.setattr(router_mod, "fetch_items", fake_fetch)
    kw = {"cookies": {"nexus_session": admin, "nexus_csrf": "c"}, "headers": {"X-CSRF-Token": "c"}}
    base = f"/api/v1/guilds/{GUILD}/integrations"
    body = {"provider": "youtube", "source": "https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw",
            "channel_id": "878787878787878787", "message": {"content": "{name}: {title}"}}
    r = await client.post(base, json=body, **kw)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["external_id"] == "UC_x5XG1OV2P6uZZ5FSM9Ttw" and r.json()["data"]["display_name"] == "Canal X"
    bad = await client.post(base, json={**body, "source": "https://youtube.com/@x"}, **kw)
    assert bad.json()["error"]["fields"]["source"] == "youtube_channel_id_required"
    status = (await client.get(f"/api/v1/guilds/{GUILD}/ai-moderation/status", **kw)).json()
    assert status["tokens_used"] == 0 and status["token_limit"] == 1_000_000
