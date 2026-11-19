"""AutoMod: revisa cada mensaje con las reglas del servidor (motor en nexus_core.automod)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from nexus_core.automod import MessageInfo, RateTracker, check_message
from nexus_core.db import sessionmaker
from nexus_core.db.models import AutomodEvent
from nexus_core.i18n import t
from nexus_core.modules import parse_config
from nexus_core.modules.moderation import AutomodConfig, channel_for

from nexus_bot.modservice import ModError, ModService

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.automod")


class AutoMod(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self.svc = ModService(bot)
        self.tracker = RateTracker()
        self._invites: dict[int, set[str]] = {}
        self.prune.start()

    def cog_unload(self) -> None:
        self.prune.cancel()

    @tasks.loop(minutes=5)
    async def prune(self) -> None:
        self.tracker.prune()
        self._invites.clear()

    async def _own_invites(self, guild: discord.Guild) -> set[str]:
        if guild.id not in self._invites:
            codes: set[str] = set()
            try:
                codes = {i.code for i in await guild.invites()}
                if guild.vanity_url_code:
                    codes.add(guild.vanity_url_code)
            except discord.HTTPException:
                pass
            self._invites[guild.id] = codes
        return self._invites[guild.id]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not isinstance(message.author, discord.Member):
            return
        state = self.bot.cache.get(message.guild.id)
        mod = state.module("automod")
        if mod is None or not state.automod_rules:
            return
        member = message.author
        if member.guild_permissions.manage_messages or member.guild_permissions.administrator:
            return  # el staff no se modera automáticamente
        cfg: AutomodConfig = parse_config("automod", mod.config, state.locale)  # type: ignore[assignment]
        role_ids = {r.id for r in member.roles}
        if role_ids & set(cfg.exempt_role_ids) or message.channel.id in set(cfg.exempt_channel_ids):
            return
        invites = await self._own_invites(message.guild) if any(
            r["rule_type"] == "invites" for r in state.automod_rules) else set()
        info = MessageInfo(message.content, mention_count=len(message.mentions) + len(message.role_mentions),
                           guild_invite_codes=invites)
        hit = check_message(state.automod_rules, info, tracker=self.tracker, guild_id=message.guild.id,
                            user_id=member.id, role_ids=role_ids, channel_id=message.channel.id)
        if hit:
            rule, match = hit
            await self._enforce(message, member, rule, match.reason, match.detail, cfg)

    async def _enforce(self, message: discord.Message, member: discord.Member, rule: dict, reason: str,
                       detail: str | None, cfg: AutomodConfig) -> None:
        guild = message.guild
        assert guild
        loc = self.bot.cache.get(guild.id).locale
        test = bool(rule.get("test_mode"))
        actions = [a["type"] for a in rule["actions"]]
        taken: list[str] = []
        if not test:
            if "delete" in actions:
                try:
                    await message.delete()
                    taken.append("delete")
                except discord.HTTPException:
                    pass
            for a in rule["actions"]:
                if a["type"] in ("warn", "timeout", "kick", "ban"):
                    try:
                        await self.svc.apply(guild, member, a["type"], moderator=None, source="automod",
                                             duration=a.get("duration_seconds"),
                                             reason=t(loc, "automod.reason", rule=rule["name"]))
                        taken.append(a["type"])
                    except ModError as exc:
                        log.info("AutoMod no pudo aplicar %s en %s: %s", a["type"], guild.id, exc.key)
        async with sessionmaker()() as db:
            db.add(AutomodEvent(guild_id=guild.id, rule_id=rule.get("id"), user_id=member.id,
                                channel_id=message.channel.id, action_taken=",".join(taken) or "none",
                                test_mode=test, excerpt=message.content[:200] or None))
            await db.commit()
        if test or "alert" in actions or taken:
            await self._alert(message, member, rule, reason, detail, taken, test, cfg)

    async def _alert(self, message: discord.Message, member: discord.Member, rule: dict, reason: str,
                     detail: str | None, taken: list[str], test: bool, cfg: AutomodConfig) -> None:
        guild = message.guild
        assert guild
        lcfg = self.svc.logging_config(guild.id)
        channel_id = cfg.log_channel_id or (channel_for(lcfg, "automod_action") if lcfg else None)
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.abc.Messageable):
            return
        loc = self.bot.cache.get(guild.id).locale
        embed = discord.Embed(
            title=("🧪 " if test else "🛡️ ") + t(loc, "automod.title", rule=rule["name"]),
            color=0xF59E0B if test else 0xEF4444,
        )
        embed.add_field(name=t(loc, "mod.user"), value=f"{member.mention} ({member})")
        embed.add_field(name=t(loc, "automod.channel"), value=message.channel.mention)  # type: ignore[union-attr]
        embed.add_field(name=t(loc, "automod.detected"), value=f"{t(loc, f'automod.type_{reason}')}" +
                        (f": `{detail[:100]}`" if detail else ""), inline=False)
        if message.content:
            embed.add_field(name=t(loc, "automod.message"), value=message.content[:1000], inline=False)
        embed.set_footer(text=t(loc, "automod.test_mode") if test else
                         t(loc, "automod.actions", actions=", ".join(taken) or "—"))
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(AutoMod(bot))
