"""Contadores diarios acumulados en memoria y volcados a PostgreSQL cada 60 s."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from sqlalchemy import update

from nexus_core.db import sessionmaker
from nexus_core.db.models import Guild
from nexus_core.db.repo import add_daily_stats, utcnow

log = logging.getLogger("nexus.bot.stats")


class StatsBuffer:
    def __init__(self) -> None:
        self._counters: dict[tuple[int, date], dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._member_counts: dict[int, int] = {}

    def incr(self, guild_id: int, column: str, amount: int = 1) -> None:
        self._counters[(guild_id, utcnow().date())][column] += amount

    def set_member_count(self, guild_id: int, count: int) -> None:
        self._member_counts[guild_id] = count

    async def flush(self) -> None:
        counters, self._counters = self._counters, defaultdict(lambda: defaultdict(int))
        members, self._member_counts = self._member_counts, {}
        if not counters and not members:
            return
        try:
            async with sessionmaker()() as db:
                for (gid, day), values in counters.items():
                    await add_daily_stats(db, gid, day, dict(values))
                for gid, count in members.items():
                    await db.execute(update(Guild).where(Guild.id == gid).values(member_count=count))
                await db.commit()
        except Exception:
            log.exception("No se pudieron guardar las estadísticas; se reintentan en el siguiente ciclo")
            for key, values in counters.items():
                for col, n in values.items():
                    self._counters[key][col] += n
            for gid, count in members.items():
                self._member_counts.setdefault(gid, count)
