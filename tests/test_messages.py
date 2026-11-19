from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from nexus_core.messages import Embed, MessageTemplate, RenderContext, render_payload, unknown_variables
from nexus_core.messages.render import ordinal
from nexus_core.modules import parse_config
from nexus_core.modules.welcome import WelcomeConfig, default_config


def ctx(**kw):
    base = dict(user_id=42, user_name="alex", user_display_name="Alex ✨", user_avatar_url="https://cdn/a.png",
                user_created_at=datetime(2021, 3, 12, tzinfo=timezone.utc), user_joined_at=None,
                server_id=7, server_name="Mi Comunidad", server_icon_url=None, member_count=12841,
                channel_id=99, locale="es", timezone="UTC")
    base.update(kw)
    return RenderContext(**base)


def test_variables_are_substituted_everywhere():
    t = MessageTemplate(content="Hola {user}", embeds=[Embed(
        title="Bienvenido a {server}", description="Eres el {member_count.ordinal} en {channel}",
        thumbnail_url="{user.avatar}", fields=[{"name": "{user.name}", "value": "{user.created_at}"}])])
    p = render_payload(t, ctx(), 0x7465F7)
    assert p["content"] == "Hola <@42>"
    e = p["embeds"][0]
    assert e["title"] == "Bienvenido a Mi Comunidad"
    assert e["description"] == "Eres el 12841.º en <#99>"
    assert e["thumbnail"] == {"url": "https://cdn/a.png"}
    assert e["fields"][0] == {"name": "alex", "value": "12 mar 2021", "inline": False}
    assert e["color"] == 0x7465F7
    assert p["allowed_mentions"] == {"parse": [], "users": ["42"]}


def test_unknown_variables_are_kept_and_reported():
    t = MessageTemplate(content="{user} {nope} {server.owner}")
    assert render_payload(t, ctx(), 0)["content"] == "<@42> {nope} {server.owner}"
    assert unknown_variables(t) == {"nope", "server.owner"}


def test_ordinals():
    assert ordinal(1, "en") == "1st" and ordinal(12, "en") == "12th" and ordinal(23, "en") == "23rd"
    assert ordinal(5, "es") == "5.º"


def test_empty_message_is_rejected():
    with pytest.raises(ValidationError, match="message_empty"):
        MessageTemplate(content="  ")
    with pytest.raises(ValidationError):
        MessageTemplate(embeds=[Embed(url="http://insecure.example")])


def test_embed_total_limit():
    with pytest.raises(ValidationError, match="embed_too_long"):
        MessageTemplate(embeds=[Embed(description="x" * 4096, fields=[{"name": "n", "value": "y" * 1024}] * 3)])


def test_welcome_requires_channel_when_enabled():
    cfg = default_config("es").model_dump(mode="json")
    cfg["join"]["enabled"] = True
    with pytest.raises(ValidationError, match="channel_required"):
        WelcomeConfig.model_validate(cfg)
    cfg["join"]["channel_id"] = "987654321098765432"
    parsed = WelcomeConfig.model_validate(cfg)
    assert parsed.join.channel_id == 987654321098765432
    assert parsed.model_dump(mode="json")["join"]["channel_id"] == "987654321098765432"


def test_defaults_follow_locale():
    assert "Bienvenido" in parse_config("welcome", {}, "es").join.message.embeds[0].title
    assert "Welcome" in parse_config("welcome", {}, "en").join.message.embeds[0].title
