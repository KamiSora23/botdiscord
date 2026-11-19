"""Niveles/XP y economía virtual."""

from __future__ import annotations

import logging
import random
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from nexus_core.db import sessionmaker
from nexus_core.db.models import EconomyInventory, EconomyItem, MemberWallet, MemberXP
from nexus_core.db.repo import utcnow
from nexus_core.economy import EconomyError, change_balance, transfer, wallet_for_update
from nexus_core.i18n import t
from nexus_core.messages.render import substitute, variables
from nexus_core.modules import parse_config
from nexus_core.modules.progression import EconomyConfig, LevelsConfig, level_from_xp

from nexus_bot.cogs.welcome import context_for
from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.progression")


def bar(progress: int, needed: int, width: int = 14) -> str:
    filled = round(width * progress / needed) if needed else 0
    return "█" * filled + "░" * (width - filled)


class Progression(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot

    def _loc(self, gid: int | None) -> str:
        return self.bot.cache.get(gid or 0).locale

    def _levels(self, gid: int) -> LevelsConfig | None:
        state = self.bot.cache.get(gid)
        mod = state.module("levels")
        return parse_config("levels", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    def _eco(self, gid: int) -> EconomyConfig | None:
        state = self.bot.cache.get(gid)
        mod = state.module("economy")
        return parse_config("economy", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    # --- XP y recompensas por mensaje -----------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not isinstance(message.author, discord.Member):
            return
        lv, eco = self._levels(message.guild.id), self._eco(message.guild.id)
        if lv:
            await self._give_xp(message, message.author, lv)
        if eco and eco.message_reward:
            await self._message_reward(message.author, eco)

    async def _give_xp(self, message: discord.Message, member: discord.Member, cfg: LevelsConfig) -> None:
        if message.channel.id in set(cfg.ignored_channel_ids) or {r.id for r in member.roles} & set(cfg.ignored_role_ids):
            return
        now = utcnow()
        async with sessionmaker()() as db:
            await db.execute(insert(MemberXP).values(guild_id=member.guild.id, user_id=member.id,
                                                     user_name=member.display_name).on_conflict_do_nothing())
            row = await db.scalar(select(MemberXP).where(MemberXP.guild_id == member.guild.id,
                                                         MemberXP.user_id == member.id).with_for_update())
            assert row is not None
            row.message_count += 1
            row.user_name = member.display_name[:100]
            row.avatar = member.display_avatar.key if member.display_avatar else None
            if row.last_xp_at and (now - row.last_xp_at).total_seconds() < cfg.cooldown_seconds:
                await db.commit()
                return
            old_level = row.level
            row.xp += random.randint(cfg.xp_min, cfg.xp_max)
            row.last_xp_at = now
            row.level = level_from_xp(row.xp)[0]
            new_level = row.level
            await db.commit()
        if new_level > old_level:
            await self._level_up(message, member, cfg, new_level)

    async def _level_up(self, message: discord.Message, member: discord.Member, cfg: LevelsConfig, level: int) -> None:
        guild = member.guild
        me = guild.me
        earned = [r for r in cfg.rewards if r.level <= level]
        if earned:
            target = earned if cfg.stack_rewards else [earned[-1]]
            add = [role for r in target if (role := guild.get_role(r.role_id)) and role < me.top_role]
            remove = [] if cfg.stack_rewards else [role for r in earned[:-1] if (role := guild.get_role(r.role_id))
                                                  and role in member.roles and role < me.top_role]
            try:
                if add:
                    await member.add_roles(*[r for r in add if r not in member.roles], reason=f"NEXUS level {level}")
                if remove:
                    await member.remove_roles(*remove, reason=f"NEXUS level {level}")
            except discord.HTTPException:
                pass
        if cfg.announce == "none":
            return
        state = self.bot.cache.get(guild.id)
        values = variables(context_for(member, guild, message.channel.id, state.locale, state.timezone))
        values["level"] = str(level)
        text = substitute(cfg.announce_message, values)
        mentions = discord.AllowedMentions(users=[member], everyone=False, roles=False)
        try:
            if cfg.announce == "dm":
                await member.send(text)
            else:
                channel = guild.get_channel(cfg.announce_channel_id or 0) if cfg.announce == "channel" else message.channel
                if isinstance(channel, discord.abc.Messageable):
                    await channel.send(text, allowed_mentions=mentions)
        except discord.HTTPException:
            pass

    async def _message_reward(self, member: discord.Member, cfg: EconomyConfig) -> None:
        now = utcnow()
        async with sessionmaker()() as db:
            w = await wallet_for_update(db, member.guild.id, member.id, start_balance=cfg.start_balance,
                                        user_name=member.display_name)
            if w.last_message_reward_at and (now - w.last_message_reward_at).total_seconds() < cfg.message_cooldown_seconds:
                await db.commit()
                return
            w.last_message_reward_at = now
            await change_balance(db, member.guild.id, member.id, cfg.message_reward, "message", max_balance=cfg.max_balance)
            await db.commit()

    # --- Comandos de niveles -------------------------------------------------
    @app_commands.command(name=key("cmd.rank.name"), description=key("cmd.rank.description"))
    @app_commands.guild_only()
    @app_commands.describe(user=key("arg.user"))
    async def rank(self, i: discord.Interaction, user: discord.Member | None = None) -> None:
        assert i.guild
        loc = self._loc(i.guild_id)
        cfg = self._levels(i.guild.id)
        if cfg is None:
            await i.response.send_message(t(loc, "lv.disabled"), ephemeral=True)
            return
        target = user or i.user
        async with sessionmaker()() as db:
            row = await db.get(MemberXP, (i.guild.id, target.id))
            position = (await db.scalar(select(func.count()).select_from(MemberXP).where(
                MemberXP.guild_id == i.guild.id, MemberXP.xp > (row.xp if row else 0)))) + 1 if row else None
        e = discord.Embed(title=t(loc, "lv.rank_title", user=target.display_name), color=cfg.card_color)
        e.set_thumbnail(url=target.display_avatar.url)
        if row is None:
            e.description = t(loc, "lv.no_xp")
        else:
            level, into, need = level_from_xp(row.xp)
            e.add_field(name=t(loc, "lv.level"), value=f"**{level}**")
            e.add_field(name=t(loc, "lv.rank"), value=f"#{position}")
            e.add_field(name=t(loc, "lv.messages"), value=str(row.message_count))
            e.add_field(name=t(loc, "lv.xp"), value=f"`{bar(into, need)}` {into}/{need}", inline=False)
        await i.response.send_message(embed=e)

    @app_commands.command(name=key("cmd.leaderboard.name"), description=key("cmd.leaderboard.description"))
    @app_commands.guild_only()
    @app_commands.describe(page=key("arg.page"))
    async def leaderboard(self, i: discord.Interaction, page: app_commands.Range[int, 1, 100] = 1) -> None:
        assert i.guild
        loc = self._loc(i.guild_id)
        cfg = self._levels(i.guild.id)
        if cfg is None:
            await i.response.send_message(t(loc, "lv.disabled"), ephemeral=True)
            return
        async with sessionmaker()() as db:
            total = await db.scalar(select(func.count()).select_from(MemberXP).where(MemberXP.guild_id == i.guild.id))
            rows = (await db.scalars(select(MemberXP).where(MemberXP.guild_id == i.guild.id)
                                     .order_by(MemberXP.xp.desc()).offset((page - 1) * 10).limit(10))).all()
        medals = ["🥇", "🥈", "🥉"]
        start = (page - 1) * 10
        lines = [f"{medals[start + n] if start + n < 3 else f'`#{start + n + 1}`'} <@{r.user_id}> · {t(loc, 'lv.level')} **{level_from_xp(r.xp)[0]}** · {r.xp} XP"
                 for n, r in enumerate(rows)]
        e = discord.Embed(title=t(loc, "lv.board_title", server=i.guild.name), color=cfg.card_color,
                          description="\n".join(lines) or t(loc, "lv.board_empty"))
        pages = max(1, -(-(total or 0) // 10))
        e.set_footer(text=t(loc, "lv.board_page", page=page, pages=pages))
        await i.response.send_message(embed=e, allowed_mentions=discord.AllowedMentions.none())

    # --- Comandos de economía ------------------------------------------------
    async def _eco_or_reply(self, i: discord.Interaction) -> EconomyConfig | None:
        cfg = self._eco(i.guild_id or 0)
        if cfg is None:
            await i.response.send_message(t(self._loc(i.guild_id), "eco.disabled"), ephemeral=True)
        return cfg

    @app_commands.command(name=key("cmd.balance.name"), description=key("cmd.balance.description"))
    @app_commands.guild_only()
    @app_commands.describe(user=key("arg.user"))
    async def balance(self, i: discord.Interaction, user: discord.Member | None = None) -> None:
        cfg = await self._eco_or_reply(i)
        if cfg is None:
            return
        target = user or i.user
        async with sessionmaker()() as db:
            w = await db.get(MemberWallet, (i.guild_id, target.id))
        amount = w.balance if w else cfg.start_balance
        await i.response.send_message(t(self._loc(i.guild_id), "eco.balance", user=target.display_name, amount=f"{amount:,}",
                                        emoji=cfg.currency_emoji, currency=cfg.currency_name))

    async def _timed(self, i: discord.Interaction, kind: str) -> None:
        cfg = await self._eco_or_reply(i)
        if cfg is None:
            return
        loc = self._loc(i.guild_id)
        now = utcnow()
        async with sessionmaker()() as db:
            w = await wallet_for_update(db, i.guild_id or 0, i.user.id, start_balance=cfg.start_balance,
                                        user_name=i.user.display_name)
            last = w.last_daily_at if kind == "daily" else w.last_work_at
            wait = timedelta(hours=20) if kind == "daily" else timedelta(minutes=cfg.work_cooldown_minutes)
            if last and now - last < wait:
                await db.rollback()
                when = f"<t:{int((last + wait).timestamp())}:R>"
                await i.response.send_message(t(loc, f"eco.{kind}_wait", when=when), ephemeral=True)
                return
            amount = cfg.daily_amount if kind == "daily" else random.randint(cfg.work_min, cfg.work_max)
            if kind == "daily":
                w.last_daily_at = now
            else:
                w.last_work_at = now
            bal = await change_balance(db, i.guild_id or 0, i.user.id, amount, kind, max_balance=cfg.max_balance)
            await db.commit()
        await i.response.send_message(t(loc, f"eco.{kind}", amount=f"{amount:,}", emoji=cfg.currency_emoji,
                                        balance=f"{bal:,}"))

    @app_commands.command(name=key("cmd.daily.name"), description=key("cmd.daily.description"))
    @app_commands.guild_only()
    async def daily(self, i: discord.Interaction) -> None:
        await self._timed(i, "daily")

    @app_commands.command(name=key("cmd.work.name"), description=key("cmd.work.description"))
    @app_commands.guild_only()
    async def work(self, i: discord.Interaction) -> None:
        await self._timed(i, "work")

    @app_commands.command(name=key("cmd.pay.name"), description=key("cmd.pay.description"))
    @app_commands.guild_only()
    @app_commands.describe(user=key("arg.user"), amount=key("arg.amount_coins"))
    async def pay(self, i: discord.Interaction, user: discord.Member, amount: app_commands.Range[int, 1, 1_000_000_000]) -> None:
        cfg = await self._eco_or_reply(i)
        if cfg is None:
            return
        loc = self._loc(i.guild_id)
        if not cfg.transfers_enabled or user.bot:
            await i.response.send_message(t(loc, "eco.no_transfers"), ephemeral=True)
            return
        try:
            async with sessionmaker()() as db:
                bal = await transfer(db, i.guild_id or 0, i.user.id, user.id, amount, max_balance=cfg.max_balance,
                                     sender_name=i.user.display_name, receiver_name=user.display_name)
                await db.commit()
        except EconomyError as exc:
            await i.response.send_message(t(loc, f"eco.{exc.code}"), ephemeral=True)
            return
        await i.response.send_message(t(loc, "eco.paid", amount=f"{amount:,}", emoji=cfg.currency_emoji,
                                        user=user.mention, balance=f"{bal:,}"),
                                      allowed_mentions=discord.AllowedMentions(users=[user]))

    @app_commands.command(name=key("cmd.shop.name"), description=key("cmd.shop.description"))
    @app_commands.guild_only()
    async def shop(self, i: discord.Interaction) -> None:
        cfg = await self._eco_or_reply(i)
        if cfg is None:
            return
        assert i.guild
        loc = self._loc(i.guild_id)
        async with sessionmaker()() as db:
            items = (await db.scalars(select(EconomyItem).where(EconomyItem.guild_id == i.guild.id,
                                                                EconomyItem.enabled.is_(True)).order_by(EconomyItem.price))).all()
        e = discord.Embed(title=t(loc, "eco.shop_title", server=i.guild.name), color=0x7465F7)
        if not items:
            e.description = t(loc, "eco.shop_empty")
        for it in items[:25]:
            extra = []
            if it.stock is not None:
                extra.append(t(loc, "eco.stock", n=it.stock))
            if it.role_id:
                extra.append(t(loc, "eco.gives_role", role=f"<@&{it.role_id}>"))
            e.add_field(name=f"{it.name} · {it.price:,} {cfg.currency_emoji}",
                        value=" · ".join(filter(None, [it.description] + extra)) or "\u200b", inline=False)
        await i.response.send_message(embed=e, allowed_mentions=discord.AllowedMentions.none())

    async def item_autocomplete(self, i: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        async with sessionmaker()() as db:
            items = (await db.scalars(select(EconomyItem).where(
                EconomyItem.guild_id == (i.guild_id or 0), EconomyItem.enabled.is_(True),
                EconomyItem.name.ilike(f"%{current.replace('%', '')}%")).limit(25))).all()
        return [app_commands.Choice(name=f"{it.name} ({it.price:,})"[:100], value=str(it.id)) for it in items]

    @app_commands.command(name=key("cmd.buy.name"), description=key("cmd.buy.description"))
    @app_commands.guild_only()
    @app_commands.describe(item=key("arg.item"))
    @app_commands.autocomplete(item=item_autocomplete)
    async def buy(self, i: discord.Interaction, item: str) -> None:
        cfg = await self._eco_or_reply(i)
        if cfg is None:
            return
        assert i.guild and isinstance(i.user, discord.Member)
        loc = self._loc(i.guild_id)
        async with sessionmaker()() as db:
            it = await db.scalar(select(EconomyItem).where(EconomyItem.guild_id == i.guild.id, EconomyItem.enabled.is_(True),
                                                           (EconomyItem.id == int(item)) if item.isdigit()
                                                           else EconomyItem.name.ilike(item)).with_for_update())
            if it is None:
                await i.response.send_message(t(loc, "eco.not_found"), ephemeral=True)
                return
            if it.stock is not None and it.stock <= 0:
                await i.response.send_message(t(loc, "eco.sold_out"), ephemeral=True)
                return
            try:
                bal = await change_balance(db, i.guild.id, i.user.id, -it.price, "buy", reference=str(it.id),
                                           user_name=i.user.display_name)
            except EconomyError as exc:
                await i.response.send_message(t(loc, f"eco.{exc.code}"), ephemeral=True)
                return
            if it.stock is not None:
                it.stock -= 1
            await db.execute(insert(EconomyInventory).values(guild_id=i.guild.id, user_id=i.user.id, item_id=it.id,
                                                             quantity=1).on_conflict_do_update(
                index_elements=["guild_id", "user_id", "item_id"], set_={"quantity": EconomyInventory.quantity + 1}))
            await db.commit()
        msg = t(loc, "eco.bought", item=it.name, price=f"{it.price:,}", emoji=cfg.currency_emoji, balance=f"{bal:,}")
        if it.role_id:
            role = i.guild.get_role(it.role_id)
            given = False
            if role is not None and role < i.guild.me.top_role:
                try:
                    await i.user.add_roles(role, reason="NEXUS shop")
                    given = True
                except discord.HTTPException:
                    pass
            if not given:
                msg += "\n" + t(loc, "eco.role_failed")
        await i.response.send_message(msg)


    # --- Ajustes del staff: /xp y /dinero ---------------------------------------
    xp_group = app_commands.Group(name=key("cmd.xp.name"), description=key("cmd.xp.description"),
                                  guild_only=True, default_permissions=discord.Permissions(manage_guild=True))
    money_group = app_commands.Group(name=key("cmd.money.name"), description=key("cmd.money.description"),
                                     guild_only=True, default_permissions=discord.Permissions(manage_guild=True))

    async def _adjust_xp(self, i: discord.Interaction, user: discord.Member, amount: int) -> None:
        loc = self._loc(i.guild_id)
        if not i.guild_id or self._levels(i.guild_id) is None:
            await i.response.send_message(t(loc, "levels.disabled"), ephemeral=True)
            return
        async with sessionmaker()() as db:
            await db.execute(insert(MemberXP).values(guild_id=i.guild_id, user_id=user.id,
                                                     user_name=user.display_name).on_conflict_do_nothing())
            row = await db.scalar(select(MemberXP).where(MemberXP.guild_id == i.guild_id,
                                                         MemberXP.user_id == user.id).with_for_update())
            assert row is not None
            row.xp = max(0, row.xp + amount)
            row.level = level_from_xp(row.xp)[0]
            xp, level = row.xp, row.level
            await db.commit()
        await i.response.send_message(f"✅ {t(loc, 'xp.changed', user=user.mention, xp=xp, level=level)}",
                                      ephemeral=True)

    @xp_group.command(name=key("cmd.xp_add.name"), description=key("cmd.xp_add.description"))
    @app_commands.describe(user=key("arg.user"), amount=key("arg.xp_amount"))
    async def xp_add(self, i: discord.Interaction, user: discord.Member,
                     amount: app_commands.Range[int, 1, 1_000_000]) -> None:
        await self._adjust_xp(i, user, amount)

    @xp_group.command(name=key("cmd.xp_remove.name"), description=key("cmd.xp_remove.description"))
    @app_commands.describe(user=key("arg.user"), amount=key("arg.xp_amount"))
    async def xp_remove(self, i: discord.Interaction, user: discord.Member,
                        amount: app_commands.Range[int, 1, 1_000_000]) -> None:
        await self._adjust_xp(i, user, -amount)

    @xp_group.command(name=key("cmd.xp_reset.name"), description=key("cmd.xp_reset.description"))
    @app_commands.describe(user=key("arg.user"))
    async def xp_reset(self, i: discord.Interaction, user: discord.Member) -> None:
        await self._adjust_xp(i, user, -10**12)  # baja a 0 (el ajuste nunca deja la XP en negativo)

    async def _adjust_money(self, i: discord.Interaction, user: discord.Member, amount: int) -> None:
        cfg = await self._eco_or_reply(i)
        if cfg is None or not i.guild_id:
            return
        async with sessionmaker()() as db:
            balance = await change_balance(db, i.guild_id, user.id, amount, "admin", max_balance=cfg.max_balance,
                                           start_balance=cfg.start_balance, user_name=user.display_name, clamp=True)
            await db.commit()
        loc = self._loc(i.guild_id)
        await i.response.send_message(
            f"✅ {t(loc, 'money.changed', user=user.mention, balance=balance, currency=cfg.currency_name)}",
            ephemeral=True)

    @money_group.command(name=key("cmd.money_add.name"), description=key("cmd.money_add.description"))
    @app_commands.describe(user=key("arg.user"), amount=key("arg.amount_coins"))
    async def money_add(self, i: discord.Interaction, user: discord.Member,
                        amount: app_commands.Range[int, 1, 1_000_000_000]) -> None:
        await self._adjust_money(i, user, amount)

    @money_group.command(name=key("cmd.money_remove.name"), description=key("cmd.money_remove.description"))
    @app_commands.describe(user=key("arg.user"), amount=key("arg.amount_coins"))
    async def money_remove(self, i: discord.Interaction, user: discord.Member,
                           amount: app_commands.Range[int, 1, 1_000_000_000]) -> None:
        await self._adjust_money(i, user, -amount)

async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Progression(bot))


