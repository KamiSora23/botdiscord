"""Ejecuta tareas de scheduled_jobs (docs/NEXUS_DATABASE_SPEC.md §2.10)."""

from __future__ import annotations

import logging
import os
import socket
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert

from nexus_core.db import sessionmaker
from nexus_core.db.models import AIModerationEvent, AutomodEvent, Guild, GuildAuditLog, ScheduledJob, UserSession
from nexus_core.db.repo import utcnow

log = logging.getLogger("nexus.bot.worker")

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
BATCH = 20
STALE_AFTER = timedelta(minutes=10)

Handler = Callable[[ScheduledJob], Awaitable[None]]

CLAIM_SQL = text("""
UPDATE scheduled_jobs SET status = 'running', locked_by = :worker, locked_at = now(),
       attempts = attempts + 1
WHERE id IN (
  SELECT id FROM scheduled_jobs
  WHERE status = 'pending' AND run_at <= now()
  ORDER BY run_at
  LIMIT :limit
  FOR UPDATE SKIP LOCKED
)
RETURNING id
""")


async def _guild_purge(job: ScheduledJob) -> None:
    gid = int(job.payload["guild_id"])
    async with sessionmaker()() as db:
        guild = await db.get(Guild, gid)
        if guild is None or guild.bot_present:
            return  # el bot volvió: no se borra nada
        await db.execute(delete(Guild).where(Guild.id == gid))  # CASCADE borra el resto
        await db.commit()
    log.info("Datos del servidor %s borrados (30 días sin el bot)", gid)


async def _system_cleanup(job: ScheduledJob) -> None:
    now = utcnow()
    async with sessionmaker()() as db:
        await db.execute(delete(GuildAuditLog).where(GuildAuditLog.created_at < now - timedelta(days=180)))
        await db.execute(delete(UserSession).where(UserSession.expires_at < now - timedelta(days=7)))
        # Retención (docs/NEXUS_DATABASE_SPEC.md §5 y /legal/privacy)
        await db.execute(delete(AutomodEvent).where(AutomodEvent.created_at < now - timedelta(days=30)))
        await db.execute(delete(AIModerationEvent).where(AIModerationEvent.created_at < now - timedelta(days=90)))
        await db.execute(delete(ScheduledJob).where(
            ScheduledJob.status.in_(("done", "cancelled")),
            ScheduledJob.completed_at < now - timedelta(days=30)))
        await db.commit()


HANDLERS: dict[str, Handler] = {
    "guild.purge": _guild_purge,
    "system.cleanup": _system_cleanup,
}

# Tareas que se repiten: tipo → intervalo.
RECURRING: dict[str, timedelta] = {"system.cleanup": timedelta(days=1)}


async def ensure_recurring() -> None:
    async with sessionmaker()() as db:
        for job_type in RECURRING:
            await db.execute(insert(ScheduledJob).values(
                job_type=job_type, run_at=utcnow(), dedupe_key=f"{job_type}:next",
            ).on_conflict_do_nothing())
        await db.commit()


async def run_due_jobs(extra_handlers: dict[str, Handler] | None = None) -> int:
    handlers = {**HANDLERS, **(extra_handlers or {})}
    async with sessionmaker()() as db:
        # Tareas de workers que murieron a mitad.
        await db.execute(update(ScheduledJob).where(
            ScheduledJob.status == "running", ScheduledJob.locked_at < utcnow() - STALE_AFTER
        ).values(status="pending", locked_by=None, locked_at=None))
        ids = [r[0] for r in (await db.execute(CLAIM_SQL, {"worker": WORKER_ID, "limit": BATCH})).all()]
        await db.commit()
        if not ids:
            return 0
        jobs = (await db.scalars(select(ScheduledJob).where(ScheduledJob.id.in_(ids)))).all()

    for job in jobs:
        handler = handlers.get(job.job_type)
        values: dict[str, Any]
        try:
            if handler is None:
                raise RuntimeError(f"Tipo de tarea desconocido: {job.job_type}")
            await handler(job)
            if job.job_type in RECURRING:
                values = dict(status="pending", run_at=utcnow() + RECURRING[job.job_type],
                              attempts=0, locked_by=None, locked_at=None, last_error=None)
            else:
                values = dict(status="done", completed_at=utcnow(), locked_by=None)
        except Exception as exc:
            log.exception("Falló la tarea %s (%s)", job.id, job.job_type)
            if job.attempts >= job.max_attempts:
                values = dict(status="failed", last_error=str(exc)[:1000], completed_at=utcnow(),
                              locked_by=None)
            else:
                values = dict(status="pending", last_error=str(exc)[:1000], locked_by=None,
                              locked_at=None, run_at=utcnow() + timedelta(minutes=2 ** job.attempts))
        async with sessionmaker()() as db:
            await db.execute(update(ScheduledJob).where(ScheduledJob.id == job.id).values(**values))
            await db.commit()
    return len(jobs)
