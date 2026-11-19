"""Etiquetas (/tag), respuestas automáticas por palabras clave y mensajes fijos al final de un canal."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from nexus_core.i18n import t
from nexus_core.messages.render import substitute, variables
from nexus_core.modules import parse_config
from nexus_core.modules.responses import ResponsesConfig, matches

from nexus_bot.cogs.welcome import context_for
from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.responses")

STICKY_DELAY = 4  # segundos de calma antes de volver a poner el mensaje fijo al final


def _sticky_key(channel_id: int) -> str:
    return f"nexus:sticky:{channel_id}"


class Responses(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self._cooldowns: dict[tuple[str, int], float] = {}  # (respuesta, canal) → último uso
        self._sticky_tasks: dict[int, asyncio.Task[None]] = {}

    def cfg(self, guild_id: int) -> ResponsesConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("responses")
        return parse_config("responses", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    def _text(self, template: str, member: discord.Member, channel_id: int) -> str:
        state = self.bot.cache.get(member.guild.id)
        return substitute(template, variables(context_for(member, member.guild, channel_id, state.locale,
                                                          state.timezone)))[:2000]

    # --- /tag -----------------------------------------------------------------------------
    @app_commands.command(name=key("cmd.tag.name"), description=key("cmd.tag.description"))
    @app_commands.guild_only()
    @app_commands.describe(name=key("arg.tag_name"), user=key("arg.tag_user"))
    async def tag(self, i: discord.Interaction, name: str, user: discord.Member | None = None) -> None:
        assert i.guild and isinstance(i.user, discord.Member)
        loc = self.bot.cache.get(i.guild.id).locale
        cfg = self.cfg(i.guild.id)
        if cfg is None:
            await i.response.send_message(t(loc, "resp.disabled"), ephemeral=True)
            return
        tag = next((x for x in cfg.tags if x.name == name.strip().lower()), None)
        if tag is None:
            await i.response.send_message(t(loc, "resp.tag_not_found", name=name), ephemeral=True)
            return
        text = self._text(tag.content, i.user, i.channel_id or 0)
        if user:
            text = f"{user.mention} {text}"[:2000]
        await i.response.send_message(text, allowed_mentions=discord.AllowedMentions(
            everyone=False, roles=False, users=[user] if user else False))

    @tag.autocomplete("name")
    async def _tag_autocomplete(self, i: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        cfg = self.cfg(i.guild_id or 0)
        cur = current.lower()
        return [app_commands.Choice(name=x.name, value=x.name) for x in (cfg.tags if cfg else []) if cur in x.name][:25]

    # --- Respuestas automáticas y mensajes fijos -------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or not isinstance(message.author, discord.Member):
            return
        cfg = self.cfg(message.guild.id)
        if cfg is None:
            return
        if any(s.channel_id == message.channel.id for s in cfg.stickies) and message.author.id != self.bot.user.id:  # type: ignore[union-attr]
            self._schedule_sticky(message.channel)  # type: ignore[arg-type]
        if message.author.bot or not message.content:
            return
        now = time.monotonic()
        for tr in cfg.triggers:
            if tr.channel_ids and message.channel.id not in set(tr.channel_ids):
                continue
            if not matches(tr, message.content):
                continue
            k = (tr.id, message.channel.id)
            if now - self._cooldowns.get(k, 0) < tr.cooldown_seconds:
                return
            self._cooldowns[k] = now
            text = self._text(tr.response, message.author, message.channel.id)
            mentions = discord.AllowedMentions(everyone=False, roles=False, users=[message.author], replied_user=True)
            try:
                if tr.reply:
                    await message.reply(text, allowed_mentions=mentions, mention_author=False)
                else:
                    await message.channel.send(text, allowed_mentions=mentions)
            except discord.HTTPException:
                pass
            return  # una sola respuesta por mensaje

    def _schedule_sticky(self, channel: discord.TextChannel) -> None:
        old = self._sticky_tasks.get(channel.id)
        if old and not old.done():
            old.cancel()  # mientras se sigue escribiendo, se espera (evita repetir el mensaje en cada línea)
        self._sticky_tasks[channel.id] = asyncio.create_task(self._repost_sticky(channel))

    async def _repost_sticky(self, channel: discord.TextChannel) -> None:
        try:
            await asyncio.sleep(STICKY_DELAY)
        except asyncio.CancelledError:
            return
        cfg = self.cfg(channel.guild.id)
        sticky = next((s for s in (cfg.stickies if cfg else []) if s.channel_id == channel.id), None)
        if sticky is None:
            return
        try:
            old_id = await self.bot.redis.get(_sticky_key(channel.id))
        except Exception:
            old_id = None
        if old_id:
            try:
                await channel.get_partial_message(int(old_id)).delete()
            except discord.HTTPException:
                pass
        loc = self.bot.cache.get(channel.guild.id).locale
        try:
            msg = await channel.send(f"📌 {sticky.content}"[:2000], allowed_mentions=discord.AllowedMentions.none(),
                                     silent=True)
        except discord.HTTPException:
            log.info("Mensaje fijo: no se pudo publicar en %s (%s)", channel.id, loc)
            return
        try:
            await self.bot.redis.set(_sticky_key(channel.id), str(msg.id))
        except Exception:
            pass


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Responses(bot))
