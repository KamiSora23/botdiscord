from nexus_core.modules import REGISTRY, parse_config
from nexus_core.modules.moderation import LOG_EVENTS
from nexus_core.modules.voice_activity import format_duration


def test_format_duration():
    assert format_duration(45) == "45 s"
    assert format_duration(125) == "2 min"
    assert format_duration(3725) == "1 h 2 min"
    assert format_duration(90000) == "1 d 1 h"


def test_module_and_log_events():
    assert REGISTRY["voice_activity"].available
    cfg = parse_config("voice_activity", {}, "es")
    assert cfg.retention_days == 90 and cfg.ignore_afk
    assert LOG_EVENTS["voice"] == ["voice_join", "voice_leave", "voice_move"]
    # Las configuraciones de Logs ya guardadas reciben la categoría nueva automáticamente.
    assert "voice" in parse_config("logging", {"categories": {}}, "es").categories
