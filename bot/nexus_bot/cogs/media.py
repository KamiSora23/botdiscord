"""Limpieza de imágenes subidas que ya no usa nada (p. ej. las de un embed que se envió una sola vez)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands, tasks
from sqlalchemy import select

from nexus_core import media as M
from nexus_core.db import sessionmaker
from nexus_core.db.models import Media

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.media")


class MediaCleanup(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self.cleanup.start()

    async def cog_unload(self) -> None:
        self.cleanup.cancel()

    @tasks.loop(hours=6)
    async def cleanup(self) -> None:
        async with sessionmaker()() as db:
            guilds = (await db.scalars(select(Media.guild_id).distinct())).all()
            total = 0
            for gid in guilds:
                total += await M.cleanup_unused(db, gid)
            await db.commit()
        if total:
            log.info("Imágenes sin usar borradas: %s", total)

    @cleanup.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(MediaCleanup(bot))
