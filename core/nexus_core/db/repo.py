"""Operaciones compartidas por la API y el bot."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.models import (
    Guild,
    GuildAuditLog,
    GuildConfig,
    GuildDailyStats,
    ScheduledJob,
)

GUILD_PURGE_DELAY = timedelta(days=30)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def upsert_guild(
    session: AsyncSession,
    *,
    guild_id: int,
    name: str,
    icon: str | None,
    owner_id: int,
    member_count: int | None = None,
    bot_present: bool | None = None,
) -> None:
    """Crea o actualiza el servidor y se asegura de que tenga guild_configs."""
    values: dict[str, Any] = {
        "id": guild_id,
        "name": name,
        "icon": icon,
        "owner_id": owner_id,
        "updated_at": utcnow(),
    }
    if member_count is not None:
        values["member_count"] = member_count
    if bot_present is not None:
        values["bot_present"] = bot_present
    stmt = insert(Guild).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Guild.id], set_={k: v for k, v in values.items() if k != "id"}
    )
    await session.execute(stmt)
    await session.execute(
        insert(GuildConfig).values(guild_id=guild_id).on_conflict_do_nothing()
    )


async def mark_bot_joined(session: AsyncSession, guild_id: int) -> bool:
    """Devuelve True si el bot no estaba marcado como presente (entrada nueva)."""
    result = await session.execute(
        update(Guild)
        .where(Guild.id == guild_id, Guild.bot_present.is_(False))
        .values(bot_present=True, bot_joined_at=utcnow(), bot_left_at=None)
    )
    await session.execute(
        update(ScheduledJob)
        .where(ScheduledJob.dedupe_key == f"guild.purge:{guild_id}", ScheduledJob.status == "pending")
        .values(status="cancelled", completed_at=utcnow())
    )
    return bool(result.rowcount)


async def mark_bot_left(session: AsyncSession, guild_id: int) -> None:
    now = utcnow()
    await session.execute(
        update(Guild).where(Guild.id == guild_id).values(bot_present=False, bot_left_at=now)
    )
    key = f"guild.purge:{guild_id}"
    # Un trabajo anterior (cancelado o terminado) con la misma clave se reutiliza.
    stmt = insert(ScheduledJob).values(
        guild_id=guild_id,
        job_type="guild.purge",
        payload={"guild_id": str(guild_id)},
        run_at=now + GUILD_PURGE_DELAY,
        dedupe_key=key,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[ScheduledJob.dedupe_key],
        set_={
            "status": "pending",
            "run_at": now + GUILD_PURGE_DELAY,
            "attempts": 0,
            "last_error": None,
            "completed_at": None,
            "locked_by": None,
            "locked_at": None,
        },
    )
    await session.execute(stmt)


async def add_audit(
    session: AsyncSession,
    *,
    guild_id: int,
    action: str,
    source: str,
    actor_id: int | None = None,
    module: str | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    session.add(
        GuildAuditLog(
            guild_id=guild_id,
            actor_id=actor_id,
            source=source,
            action=action,
            module=module,
            changes=changes,
        )
    )


STAT_COLUMNS = ("members_joined", "members_left", "commands_used", "welcome_sent", "mod_actions")


async def add_daily_stats(
    session: AsyncSession, guild_id: int, day: date, counters: dict[str, int]
) -> None:
    values = {k: v for k, v in counters.items() if k in STAT_COLUMNS and v}
    if not values:
        return
    stmt = insert(GuildDailyStats).values(guild_id=guild_id, day=day, **values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[GuildDailyStats.guild_id, GuildDailyStats.day],
        set_={k: getattr(GuildDailyStats, k) + v for k, v in values.items()},
    )
    await session.execute(stmt)


async def get_guild_config(session: AsyncSession, guild_id: int) -> GuildConfig | None:
    return await session.scalar(select(GuildConfig).where(GuildConfig.guild_id == guild_id))


def diff_changes(old: dict[str, Any], new: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Claves que cambiaron, aplanadas con puntos: {"a.b": {"old": 1, "new": 2}}."""
    out: dict[str, Any] = {}
    for key in sorted(set(old) | set(new)):
        path = f"{prefix}{key}"
        a, b = old.get(key), new.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            out.update(diff_changes(a, b, path + "."))
        elif a != b:
            out[path] = {"old": a, "new": b}
    return out


async def next_number(db: AsyncSession, model: Any, guild_id: int, column: str = "number") -> int:
    """Siguiente número por servidor (tickets, sugerencias…). El bloqueo evita números repetidos."""
    from sqlalchemy import func, text

    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": guild_id})
    col = getattr(model, column)
    return (await db.scalar(select(func.coalesce(func.max(col), 0)).where(model.guild_id == guild_id))) + 1
