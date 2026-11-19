"""Juegos (piedra-papel-tijera, tres en raya, ship) y extras de economía (semanal, inventario, apuestas, robos)."""

from __future__ import annotations

import hashlib
import random
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from nexus_core.db import sessionmaker
from nexus_core.db.models import EconomyInventory, EconomyItem
from nexus_core.db.repo import utcnow
from nexus_core.economy import change_balance, wallet_for_update
from nexus_core.i18n import t
from nexus_core.modules import parse_config
from nexus_core.modules.progression import EconomyConfig

from nexus_bot import groups
from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

SLOT_SYMBOLS = ["🍒", "🍋", "🍇", "🔔", "⭐", "💎"]
SLOT_MULT = {"💎": 10, "⭐": 5, "🔔": 4}  # tres iguales; el resto paga x3
ROB_COOLDOWN = timedelta(hours=2)
CRIME_COOLDOWN = timedelta(hours=1)
WEEKLY_COOLDOWN = timedelta(days=7)
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def slot_result(reels: list[str]) -> int:
    """Multiplicador bruto de la tirada: 0 = pierde; 1 = recupera la apuesta; >1 = gana."""
    if reels[0] == reels[1] == reels[2]:
        return SLOT_MULT.get(reels[0], 3)
    if len(set(reels)) == 2:
        return 1
    return 0


def ttt_winner(board: list[int]) -> int:
    """0 = nadie aún, 1 = X, 2 = O, 3 = empate."""
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return 3 if all(board) else 0


def ship_percent(a: int, b: int) -> int:
    """Siempre el mismo resultado para la misma pareja (en cualquier orden)."""
    lo, hi = sorted((a, b))
    return int(hashlib.sha256(f"{lo}:{hi}".encode()).hexdigest(), 16) % 101


