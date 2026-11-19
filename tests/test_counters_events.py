from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nexus_core.modules import REGISTRY, parse_config
from nexus_core.modules.counters import Counter, format_count, render_name
from nexus_core.modules.events import EventIn, parse_when


def test_counters_defaults_and_names():
    assert REGISTRY["counters"].available and REGISTRY["events"].available
    cfg = parse_config("counters", {}, "es")
    assert [c.type for c in cfg.counters] == ["members", "humans"]
    assert render_name("👥 Miembros: {count}", 1420, "es") == "👥 Miembros: 1.420"
    assert render_name("👥 Members: {count}", 1420, "en") == "👥 Members: 1,420"
    assert format_count(5, "es") == "5"
    with pytest.raises(ValidationError, match="count_required"):
        Counter(template="sin número")


def test_parse_when_formats():
    now = datetime(2026, 11, 16, 23, 0, tzinfo=timezone.utc)
    assert parse_when("2h", "UTC", now) == now + timedelta(hours=2)
    assert parse_when("1d 3h", "UTC", now) == now + timedelta(days=1, hours=3)
    lima = parse_when("20/11 21:00", "America/Lima", now)
    assert lima.utcoffset() == timedelta(hours=-5) and (lima.month, lima.day, lima.hour) == (11, 20, 21)
    assert parse_when("2026-11-20 21:00", "UTC", now).isoformat() == "2026-11-20T21:00:00+00:00"
    assert parse_when("01/01 10:00", "UTC", now).year == 2027  # ya pasó este año → el próximo
    assert parse_when("mañana", "UTC", now) is None and parse_when("31/02 10:00", "UTC", now) is None


def test_event_input_validation():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    ok = EventIn(title="Torneo", starts_at=future, channel_id="111111111111111111", max_slots=10)
    assert ok.channel_id == 111111111111111111
    with pytest.raises(ValidationError, match="in_the_past"):
        EventIn(title="x", starts_at=datetime.now(timezone.utc) - timedelta(hours=1), channel_id="111111111111111111")
    with pytest.raises(ValidationError, match="invalid_url"):
        EventIn(title="x", starts_at=future, channel_id="111111111111111111", image_url="http://inseguro")
