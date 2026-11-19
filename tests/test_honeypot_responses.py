import pytest
from pydantic import ValidationError

from nexus_core.discord.permissions import REQUIRED_PERMISSIONS
from nexus_core.modules import REGISTRY, parse_config
from nexus_core.modules.honeypot import is_exempt
from nexus_core.modules.responses import ResponsesConfig, Trigger, matches


def test_honeypot_defaults_are_cautious():
    cfg = parse_config("honeypot", {}, "es")
    assert REGISTRY["honeypot"].available
    assert cfg.action == "timeout" and cfg.timeout_minutes == 60 and cfg.purge_minutes == 60
    assert cfg.message.embeds and "honeypot" in REQUIRED_PERMISSIONS["manage_messages"]


def test_honeypot_who_is_exempt():
    base = dict(is_owner=False, is_staff=False, is_bot=False, role_ids={1}, exempt=[2])
    assert not is_exempt(**base)  # miembro normal: cae en la trampa
    assert is_exempt(**{**base, "is_owner": True})
    assert is_exempt(**{**base, "is_staff": True})
    assert is_exempt(**{**base, "is_bot": True})
    assert is_exempt(**{**base, "role_ids": {1, 2}})  # rol exento


def test_trigger_matching_modes():
    word = Trigger(keywords=["ban"], response="x", match="word")
    assert matches(word, "me dieron BAN") and not matches(word, "banana")
    contains = Trigger(keywords=["ban"], response="x", match="contains")
    assert matches(contains, "banana")
    starts = Trigger(keywords=["!ayuda"], response="x", match="starts")
    assert matches(starts, "!ayuda por favor") and not matches(starts, "necesito !ayuda")
    exact = Trigger(keywords=["hola"], response="x", match="exact")
    assert matches(exact, "Hola") and not matches(exact, "hola a todos")
    accents = Trigger(keywords=["cómo me verifico"], response="x")
    assert matches(accents, "como me verifico??")


def test_responses_validation():
    with pytest.raises(ValidationError, match="duplicate_tag"):
        ResponsesConfig.model_validate({"tags": [{"name": "reglas", "content": "a"}, {"name": "Reglas", "content": "b"}]})
    with pytest.raises(ValidationError):
        ResponsesConfig.model_validate({"tags": [{"name": "con espacios raros!", "content": "a"}]})
    cfg = ResponsesConfig.model_validate({"tags": [{"name": "Preguntas Frecuentes", "content": "x"}]})
    assert cfg.tags[0].name == "preguntas-frecuentes"
    with pytest.raises(ValidationError, match="keywords_required"):
        Trigger(keywords=["  ", ""], response="x")


def test_honeypot_escalation_steps():
    from nexus_core.modules.honeypot import HoneypotConfig, honeypot_default, pick_action

    data = honeypot_default().model_dump(mode="json") | {"action": "timeout", "timeout_minutes": 60, "escalation": [
        {"count": 4, "action": "ban"}, {"count": 3, "action": "timeout", "timeout_minutes": 1440}]}
    cfg = HoneypotConfig.model_validate(data)
    assert [s.count for s in cfg.escalation] == [3, 4]  # se ordenan solos
    assert pick_action(cfg, 1)[:2] == ("timeout", 60)
    assert pick_action(cfg, 2)[:2] == ("timeout", 60)
    assert pick_action(cfg, 3)[:2] == ("timeout", 1440)
    assert pick_action(cfg, 4)[0] == "ban" and pick_action(cfg, 9)[0] == "ban"
    assert cfg.strike_window_days == 30
    with pytest.raises(ValidationError, match="duplicate_step"):
        HoneypotConfig.model_validate(data | {"escalation": [{"count": 3}, {"count": 3}]})
