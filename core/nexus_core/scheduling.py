"""Cálculo de la próxima ejecución de mensajes programados, en la zona horaria del servidor."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _local(local_time: str, tz: str) -> datetime:
    return datetime.strptime(local_time, "%Y-%m-%dT%H:%M").replace(tzinfo=ZoneInfo(tz))


def _add_month(dt: datetime, day: int) -> datetime:
    year, month = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    last = calendar.monthrange(year, month)[1]
    return dt.replace(year=year, month=month, day=min(day, last))


def next_run(local_time: str, tz: str, repeat: str, after: datetime) -> datetime | None:
    """Primera ejecución estrictamente posterior a ``after`` (UTC). None si ya pasó y no se repite.

    Las repeticiones se calculan en hora local: "todos los días a las 9:00" sigue siendo a las 9:00
    después de un cambio de horario de verano.
    """
    start = _local(local_time, tz)
    after_local = after.astimezone(ZoneInfo(tz))
    if start > after_local:
        return start.astimezone(timezone.utc)
    if repeat == "none":
        return None
    candidate = start
    if repeat == "daily":
        days = (after_local.date() - start.date()).days
        candidate = start + timedelta(days=max(days, 0))
        while candidate <= after_local:
            candidate += timedelta(days=1)
    elif repeat == "weekly":
        weeks = (after_local.date() - start.date()).days // 7
        candidate = start + timedelta(weeks=max(weeks, 0))
        while candidate <= after_local:
            candidate += timedelta(weeks=1)
    elif repeat == "monthly":
        while candidate <= after_local:
            candidate = _add_month(candidate, start.day)
    # Reconstruir con la hora local para respetar el horario de verano.
    candidate = candidate.replace(tzinfo=None).replace(tzinfo=ZoneInfo(tz))
    return candidate.astimezone(timezone.utc)


async def schedule_message_job(db, message, tz: str) -> None:  # type: ignore[no-untyped-def]
    """Cancela la tarea pendiente de un ScheduledMessage y crea la siguiente (si toca)."""
    from sqlalchemy import update

    from nexus_core.db.models import ScheduledJob
    from nexus_core.db.repo import utcnow

    await db.execute(update(ScheduledJob).where(
        ScheduledJob.job_type == "scheduled_message.send", ScheduledJob.status == "pending",
        ScheduledJob.payload["id"].astext == str(message.id)).values(status="cancelled", completed_at=utcnow()))
    tz = getattr(message, "timezone", None) or tz  # cada mensaje usa la zona en que se programó
    message.next_run_at = (next_run(message.local_time, tz, message.repeat, utcnow())
                           if message.status == "scheduled" else None)
    if message.next_run_at:
        db.add(ScheduledJob(guild_id=message.guild_id, job_type="scheduled_message.send", run_at=message.next_run_at,
                            payload={"id": str(message.id)},
                            dedupe_key=f"scheduled_message:{message.id}:{message.next_run_at.isoformat()}"))
