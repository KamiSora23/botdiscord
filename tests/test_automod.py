import pytest
from pydantic import ValidationError

from nexus_core.automod import MessageInfo, RateTracker, check_message, check_static
from nexus_core.modules.moderation import AutomodRuleIn, LoggingConfig, ModerationConfig, channel_for


def rule(rt, cfg=None, **kw):
    r = AutomodRuleIn(name=rt, rule_type=rt, config=cfg or {}, actions=[{"type": "delete"}], **kw)
    d = r.model_dump()
    d["exempt_role_ids"] = set(d["exempt_role_ids"])
    return d


def test_bad_words_whole_word_wildcard_and_leet():
    cfg = {"words": ["tonto", "spam*"]}
    assert check_static("bad_words", cfg, MessageInfo("eres un TONTO")).detail == "tonto"
    assert check_static("bad_words", cfg, MessageInfo("eres un t0nt0")) is not None
    assert check_static("bad_words", cfg, MessageInfo("spammer total")) is not None
    assert check_static("bad_words", cfg, MessageInfo("tontería no cuenta")) is None


def test_links_modes():
    msg = MessageInfo("mira https://www.youtube.com/watch?v=1 y https://evil.example/x")
    assert check_static("links", {"mode": "allowlist", "domains": ["youtube.com"]}, msg).detail == "evil.example"
    assert check_static("links", {"mode": "blocklist", "domains": ["evil.example"]}, msg).detail == "evil.example"
    assert check_static("links", {"mode": "blocklist", "domains": ["other.com"]}, msg) is None
    assert check_static("links", {"mode": "allowlist", "domains": ["youtube.com", "example"]},
                        MessageInfo("https://sub.youtube.com")) is None


def test_invites_allow_own_server():
    msg = MessageInfo("únete discord.gg/abc123", guild_invite_codes={"abc123"})
    assert check_static("invites", {"allow_own_server": True}, msg) is None
    assert check_static("invites", {"allow_own_server": False}, msg) is not None


def test_caps_and_mentions():
    assert check_static("caps", {"min_length": 5, "max_percent": 70}, MessageInfo("HOLA A TODOS")) is not None
    assert check_static("caps", {"min_length": 5, "max_percent": 70}, MessageInfo("Hola a todos")) is None
    assert check_static("mass_mentions", {"max_mentions": 2}, MessageInfo("<@1> <@2> <@3>")) is not None


def test_spam_and_duplicates_windows():
    t = RateTracker()
    cfg = {"max_messages": 3, "per_seconds": 5}
    assert [t.check("spam", cfg, 1, 1, "x", now=i) for i in range(3)] == [None, None, None]
    assert t.check("spam", cfg, 1, 1, "x", now=3) is not None
    assert t.check("spam", cfg, 1, 1, "x", now=20) is None  # la ventana se vació
    d = {"max_repeats": 2, "per_seconds": 30}
    assert t.check("duplicates", d, 1, 2, "hola", now=0) is None
    assert t.check("duplicates", d, 1, 2, "HOLA ", now=1) is None
    assert t.check("duplicates", d, 1, 2, "hola", now=2) is not None


def test_priority_and_exemptions():
    rules = [rule("caps", {"min_length": 3}, priority=1), rule("bad_words", {"words": ["feo"]}, priority=5,
                                                                exempt_role_ids=["123456789012345678"])]
    hit = check_message(rules, MessageInfo("ERES FEO"))
    assert hit and hit[0]["rule_type"] == "bad_words"
    hit = check_message(rules, MessageInfo("ERES FEO"), role_ids={123456789012345678})
    assert hit and hit[0]["rule_type"] == "caps"


def test_rule_validation():
    with pytest.raises(ValidationError, match="one_punishment_only"):
        AutomodRuleIn(name="x", rule_type="caps", actions=[{"type": "warn"}, {"type": "ban"}])
    with pytest.raises(ValidationError, match="duration_required"):
        AutomodRuleIn(name="x", rule_type="caps", actions=[{"type": "timeout"}])


def test_moderation_escalation_sorted_and_unique():
    cfg = ModerationConfig(escalation=[{"warns": 5, "action": "kick"}, {"warns": 3, "action": "timeout", "duration_seconds": 600}])
    assert [s.warns for s in cfg.escalation] == [3, 5]
    with pytest.raises(ValidationError):
        ModerationConfig(escalation=[{"warns": 3, "action": "kick"}, {"warns": 3, "action": "ban"}])


def test_logging_defaults_and_channel_lookup():
    cfg = LoggingConfig.model_validate({"categories": {"messages": {"channel_id": "111111111111111111",
                                                                    "events": {"message_edit": False}}}})
    assert channel_for(cfg, "message_delete") == 111111111111111111
    assert channel_for(cfg, "message_edit") is None
    assert channel_for(cfg, "role_create") is None
    assert set(cfg.categories) == {"messages", "members", "roles", "channels", "moderation", "voice"}


def test_logging_per_event_channel():
    from nexus_core.modules.moderation import LoggingConfig, channel_for

    cfg = LoggingConfig.model_validate({"categories": {"voice": {
        "channel_id": "111111111111111111",
        "event_channels": {"voice_leave": "222222222222222222", "no_existe": "333333333333333333"},
        "events": {"voice_move": False}}}})
    assert channel_for(cfg, "voice_join") == 111111111111111111   # canal de la categoría
    assert channel_for(cfg, "voice_leave") == 222222222222222222  # canal propio del aviso
    assert channel_for(cfg, "voice_move") is None                  # aviso desactivado
    assert "no_existe" not in cfg.categories["voice"].event_channels
    # Un aviso con canal propio funciona aunque la categoría no tenga canal.
    solo = LoggingConfig.model_validate({"categories": {"members": {"event_channels": {"member_join": "444444444444444444"}}}})
    assert channel_for(solo, "member_join") == 444444444444444444 and channel_for(solo, "member_leave") is None