class TicTacToe(discord.ui.View):
    def __init__(self, loc: str, x: discord.abc.User, o: discord.abc.User) -> None:
        super().__init__(timeout=180)
        self.loc, self.players = loc, {1: x, 2: o}
        self.board = [0] * 9
        self.turn = 1
        self.message: discord.Message | None = None
        for n in range(9):
            btn = discord.ui.Button(label="\u200b", style=discord.ButtonStyle.secondary, row=n // 3)
            btn.callback = self._make_move(n)  # type: ignore[method-assign]
            self.add_item(btn)

    def header(self, status: str) -> str:
        return f"{t(self.loc, 'ttt.title', x=self.players[1].mention, o=self.players[2].mention)}\n{status}"

    def _make_move(self, n: int):  # type: ignore[no-untyped-def]
        async def move(interaction: discord.Interaction) -> None:
            if interaction.user.id != self.players[self.turn].id or self.board[n]:
                await interaction.response.send_message(t(self.loc, "ttt.not_yours"), ephemeral=True)
                return
            self.board[n] = self.turn
            btn = self.children[n]
            assert isinstance(btn, discord.ui.Button)
            btn.label = "❌" if self.turn == 1 else "⭕"
            btn.style = discord.ButtonStyle.danger if self.turn == 1 else discord.ButtonStyle.primary
            btn.disabled = True
            result = ttt_winner(self.board)
            if result:
                for item in self.children:
                    item.disabled = True  # type: ignore[attr-defined]
                status = t(self.loc, "ttt.draw") if result == 3 else t(self.loc, "ttt.win",
                                                                      user=self.players[result].mention)
                self.stop()
            else:
                self.turn = 2 if self.turn == 1 else 1
                status = t(self.loc, "ttt.turn", user=self.players[self.turn].mention)
            await interaction.response.edit_message(content=self.header(status), view=self,
                                                    allowed_mentions=discord.AllowedMentions.none())
        return move

    async def on_timeout(self) -> None:
        if self.message:
            for item in self.children:
                item.disabled = True  # type: ignore[attr-defined]
            try:
                await self.message.edit(content=self.header(t(self.loc, "ttt.timeout")), view=self)
            except discord.HTTPException:
                pass


class Games(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        groups.bind(self, self.rps, self.ttt, self.ship)

    def loc(self, i: discord.Interaction) -> str:
        if i.guild_id:
            return self.bot.cache.get(i.guild_id).locale
        return "es" if str(i.locale).startswith("es") else "en"

    # --- Juegos -----------------------------------------------------------------------
    @groups.fun.command(name=key("sub.fun.rps"), description=key("cmd.rps.description"))
    @app_commands.describe(choice=key("arg.rps_choice"))
    @app_commands.choices(choice=[app_commands.Choice(name=key("rps.rock"), value="rock"),
                                  app_commands.Choice(name=key("rps.paper"), value="paper"),
                                  app_commands.Choice(name=key("rps.scissors"), value="scissors")])
    async def rps(self, i: discord.Interaction, choice: app_commands.Choice[str]) -> None:
        loc = self.loc(i)
        bot_pick = random.choice(list(RPS_BEATS))
        you = choice.value
        outcome = "rps.draw" if you == bot_pick else ("rps.win" if RPS_BEATS[you] == bot_pick else "rps.lose")
        await i.response.send_message(t(loc, "rps.result", you=t(loc, f"rps.{you}"), bot=t(loc, f"rps.{bot_pick}"),
                                        outcome=t(loc, outcome)))

    @groups.fun.command(name=key("sub.fun.ttt"), description=key("cmd.ttt.description"))
    @app_commands.describe(opponent=key("arg.opponent"))
    async def ttt(self, i: discord.Interaction, opponent: discord.Member) -> None:
        loc = self.loc(i)
        if opponent.bot or opponent.id == i.user.id:
            await i.response.send_message(t(loc, "ttt.bad_opponent"), ephemeral=True)
            return
        view = TicTacToe(loc, i.user, opponent)
        await i.response.send_message(view.header(t(loc, "ttt.turn", user=i.user.mention)), view=view,
                                      allowed_mentions=discord.AllowedMentions(users=[opponent]))
        view.message = await i.original_response()

    @groups.fun.command(name=key("sub.fun.ship"), description=key("cmd.ship.description"))
    @app_commands.describe(user1=key("arg.user1"), user2=key("arg.user2"))
    async def ship(self, i: discord.Interaction, user1: discord.User, user2: discord.User | None = None) -> None:
        other = user2 or i.user
        pct = ship_percent(user1.id, other.id)
        bar = "❤️" * (pct // 10) + "🤍" * (10 - pct // 10)
        await i.response.send_message(t(self.loc(i), "ship.result", a=user1.display_name, b=other.display_name,
                                        pct=pct, bar=bar), allowed_mentions=discord.AllowedMentions.none())

    # --- Economía ----------------------------------------------------------------------
    async def _eco(self, i: discord.Interaction) -> EconomyConfig | None:
        state = self.bot.cache.get(i.guild_id or 0)
        mod = state.module("economy")
        if mod is None:
            await i.response.send_message(t(self.loc(i), "eco.disabled"), ephemeral=True)
            return None
        return parse_config("economy", mod.config, state.locale)  # type: ignore[return-value]

    def _fmt(self, n: int) -> str:
        return f"{n:,}"

    @app_commands.command(name=key("cmd.weekly.name"), description=key("cmd.weekly.description"))
    @app_commands.guild_only()
    async def weekly(self, i: discord.Interaction) -> None:
        cfg = await self._eco(i)
        if cfg is None:
            return
        loc, now = self.loc(i), utcnow()
        async with sessionmaker()() as db:
            w = await wallet_for_update(db, i.guild_id or 0, i.user.id, start_balance=cfg.start_balance,
                                        user_name=i.user.display_name)
            if w.last_weekly_at and now - w.last_weekly_at < WEEKLY_COOLDOWN:
                await db.rollback()
                when = f"<t:{int((w.last_weekly_at + WEEKLY_COOLDOWN).timestamp())}:R>"
                await i.response.send_message(t(loc, "eco.weekly_wait", when=when), ephemeral=True)
                return
            w.last_weekly_at = now
            bal = await change_balance(db, i.guild_id or 0, i.user.id, cfg.weekly_amount, "weekly",
                                       max_balance=cfg.max_balance)
            await db.commit()
        await i.response.send_message(t(loc, "eco.weekly", amount=self._fmt(cfg.weekly_amount),
                                        emoji=cfg.currency_emoji, balance=self._fmt(bal)))

    @app_commands.command(name=key("cmd.inventory.name"), description=key("cmd.inventory.description"))
    @app_commands.guild_only()
    @app_commands.describe(user=key("arg.target_user"))
    async def inventory(self, i: discord.Interaction, user: discord.Member | None = None) -> None:
        cfg = await self._eco(i)
        if cfg is None:
            return
        who = user or i.user
        loc = self.loc(i)
        async with sessionmaker()() as db:
            rows = (await db.execute(select(EconomyItem.name, EconomyInventory.quantity)
                                     .join(EconomyItem, EconomyItem.id == EconomyInventory.item_id)
                                     .where(EconomyInventory.guild_id == i.guild_id,
                                            EconomyInventory.user_id == who.id)
                                     .order_by(EconomyItem.name))).all()
        e = discord.Embed(title=t(loc, "inv.title", user=who.display_name),
                          color=self.bot.cache.get(i.guild_id or 0).embed_color)
        e.description = "\n".join(f"• **{name}** × {qty}" for name, qty in rows) or t(loc, "inv.empty")
        await i.response.send_message(embed=e, ephemeral=True)

    async def _check_bet(self, i: discord.Interaction, cfg: EconomyConfig, amount: int) -> bool:
        loc = self.loc(i)
        if not cfg.gambling_enabled:
            await i.response.send_message(t(loc, "eco.gambling_off"), ephemeral=True)
            return False
        if amount > cfg.max_bet:
            await i.response.send_message(t(loc, "eco.max_bet", max=self._fmt(cfg.max_bet)), ephemeral=True)
            return False
        return True

    async def _settle(self, i: discord.Interaction, cfg: EconomyConfig, bet: int, profit: int) -> int | None:
        """Aplica el resultado de una apuesta en una sola transacción; None si no tenía saldo."""
        async with sessionmaker()() as db:
            w = await wallet_for_update(db, i.guild_id or 0, i.user.id, start_balance=cfg.start_balance,
                                        user_name=i.user.display_name)
            if w.balance < bet:
                await db.rollback()
                return None
            bal = await change_balance(db, i.guild_id or 0, i.user.id, profit, "gamble", max_balance=cfg.max_balance)
            await db.commit()
            return bal

    @app_commands.command(name=key("cmd.bet.name"), description=key("cmd.bet.description"))
    @app_commands.guild_only()
    @app_commands.describe(amount=key("arg.bet"), side=key("arg.side"))
    @app_commands.choices(side=[app_commands.Choice(name=key("fun.heads"), value="heads"),
                                app_commands.Choice(name=key("fun.tails"), value="tails")])
    async def bet(self, i: discord.Interaction, amount: app_commands.Range[int, 1, 1_000_000_000],
                  side: app_commands.Choice[str]) -> None:
        cfg = await self._eco(i)
        if cfg is None or not await self._check_bet(i, cfg, amount):
            return
        loc = self.loc(i)
        result = random.choice(("heads", "tails"))
        won = result == side.value
        bal = await self._settle(i, cfg, amount, amount if won else -amount)
        if bal is None:
            await i.response.send_message(t(loc, "eco.no_funds"), ephemeral=True)
            return
        await i.response.send_message(t(loc, "bet.win" if won else "bet.lose", side=t(loc, f"fun.{result}"),
                                        amount=self._fmt(amount), emoji=cfg.currency_emoji, balance=self._fmt(bal)))

    @app_commands.command(name=key("cmd.slots.name"), description=key("cmd.slots.description"))
    @app_commands.guild_only()
    @app_commands.describe(amount=key("arg.bet"))
    async def slots(self, i: discord.Interaction, amount: app_commands.Range[int, 1, 1_000_000_000]) -> None:
        cfg = await self._eco(i)
        if cfg is None or not await self._check_bet(i, cfg, amount):
            return
        loc = self.loc(i)
        reels = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
        mult = slot_result(reels)
        profit = amount * (mult - 1) if mult else -amount
        bal = await self._settle(i, cfg, amount, profit)
        if bal is None:
            await i.response.send_message(t(loc, "eco.no_funds"), ephemeral=True)
            return
        text = " | ".join(reels)
        if mult > 1:
            msg = t(loc, "slots.win", reels=text, mult=mult, amount=self._fmt(profit), emoji=cfg.currency_emoji,
                    balance=self._fmt(bal))
        elif mult == 1:
            msg = t(loc, "slots.win", reels=text, mult=1, amount=0, emoji=cfg.currency_emoji, balance=self._fmt(bal))
        else:
            msg = t(loc, "slots.lose", reels=text, amount=self._fmt(amount), emoji=cfg.currency_emoji,
                    balance=self._fmt(bal))
        await i.response.send_message(msg)

    @app_commands.command(name=key("cmd.rob.name"), description=key("cmd.rob.description"))
    @app_commands.guild_only()
    @app_commands.describe(user=key("arg.user"))
    async def rob(self, i: discord.Interaction, user: discord.Member) -> None:
        cfg = await self._eco(i)
        if cfg is None:
            return
        loc, now, gid = self.loc(i), utcnow(), i.guild_id or 0
        if not cfg.rob_enabled:
            await i.response.send_message(t(loc, "eco.rob_off"), ephemeral=True)
            return
        if user.id == i.user.id or user.bot:
            await i.response.send_message(t(loc, "rob.self"), ephemeral=True)
            return
        async with sessionmaker()() as db:
            # Bloqueo en orden de ID para que dos robos cruzados no se queden esperando entre sí.
            first, second = sorted((i.user.id, user.id))
            wallets = {}
            for uid in (first, second):
                wallets[uid] = await wallet_for_update(db, gid, uid, start_balance=cfg.start_balance)
            me, victim = wallets[i.user.id], wallets[user.id]
            if me.last_rob_at and now - me.last_rob_at < ROB_COOLDOWN:
                await db.rollback()
                when = f"<t:{int((me.last_rob_at + ROB_COOLDOWN).timestamp())}:R>"
                await i.response.send_message(t(loc, "rob.wait", when=when), ephemeral=True)
                return
            if victim.balance < 100:
                await db.rollback()
                await i.response.send_message(t(loc, "rob.poor", user=user.display_name), ephemeral=True)
                return
            me.last_rob_at = now
            if random.random() < 0.45:
                amount = max(1, int(victim.balance * random.uniform(0.1, 0.3)))
                await change_balance(db, gid, user.id, -amount, "robbed", clamp=True)
                await change_balance(db, gid, i.user.id, amount, "rob", max_balance=cfg.max_balance)
                msg = t(loc, "rob.ok", amount=self._fmt(amount), emoji=cfg.currency_emoji, user=user.mention)
            else:
                fine = max(50, int(me.balance * random.uniform(0.1, 0.2)))
                await change_balance(db, gid, i.user.id, -fine, "fine", clamp=True)
                msg = t(loc, "rob.fail", amount=self._fmt(fine), emoji=cfg.currency_emoji)
            await db.commit()
        await i.response.send_message(msg, allowed_mentions=discord.AllowedMentions(users=[user]))

    @app_commands.command(name=key("cmd.crime.name"), description=key("cmd.crime.description"))
    @app_commands.guild_only()
    async def crime(self, i: discord.Interaction) -> None:
        cfg = await self._eco(i)
        if cfg is None:
            return
        loc, now, gid = self.loc(i), utcnow(), i.guild_id or 0
        if not cfg.rob_enabled:
            await i.response.send_message(t(loc, "eco.rob_off"), ephemeral=True)
            return
        async with sessionmaker()() as db:
            w = await wallet_for_update(db, gid, i.user.id, start_balance=cfg.start_balance,
                                        user_name=i.user.display_name)
            if w.last_crime_at and now - w.last_crime_at < CRIME_COOLDOWN:
                await db.rollback()
                when = f"<t:{int((w.last_crime_at + CRIME_COOLDOWN).timestamp())}:R>"
                await i.response.send_message(t(loc, "rob.wait", when=when), ephemeral=True)
                return
            w.last_crime_at = now
            base = max(cfg.work_max, 50)
            if random.random() < 0.55:
                amount = random.randint(base * 2, base * 5)
                bal = await change_balance(db, gid, i.user.id, amount, "crime", max_balance=cfg.max_balance)
                msg = t(loc, "crime.ok", amount=self._fmt(amount), emoji=cfg.currency_emoji, balance=self._fmt(bal))
            else:
                fine = random.randint(base, base * 3)
                bal = await change_balance(db, gid, i.user.id, -fine, "fine", clamp=True)
                msg = t(loc, "crime.fail", amount=self._fmt(fine), emoji=cfg.currency_emoji, balance=self._fmt(bal))
            await db.commit()
        await i.response.send_message(msg)


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Games(bot))
