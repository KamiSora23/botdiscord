"""Sugerencias, sorteos, encuestas y Starboard."""

from __future__ import annotations

import hashlib
import logging
import random
import re
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Literal

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from nexus_core.db import sessionmaker
from nexus_core.db.models import Giveaway, GiveawayEntry, ScheduledJob, StarboardEntry, Suggestion, SuggestionVote
from nexus_core.db.repo import next_number, utcnow
from nexus_core.i18n import t
from nexus_core.modules import parse_config
from nexus_core.modules.community import GiveawaysConfig, PollsConfig, StarboardConfig, SuggestionsConfig

from nexus_bot.modservice import parse_duration
from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.community")


def _norm_emoji(e: str) -> str:
    """⭐ puede llegar con o sin el selector de variación U+FE0F según el cliente."""
    return e.replace("\ufe0f", "")

STATUS_COLORS = {"pending": 0x7465F7, "approved": 0x22C55E, "denied": 0xEF4444, "in_progress": 0xF59E0B,
                 "implemented": 0x06B6D4}


def pick_winners(entries: list[int], count: int, seed: str) -> list[int]:
    """Sorteo verificable: con la misma semilla y participantes, siempre salen los mismos ganadores."""
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))
    pool = sorted(entries)
    return rng.sample(pool, min(count, len(pool)))


class VoteButton(discord.ui.DynamicItem[discord.ui.Button], template=r"nexus:sg:(?P<vote>up|down):(?P<sid>\d+)"):
    def __init__(self, vote: str, sid: int, count: int = 0) -> None:
        super().__init__(discord.ui.Button(
            emoji="👍" if vote == "up" else "👎", label=str(count),
            style=discord.ButtonStyle.success if vote == "up" else discord.ButtonStyle.danger,
            custom_id=f"nexus:sg:{vote}:{sid}"))
        self.vote, self.sid = vote, sid

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):  # type: ignore[no-untyped-def]
        inst = cls.__new__(cls)
        discord.ui.DynamicItem.__init__(inst, item)
        inst.vote, inst.sid = match["vote"], int(match["sid"])
        return inst

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Community = interaction.client.get_cog("Community")  # type: ignore[union-attr,assignment]
        await cog.vote(interaction, self.sid, 1 if self.vote == "up" else -1)


class JoinButton(discord.ui.DynamicItem[discord.ui.Button], template=r"nexus:gw:(?P<gid>\d+)"):
    def __init__(self, gid: int, label: str) -> None:
        super().__init__(discord.ui.Button(emoji="🎉", label=label, style=discord.ButtonStyle.primary,
                                           custom_id=f"nexus:gw:{gid}"))
        self.gid = gid

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):  # type: ignore[no-untyped-def]
        inst = cls.__new__(cls)
        discord.ui.DynamicItem.__init__(inst, item)
        inst.gid = int(match["gid"])
        return inst

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Community = interaction.client.get_cog("Community")  # type: ignore[union-attr,assignment]
        await cog.toggle_entry(interaction, self.gid)


