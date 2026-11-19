"""IA de moderación: analiza mensajes con Claude dentro de límites de uso y con revisión humana.

La IA nunca expulsa ni banea: como mucho borra el mensaje y aísla temporalmente, y lo deja en la cola de revisión.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import TYPE_CHECKING

import anthropic
import discord
from discord.ext import commands
from sqlalchemy.dialects.postgresql import insert

from nexus_core.ai import ai_configured, classify
from nexus_core.db import sessionmaker
from nexus_core.db.models import AIModerationEvent, AIUsage
from nexus_core.db.repo import utcnow
from nexus_core.i18n import t
from nexus_core.modules import parse_config
from nexus_core.modules.integrations import AIModerationConfig

from nexus_bot.modservice import ModError, ModService

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.ai")


class AIModeration(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self.svc = ModService(bot)
        self._calls: dict[int, deque[float]] = defaultdict(deque)
        self._over_budget: dict[int, str] = {}  # guild → mes en el que se agotó el límite

    def _cfg(self, guild_id: int) -> AIModerationConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("ai_moderation")
        return parse_config("ai_moderation", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    def _allowed_now(self, guild_id: int, per_minute: int) -> bool:
        q, now = self._calls[guild_id], time.monotonic()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= per_minute:
            return False
        q.append(now)
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not isinstance(message.author, discord.Member):
            return
        cfg = self._cfg(message.guild.id)
        if cfg is None or not ai_configured() or len(message.content.strip()) < cfg.min_length:
            return
        member = message.author
        if member.guild_permissions.manage_messages or {r.id for r in member.roles} & set(cfg.exempt_role_ids):
            return
        if cfg.monitored_channel_ids and message.channel.id not in set(cfg.monitored_channel_ids):
            return
        month = utcnow().strftime("%Y-%m")
        if self._over_budget.get(message.guild.id) == month:
            return
        if not self._allowed_now(message.guild.id, cfg.max_requests_per_minute):
            return
        asyncio.create_task(self._analyze(message, member, cfg, month))

    async def _analyze(self, message: discord.Message, member: discord.Member, cfg: AIModerationConfig,
                       month: str) -> None:
        guild = message.guild
        assert guild
        async with sessionmaker()() as db:
            usage = await db.get(AIUsage, (guild.id, month))
            if usage and usage.input_tokens + usage.output_tokens >= cfg.monthly_token_limit:
                self._over_budget[guild.id] = month
                return
        state = self.bot.cache.get(guild.id)
        try:
            v = await classify(message.content, cfg.rules_text, state.locale)
        except anthropic.RateLimitError:
            log.info("IA limitada por la API (429) en %s", guild.id)
            return
        except anthropic.APIError:
            log.warning("La API de IA falló en %s", guild.id, exc_info=True)
            return
        async with sessionmaker()() as db:
            await db.execute(insert(AIUsage).values(guild_id=guild.id, month=month, input_tokens=v.input_tokens,
                                                    output_tokens=v.output_tokens, requests=1).on_conflict_do_update(
                index_elements=["guild_id", "month"],
                set_={"input_tokens": AIUsage.input_tokens + v.input_tokens,
                      "output_tokens": AIUsage.output_tokens + v.output_tokens, "requests": AIUsage.requests + 1}))
            await db.commit()
        if v.category == "none" or not cfg.categories.get(v.category, False) or v.score < cfg.review_threshold:
            return
        act = v.score >= cfg.action_threshold
        action = "review"
        if act and cfg.action in ("delete", "delete_timeout"):
            try:
                await message.delete()
                action = "deleted"
            except discord.HTTPException:
                action = "alert"
            if cfg.action == "delete_timeout":
                try:
                    await self.svc.apply(guild, member, "timeout", moderator=None, duration=cfg.timeout_seconds,
                                         reason=t(state.locale, "ai.reason", category=t(state.locale, f"ai.cat_{v.category}")),
                                         source="ai")
                    action = "deleted_timeout"
                except ModError:
                    pass
        elif act:
            action = "alert"
        async with sessionmaker()() as db:
            db.add(AIModerationEvent(guild_id=guild.id, channel_id=message.channel.id, message_id=message.id,
                                     user_id=member.id, user_name=str(member), category=v.category, score=v.score,
                                     reason=v.reason, action=action, review_status="pending"))
            await db.commit()
        await self._alert(message, member, v.category, v.score, v.reason, action, cfg)

    async def _alert(self, message: discord.Message, member: discord.Member, category: str, score: float,
                     reason: str, action: str, cfg: AIModerationConfig) -> None:
        guild = message.guild
        assert guild
        channel = guild.get_channel(cfg.alert_channel_id or 0)
        if not isinstance(channel, discord.abc.Messageable):
            return
        loc = self.bot.cache.get(guild.id).locale
        e = discord.Embed(title=f"🤖 {t(loc, 'ai.title')} · {t(loc, f'ai.cat_{category}')}",
                          color=0xEF4444 if action.startswith("deleted") else 0xF59E0B, timestamp=utcnow())
        e.add_field(name=t(loc, "mod.user"), value=f"{member.mention} ({member})")
        e.add_field(name=t(loc, "automod.channel"), value=message.channel.mention)  # type: ignore[union-attr]
        e.add_field(name=t(loc, "ai.confidence"), value=f"{round(score * 100)}%")
        e.add_field(name=t(loc, "ai.why"), value=reason or "—", inline=False)
        e.add_field(name=t(loc, "ai.action"), value=t(loc, f"ai.action_{action}"), inline=False)
        if not action.startswith("deleted"):
            e.url = message.jump_url
        e.set_footer(text=t(loc, "ai.review_hint"))
        try:
            await channel.send(embed=e, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(AIModeration(bot))

