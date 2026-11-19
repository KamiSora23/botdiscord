"""Integraciones: consulta YouTube, RSS, GitHub y Twitch cada pocos minutos y avisa en Discord."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import discord
import httpx
from discord.ext import commands, tasks
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from nexus_core.db import sessionmaker
from nexus_core.db.models import Integration, IntegrationDelivery
from nexus_core.db.repo import utcnow
from nexus_core.feeds import FeedError, FeedItem, fetch_items
from nexus_core.messages import MessageTemplate, render_payload

from nexus_bot.cogs.welcome import context_for, with_media

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.integrations")
MAX_POSTS_PER_CHECK = 3


class Integrations(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self.http = httpx.AsyncClient()
        self._cycle = 0
        bot.rpc_handlers["integrations.test"] = self.rpc_test
        self.poll.start()

    async def cog_unload(self) -> None:
        self.poll.cancel()
        await self.http.aclose()

    async def _post(self, integ: Integration, name: str, item: FeedItem) -> None:
        guild = self.bot.get_guild(integ.guild_id)
        channel = guild.get_channel(integ.channel_id) if guild else None
        if guild is None or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise FeedError("channel_not_found")
        state = self.bot.cache.get(guild.id)
        extra = {"title": item.title[:256], "url": item.url, "author": item.author[:100], "name": name[:100],
                 "thumbnail": item.thumbnail}
        payload = render_payload(MessageTemplate.model_validate(integ.message),
                                 context_for(guild.me, guild, channel.id, state.locale, state.timezone),
                                 state.embed_color, extra=extra)
        kwargs = await with_media(guild.id, payload)
        kwargs["allowed_mentions"] = discord.AllowedMentions(everyone=True, roles=True)
        try:
            await channel.send(**kwargs)
        except discord.Forbidden as exc:
            raise FeedError("bot_cannot_send") from exc

    async def check(self, integ: Integration) -> None:
        try:
            name, items = await fetch_items(self.http, integ.provider, integ.external_id)
        except (FeedError, httpx.HTTPError) as exc:
            async with sessionmaker()() as db:
                row = await db.get(Integration, integ.id)
                if row:
                    row.status, row.last_error = "error", getattr(exc, "code", "unreachable")
                    row.last_checked_at = utcnow()
                    await db.commit()
            return
        async with sessionmaker()() as db:
            known = set((await db.scalars(select(IntegrationDelivery.external_event_id).where(
                IntegrationDelivery.integration_id == integ.id))).all())
            new = [i for i in items if i.id not in known]
            row = await db.get(Integration, integ.id)
            if row is None:
                return
            to_post = [] if not row.initialized else list(reversed(new))[-MAX_POSTS_PER_CHECK:]
            error = None
            for item in to_post:
                try:
                    await self._post(row, name or row.display_name or row.external_id, item)
                    row.last_event_at = utcnow()
                except FeedError as exc:
                    error = exc.code
                    break
            for item in new:
                # Al iniciar (o si hay muchos a la vez) los anteriores se marcan como vistos sin avisar.
                await db.execute(insert(IntegrationDelivery).values(
                    integration_id=row.id, external_event_id=item.id[:500], title=item.title[:300], url=item.url[:500],
                    status="sent" if item in to_post and error is None else "skipped").on_conflict_do_nothing())
            row.initialized = True
            row.display_name = (name or row.display_name or "")[:100] or row.display_name
            row.status, row.last_error, row.last_checked_at = ("error", error, utcnow()) if error else ("ok", None, utcnow())
            await db.commit()

    @tasks.loop(minutes=1)
    async def poll(self) -> None:
        """Twitch cada 2 minutos (los directos son cortos); el resto cada 5."""
        self._cycle += 1
        providers = {"twitch"} if self._cycle % 2 == 0 else set()
        if self._cycle % 5 == 0:
            providers |= {"youtube", "rss", "github"}
        if not providers:
            return
        guild_ids = [g.id for g in self.bot.guilds if self.bot.cache.get(g.id).module("integrations")]
        if not guild_ids:
            return
        async with sessionmaker()() as db:
            rows = (await db.scalars(select(Integration).where(
                Integration.guild_id.in_(guild_ids), Integration.enabled.is_(True),
                Integration.provider.in_(providers)))).all()
        sem = asyncio.Semaphore(5)

        async def run(i: Integration) -> None:
            async with sem:
                try:
                    await self.check(i)
                except Exception:
                    log.exception("Error revisando la integración %s", i.id)

        await asyncio.gather(*(run(i) for i in rows))
        if self._cycle % 1440 == 0:  # una vez al día: limpiar entregas de más de 30 días
            from datetime import timedelta

            async with sessionmaker()() as db:
                await db.execute(delete(IntegrationDelivery).where(
                    IntegrationDelivery.created_at < utcnow() - timedelta(days=30)))
                await db.commit()

    @poll.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()

    async def rpc_test(self, params: dict[str, Any]) -> dict[str, Any]:
        """Publica el elemento más reciente de la fuente para comprobar el mensaje."""
        from nexus_bot.client import RpcFailure

        async with sessionmaker()() as db:
            integ = await db.get(Integration, int(params["id"]))
        if integ is None or integ.guild_id != int(params["guild_id"]):
            raise RpcFailure("not_found")
        try:
            name, items = await fetch_items(self.http, integ.provider, integ.external_id)
            if not items:
                raise RpcFailure("no_items")
            await self._post(integ, name or integ.display_name or integ.external_id, items[0])
        except FeedError as exc:
            raise RpcFailure(exc.code) from exc
        return {"title": items[0].title}


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Integrations(bot))
