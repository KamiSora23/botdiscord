"""Eventos con inscripción: tarjeta con botones (Asistiré / Tal vez / No podré), cupos y recordatorio."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

from nexus_core.messages.template import OptSnowflake, Snowflake

RSVP = ("going", "maybe", "no")


class EventsConfig(BaseModel):
    default_channel_id: OptSnowflake = None
    reminder_minutes: int = Field(15, ge=0, le=1440)  # 0 = sin recordatorio
    manager_role_ids: list[Snowflake] = Field(default_factory=list, max_length=10)
    ping_at_start: bool = True  # mencionar a los inscritos cuando empieza


def events_default(locale: str = "es") -> EventsConfig:
    return EventsConfig()


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field("", max_length=1500)
    starts_at: datetime
    channel_id: Snowflake
    max_slots: int | None = Field(None, ge=1, le=1000)
    image_url: str | None = Field(None, max_length=500)

    @field_validator("image_url")
    @classmethod
    def _img(cls, v: str | None) -> str | None:
        if not v:
            return None
        from nexus_core.media import MEDIA_RE

        if not (v.startswith("https://") or MEDIA_RE.match(v)):  # enlace o imagen subida al panel
            raise ValueError("invalid_url")
        return v

    @field_validator("starts_at")
    @classmethod
    def _future(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timezone_required")
        if v <= datetime.now(v.tzinfo) + timedelta(minutes=1):
            raise ValueError("in_the_past")
        return v


_REL = re.compile(r"(\d+)\s*([mhdw])")
_ABS = re.compile(r"^(?:(\d{4})-(\d{1,2})-(\d{1,2})|(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?)\s+(\d{1,2}):(\d{2})$")


def parse_when(text: str, tz: str, now: datetime) -> datetime | None:
    """«2h», «1d3h», «20/11 21:00», «20/11/2026 21:00» o «2026-11-20 21:00» (en la zona ``tz``) → instante."""
    text = text.strip().lower()
    if _REL.fullmatch(text.replace(" ", "")) or re.fullmatch(r"(\d+\s*[mhdw]\s*)+", text):
        total = sum(int(n) * {"m": 60, "h": 3600, "d": 86400, "w": 604800}[u] for n, u in _REL.findall(text))
        return now + timedelta(seconds=total) if total else None
    m = _ABS.match(text)
    if not m:
        return None
    try:
        zone = ZoneInfo(tz)
    except Exception:  # noqa: BLE001
        zone = ZoneInfo("UTC")
    local_now = now.astimezone(zone)
    if m.group(1):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        d, mo = int(m.group(4)), int(m.group(5))
        y = int(m.group(6)) if m.group(6) else local_now.year
        if y < 100:
            y += 2000
    try:
        dt = datetime(y, mo, d, int(m.group(7)), int(m.group(8)), tzinfo=zone)
    except ValueError:
        return None
    if not m.group(1) and not m.group(6) and dt < local_now:  # «20/11» ya pasado este año → el próximo
        dt = dt.replace(year=dt.year + 1)
    return dt