class Community(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        bot.add_dynamic_items(VoteButton, JoinButton)
        bot.rpc_handlers.update({
            "suggestions.respond": self.rpc_respond,
            "giveaways.create": self.rpc_giveaway_create,
            "giveaways.end": self.rpc_giveaway_end,
            "giveaways.reroll": self.rpc_giveaway_reroll,
            "giveaways.cancel": self.rpc_giveaway_cancel,
            "polls.create": self.rpc_poll,
        })
        bot.job_handlers["giveaway.end"] = self.job_giveaway_end

    def _loc(self, guild_id: int | None) -> str:
        return self.bot.cache.get(guild_id or 0).locale

    def _cfg(self, guild_id: int, module: str) -> Any:
        state = self.bot.cache.get(guild_id)
        mod = state.module(module)
        return parse_config(module, mod.config, state.locale) if mod else None

    # --- Sugerencias -------------------------------------------------------
    def _suggestion_embed(self, s: Suggestion, loc: str, color: int | None = None) -> discord.Embed:
        cfg: SuggestionsConfig | None = self._cfg(s.guild_id, "suggestions")
        e = discord.Embed(title=t(loc, "sg.title", number=s.number), description=s.content,
                          color=color or STATUS_COLORS.get(s.status, 0x7465F7))
        e.set_author(name=t(loc, "sg.anonymous") if cfg and cfg.anonymous else s.author_name)
        e.add_field(name=t(loc, "sg.status"), value=t(loc, f"sg.status_{s.status}"))
        if s.staff_response:
            e.add_field(name=t(loc, "sg.response"), value=s.staff_response[:1024], inline=False)
        e.timestamp = s.created_at
        return e

    def _vote_view(self, s: Suggestion) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        if s.status in ("pending", "in_progress"):
            view.add_item(VoteButton("up", s.id, s.upvotes))
            view.add_item(VoteButton("down", s.id, s.downvotes))
        return view

    @app_commands.command(name=key("cmd.suggest.name"), description=key("cmd.suggest.description"))
    @app_commands.guild_only()
    @app_commands.describe(text=key("arg.suggestion"))
    async def suggest(self, interaction: discord.Interaction, text: app_commands.Range[str, 5, 1500]) -> None:
        assert interaction.guild
        loc = self._loc(interaction.guild_id)
        cfg: SuggestionsConfig | None = self._cfg(interaction.guild.id, "suggestions")
        channel = interaction.guild.get_channel(cfg.channel_id or 0) if cfg else None
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(t(loc, "sg.disabled"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        async with sessionmaker()() as db:
            s = Suggestion(guild_id=interaction.guild.id, number=await next_number(db, Suggestion, interaction.guild.id),
                           author_id=interaction.user.id, author_name=str(interaction.user), content=text,
                           channel_id=channel.id)
            db.add(s)
            await db.flush()
            msg = await channel.send(embed=self._suggestion_embed(s, loc), view=self._vote_view(s))
            s.message_id = msg.id
            await db.commit()
        if cfg and cfg.create_thread:
            try:
                await msg.create_thread(name=f"#{s.number} · {text[:80]}")
            except discord.HTTPException:
                pass
        await interaction.followup.send(t(loc, "sg.sent", number=s.number), ephemeral=True)

    async def vote(self, interaction: discord.Interaction, sid: int, value: int) -> None:
        loc = self._loc(interaction.guild_id)
        async with sessionmaker()() as db:
            s = await db.get(Suggestion, sid)
            if s is None or s.status not in ("pending", "in_progress"):
                await interaction.response.send_message("❌", ephemeral=True)
                return
            current = await db.get(SuggestionVote, (sid, interaction.user.id))
            if current and current.vote == value:
                await db.delete(current)
                msg = t(loc, "sg.unvoted")
            else:
                await db.execute(insert(SuggestionVote).values(suggestion_id=sid, user_id=interaction.user.id, vote=value)
                                 .on_conflict_do_update(index_elements=["suggestion_id", "user_id"], set_={"vote": value}))
                msg = t(loc, "sg.voted")
            await db.flush()
            s.upvotes = await db.scalar(select(func.count()).select_from(SuggestionVote).where(
                SuggestionVote.suggestion_id == sid, SuggestionVote.vote == 1)) or 0
            s.downvotes = await db.scalar(select(func.count()).select_from(SuggestionVote).where(
                SuggestionVote.suggestion_id == sid, SuggestionVote.vote == -1)) or 0
            await db.commit()
        await interaction.response.edit_message(view=self._vote_view(s))
        await interaction.followup.send(msg, ephemeral=True)

    async def set_status(self, guild_id: int, number: int, status: str, response: str | None,
                         staff_id: int) -> Suggestion | None:
        async with sessionmaker()() as db:
            s = await db.scalar(select(Suggestion).where(Suggestion.guild_id == guild_id, Suggestion.number == number))
            if s is None:
                return None
            s.status, s.staff_response, s.responded_by, s.updated_at = status, response, staff_id, utcnow()
            await db.commit()
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(s.channel_id or 0) if guild else None
        if isinstance(channel, discord.TextChannel) and s.message_id:
            try:
                msg = channel.get_partial_message(s.message_id)
                await msg.edit(embed=self._suggestion_embed(s, self._loc(guild_id)), view=self._vote_view(s))
            except discord.HTTPException:
                pass
        return s

    @app_commands.command(name=key("cmd.suggestion.name"), description=key("cmd.suggestion.description"))
    @app_commands.guild_only()
    @app_commands.describe(number=key("arg.number"), status=key("arg.status"), response=key("arg.response"))
    async def respond(self, interaction: discord.Interaction, number: int,
                      status: Literal["approved", "denied", "in_progress", "implemented", "pending"],
                      response: str | None = None) -> None:
        assert interaction.guild and isinstance(interaction.user, discord.Member)
        loc = self._loc(interaction.guild_id)
        cfg: SuggestionsConfig | None = self._cfg(interaction.guild.id, "suggestions")
        perms = interaction.user.guild_permissions
        if not (perms.manage_guild or perms.manage_messages or
                (cfg and {r.id for r in interaction.user.roles} & set(cfg.staff_role_ids))):
            await interaction.response.send_message(t(loc, "sg.staff_only"), ephemeral=True)
            return
        s = await self.set_status(interaction.guild.id, number, status, response, interaction.user.id)
        await interaction.response.send_message(t(loc, "sg.updated" if s else "sg.not_found", number=number),
                                                ephemeral=True)

    async def rpc_respond(self, params: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        s = await self.set_status(int(params["guild_id"]), int(params["number"]), params["status"],
                                  params.get("response"), int(params["staff_id"]))
        if s is None:
            raise RpcFailure("not_found")
        return {"status": s.status}

    # --- Sorteos -------------------------------------------------------------
    def _giveaway_embed(self, g: Giveaway, loc: str, entries: int | None = None) -> discord.Embed:
        e = discord.Embed(title=t(loc, "gw.title", prize=g.prize), color=0xEC4899)
        body = g.description + "\n\n" if g.description else ""
        if g.ended:
            winners = ", ".join(f"<@{w}>" for w in g.winner_ids) or t(loc, "gw.no_entries")
            e.description = body + t(loc, "gw.winners", winners=winners)
            e.set_footer(text=t(loc, "gw.ended"))
        else:
            e.description = body + t(loc, "gw.body", ends=f"<t:{int(g.ends_at.timestamp())}:R>", count=g.winner_count)
            if g.required_role_ids:
                e.add_field(name="\u200b", value=t(loc, "gw.requirements",
                                                   roles=", ".join(f"<@&{r}>" for r in g.required_role_ids)))
        if entries is not None:
            e.set_footer(text=f"{entries} 🎟️")
        e.timestamp = g.ends_at
        return e

    async def create_giveaway(self, guild: discord.Guild, channel_id: int, prize: str, duration: int, winners: int,
                              host_id: int, description: str | None = None,
                              required_role_ids: list[int] | None = None) -> Giveaway:
        from nexus_bot.client import RpcFailure

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise RpcFailure("channel_not_found")
        loc = self._loc(guild.id)
        cfg: GiveawaysConfig | None = self._cfg(guild.id, "giveaways")
        async with sessionmaker()() as db:
            g = Giveaway(guild_id=guild.id, channel_id=channel_id, prize=prize, description=description,
                         winner_count=winners, host_id=host_id, required_role_ids=required_role_ids or [],
                         ends_at=utcnow() + timedelta(seconds=duration))
            db.add(g)
            await db.flush()
            view = discord.ui.View(timeout=None)
            view.add_item(JoinButton(g.id, t(loc, "gw.join")))
            ping = f"<@&{cfg.ping_role_id}>" if cfg and cfg.ping_role_id else None
            try:
                msg = await channel.send(content=ping, embed=self._giveaway_embed(g, loc), view=view,
                                         allowed_mentions=discord.AllowedMentions(roles=True))
            except discord.Forbidden as exc:
                raise RpcFailure("bot_cannot_send") from exc
            g.message_id = msg.id
            db.add(ScheduledJob(guild_id=guild.id, job_type="giveaway.end", run_at=g.ends_at,
                                payload={"giveaway_id": str(g.id)}, dedupe_key=f"giveaway.end:{g.id}"))
            await db.commit()
        return g

    async def toggle_entry(self, interaction: discord.Interaction, gid: int) -> None:
        loc = self._loc(interaction.guild_id)
        async with sessionmaker()() as db:
            g = await db.get(Giveaway, gid)
            if g is None or g.ended:
                await interaction.response.send_message(t(loc, "gw.ended"), ephemeral=True)
                return
            member = interaction.user
            if g.required_role_ids and isinstance(member, discord.Member) and \
                    not {r.id for r in member.roles} & set(g.required_role_ids):
                await interaction.response.send_message(
                    t(loc, "gw.missing_role", roles=", ".join(f"<@&{r}>" for r in g.required_role_ids)),
                    ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                return
            existing = await db.get(GiveawayEntry, (gid, member.id))
            if existing:
                await db.delete(existing)
            else:
                db.add(GiveawayEntry(giveaway_id=gid, user_id=member.id))
            await db.flush()
            count = await db.scalar(select(func.count()).select_from(GiveawayEntry).where(GiveawayEntry.giveaway_id == gid))
            await db.commit()
        await interaction.response.send_message(t(loc, "gw.left") if existing else t(loc, "gw.joined", count=count),
                                                ephemeral=True)

    async def end_giveaway(self, gid: int, *, reroll: bool = False) -> Giveaway | None:
        async with sessionmaker()() as db:
            g = await db.get(Giveaway, gid)
            if g is None or (g.ended and not reroll):
                return g
            entries = list((await db.scalars(select(GiveawayEntry.user_id).where(GiveawayEntry.giveaway_id == gid))).all())
            g.seed = secrets.token_hex(16)
            g.winner_ids = pick_winners(entries, g.winner_count, g.seed)
            g.ended = True
            await db.commit()
        guild = self.bot.get_guild(g.guild_id)
        channel = guild.get_channel(g.channel_id) if guild else None
        if isinstance(channel, (discord.TextChannel, discord.Thread)) and g.message_id:
            loc = self._loc(g.guild_id)
            try:
                msg = channel.get_partial_message(g.message_id)
                await msg.edit(embed=self._giveaway_embed(g, loc, len(entries)), view=None)
                if g.winner_ids:
                    await msg.reply(t(loc, "gw.congrats", winners=", ".join(f"<@{w}>" for w in g.winner_ids),
                                      prize=g.prize), allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                pass
        return g

    async def job_giveaway_end(self, job: ScheduledJob) -> None:
        await self.end_giveaway(int(job.payload["giveaway_id"]))

    @app_commands.command(name=key("cmd.giveaway.name"), description=key("cmd.giveaway.description"))
    @app_commands.guild_only()
    @app_commands.describe(prize=key("arg.prize"), duration=key("arg.duration"), winners=key("arg.winners"),
                           channel=key("arg.channel"))
    async def giveaway(self, interaction: discord.Interaction, prize: str, duration: str,
                       winners: app_commands.Range[int, 1, 20] = 1, channel: discord.TextChannel | None = None) -> None:
        from nexus_bot.client import RpcFailure

        assert interaction.guild
        loc = self._loc(interaction.guild_id)
        cfg: GiveawaysConfig | None = self._cfg(interaction.guild.id, "giveaways")
        if cfg is None:
            await interaction.response.send_message(t(loc, "mod.module_disabled"), ephemeral=True)
            return
        member = interaction.user
        if not (isinstance(member, discord.Member) and (member.guild_permissions.manage_guild or
                                                        {r.id for r in member.roles} & set(cfg.manager_role_ids))):
            await interaction.response.send_message(t(loc, "gw.manager_only"), ephemeral=True)
            return
        seconds = parse_duration(duration)
        if not seconds or seconds < 60:
            await interaction.response.send_message(t(loc, "mod.err_duration"), ephemeral=True)
            return
        target = channel or interaction.channel
        try:
            await self.create_giveaway(interaction.guild, target.id, prize[:200], seconds, winners, interaction.user.id)  # type: ignore[union-attr]
        except RpcFailure:
            await interaction.response.send_message(t(loc, "error.bot_cannot_send"), ephemeral=True)
            return
        await interaction.response.send_message(t(loc, "gw.created", channel=target.mention), ephemeral=True)  # type: ignore[union-attr]

    async def rpc_giveaway_create(self, p: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(p["guild_id"]))
        if guild is None or self._cfg(guild.id, "giveaways") is None:
            raise RpcFailure("module_disabled")
        g = await self.create_giveaway(guild, int(p["channel_id"]), p["prize"], int(p["duration_seconds"]),
                                       int(p["winner_count"]), int(p["host_id"]), p.get("description"),
                                       [int(x) for x in p.get("required_role_ids", [])])
        return {"id": str(g.id)}

    async def _owned(self, p: dict[str, Any]) -> Giveaway:
        from nexus_bot.client import RpcFailure

        async with sessionmaker()() as db:
            g = await db.get(Giveaway, int(p["giveaway_id"]))
        if g is None or g.guild_id != int(p["guild_id"]):
            raise RpcFailure("not_found")
        return g

    async def rpc_giveaway_end(self, p: dict[str, Any]) -> dict[str, Any]:
        g = await self._owned(p)
        g = await self.end_giveaway(g.id)
        return {"winners": [str(w) for w in (g.winner_ids if g else [])]}

    async def rpc_giveaway_reroll(self, p: dict[str, Any]) -> dict[str, Any]:
        g = await self._owned(p)
        g = await self.end_giveaway(g.id, reroll=True)
        return {"winners": [str(w) for w in (g.winner_ids if g else [])]}

    async def rpc_giveaway_cancel(self, p: dict[str, Any]) -> dict[str, Any]:
        g = await self._owned(p)
        async with sessionmaker()() as db:
            await db.execute(update(ScheduledJob).where(ScheduledJob.dedupe_key == f"giveaway.end:{g.id}",
                                                        ScheduledJob.status == "pending").values(status="cancelled"))
            await db.execute(delete(Giveaway).where(Giveaway.id == g.id))
            await db.commit()
        guild = self.bot.get_guild(g.guild_id)
        channel = guild.get_channel(g.channel_id) if guild else None
        if isinstance(channel, discord.TextChannel) and g.message_id:
            try:
                await channel.get_partial_message(g.message_id).delete()
            except discord.HTTPException:
                pass
        return {"cancelled": True}

    # --- Encuestas (encuestas nativas de Discord) --------------------------------
    async def send_poll(self, channel: discord.abc.Messageable, question: str, answers: list[str], hours: int,
                        multiple: bool) -> discord.Message:
        poll = discord.Poll(question=question[:300], duration=timedelta(hours=hours), multiple=multiple)
        for a in answers[:10]:
            poll.add_answer(text=a[:55])
        return await channel.send(poll=poll)

    @app_commands.command(name=key("cmd.poll.name"), description=key("cmd.poll.description"))
    @app_commands.guild_only()
    @app_commands.describe(question=key("arg.question"), answers=key("arg.answers"), hours=key("arg.hours"),
                           multiple=key("arg.multiple"))
    async def poll(self, interaction: discord.Interaction, question: str, answers: str,
                   hours: app_commands.Range[int, 1, 768] = 24, multiple: bool = False) -> None:
        assert interaction.guild and isinstance(interaction.user, discord.Member)
        loc = self._loc(interaction.guild_id)
        cfg: PollsConfig | None = self._cfg(interaction.guild.id, "polls")
        if cfg is None:
            await interaction.response.send_message(t(loc, "mod.module_disabled"), ephemeral=True)
            return
        if not cfg.allow_members and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(t(loc, "poll.not_allowed"), ephemeral=True)
            return
        opts = [a.strip() for a in answers.split("|") if a.strip()]
        if not 2 <= len(opts) <= 10:
            await interaction.response.send_message(t(loc, "poll.invalid"), ephemeral=True)
            return
        await interaction.response.send_message(t(loc, "poll.created"), ephemeral=True)
        await self.send_poll(interaction.channel, question, opts, hours, multiple)  # type: ignore[arg-type]

    async def rpc_poll(self, p: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(p["guild_id"]))
        if guild is None or self._cfg(guild.id, "polls") is None:
            raise RpcFailure("module_disabled")
        channel = guild.get_channel(int(p["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            raise RpcFailure("channel_not_found")
        try:
            msg = await self.send_poll(channel, p["question"], p["answers"], int(p["duration_hours"]), bool(p["multiple"]))
        except discord.Forbidden as exc:
            raise RpcFailure("bot_cannot_send") from exc
        return {"message_id": str(msg.id), "jump_url": msg.jump_url}

    # --- Starboard -------------------------------------------------------------
    async def _star(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        cfg: StarboardConfig | None = self._cfg(payload.guild_id, "starboard")
        if cfg is None or not cfg.channel_id:
            return
        if _norm_emoji(str(payload.emoji)) != _norm_emoji(cfg.emoji):
            return
        log.info("Starboard: reacción %s en canal %s (mensaje %s)", payload.emoji, payload.channel_id,
                 payload.message_id)
        if payload.channel_id in set(cfg.ignored_channel_ids) or payload.channel_id == cfg.channel_id:
            log.info("Starboard: canal ignorado o es el propio canal de destacados")
            return
        guild = self.bot.get_guild(payload.guild_id)
        source = guild.get_channel_or_thread(payload.channel_id) if guild else None
        board = guild.get_channel(cfg.channel_id) if guild else None
        if not isinstance(source, (discord.TextChannel, discord.Thread)) or not isinstance(board, discord.TextChannel):
            log.info("Starboard: canal de origen o de destacados no disponible")
            return
        if getattr(source, "nsfw", False) and not board.nsfw:
            return
        try:
            message = await source.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        if message.author.bot and not cfg.include_bots:
            log.info("Starboard: mensaje de un bot ignorado (include_bots=False)")
            return
        reaction = next((r for r in message.reactions if _norm_emoji(str(r.emoji)) == _norm_emoji(cfg.emoji)), None)
        count = 0
        if reaction:
            count = reaction.count
            if not cfg.allow_self_star:
                async for u in reaction.users():
                    if u.id == message.author.id:
                        count -= 1
                        break
        async with sessionmaker()() as db:
            entry = await db.get(StarboardEntry, (payload.guild_id, message.id))
            text_line = f"{cfg.emoji} **{count}** · {source.mention}"
            log.info("Starboard: %s estrellas (umbral %s)", count, cfg.threshold)
            if count >= cfg.threshold:
                embed = discord.Embed(description=message.content[:4000] or None, color=0xF59E0B,
                                      timestamp=message.created_at)
                embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
                img = next((a.url for a in message.attachments if (a.content_type or "").startswith("image/")), None)
                if img:
                    embed.set_image(url=img)
                view = discord.ui.View()
                view.add_item(discord.ui.Button(label=t(self._loc(payload.guild_id), "sb.jump"), url=message.jump_url))
                if entry and entry.starboard_message_id:
                    try:
                        await board.get_partial_message(entry.starboard_message_id).edit(content=text_line, embed=embed)
                    except discord.HTTPException:
                        pass
                    entry.star_count = count
                else:
                    posted = await board.send(content=text_line, embed=embed, view=view,
                                              allowed_mentions=discord.AllowedMentions.none())
                    if entry:
                        entry.starboard_message_id, entry.star_count = posted.id, count
                    else:
                        db.add(StarboardEntry(guild_id=payload.guild_id, source_message_id=message.id,
                                              source_channel_id=source.id, author_id=message.author.id,
                                              starboard_message_id=posted.id, star_count=count))
            elif entry and entry.starboard_message_id:
                try:
                    await board.get_partial_message(entry.starboard_message_id).delete()
                except discord.HTTPException:
                    pass
                entry.starboard_message_id, entry.star_count = None, count
            await db.commit()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._star(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._star(payload)


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Community(bot))
