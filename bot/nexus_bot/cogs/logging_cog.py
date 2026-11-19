"""Logs del servidor: el contenido se envía al canal de logs y NO se guarda en la base de datos."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from nexus_core.i18n import t
from nexus_core.modules import parse_config
from nexus_core.modules.moderation import LoggingConfig, channel_for

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

GREEN, RED, AMBER, BLUE = 0x22C55E, 0xEF4444, 0xF59E0B, 0x5865F2


class Logging(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot

    def _cfg(self, guild_id: int) -> LoggingConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("logging")
        return parse_config("logging", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    async def _send(self, guild: discord.Guild, event: str, embed: discord.Embed,
                    source_channel_id: int | None = None) -> None:
        cfg = self._cfg(guild.id)
        if cfg is None:
            return
        if source_channel_id and source_channel_id in set(cfg.ignored_channel_ids):
            return
        channel_id = channel_for(cfg, event)
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.abc.Messageable) or channel.id == source_channel_id:
            return
        embed.timestamp = discord.utils.utcnow()
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    def L(self, guild: discord.Guild, k: str, **kw: object) -> str:
        return t(self.bot.cache.get(guild.id).locale, f"log.{k}", **kw)

    def _skip_author(self, guild: discord.Guild, author: discord.abc.User) -> bool:
        cfg = self._cfg(guild.id)
        return bool(cfg and cfg.ignore_bots and author.bot)

    # --- mensajes ---------------------------------------------------------
    @commands.Cog.listener()
    async def on_message_delete(self, m: discord.Message) -> None:
        if not m.guild or self._skip_author(m.guild, m.author):
            return
        e = discord.Embed(title=self.L(m.guild, "message_delete"), color=RED,
                          description=(m.content or self.L(m.guild, "no_text"))[:4000])
        e.add_field(name=self.L(m.guild, "author"), value=f"{m.author.mention} ({m.author})")
        e.add_field(name=self.L(m.guild, "channel"), value=m.channel.mention)  # type: ignore[union-attr]
        if m.attachments:
            e.add_field(name=self.L(m.guild, "attachments"), value="\n".join(a.filename for a in m.attachments)[:1000],
                        inline=False)
        e.set_footer(text=f"ID {m.author.id}")
        await self._send(m.guild, "message_delete", e, m.channel.id)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not after.guild or before.content == after.content or self._skip_author(after.guild, after.author):
            return
        g = after.guild
        e = discord.Embed(title=self.L(g, "message_edit"), color=AMBER, url=after.jump_url)
        e.add_field(name=self.L(g, "before"), value=(before.content or "—")[:1024], inline=False)
        e.add_field(name=self.L(g, "after"), value=(after.content or "—")[:1024], inline=False)
        e.add_field(name=self.L(g, "author"), value=f"{after.author.mention} ({after.author})")
        e.add_field(name=self.L(g, "channel"), value=after.channel.mention)  # type: ignore[union-attr]
        await self._send(g, "message_edit", e, after.channel.id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, p: discord.RawBulkMessageDeleteEvent) -> None:
        g = self.bot.get_guild(p.guild_id or 0)
        if g is None:
            return
        e = discord.Embed(title=self.L(g, "message_bulk_delete"), color=RED,
                          description=self.L(g, "bulk_count", count=len(p.message_ids), channel=f"<#{p.channel_id}>"))
        await self._send(g, "message_bulk_delete", e, p.channel_id)

    # --- miembros ---------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, m: discord.Member) -> None:
        e = discord.Embed(title=self.L(m.guild, "member_join"), color=GREEN, description=f"{m.mention} ({m})")
        e.add_field(name=self.L(m.guild, "account_created"), value=f"<t:{int(m.created_at.timestamp())}:R>")
        e.set_thumbnail(url=m.display_avatar.url)
        e.set_footer(text=f"ID {m.id}")
        await self._send(m.guild, "member_join", e)

    @commands.Cog.listener()
    async def on_member_remove(self, m: discord.Member) -> None:
        e = discord.Embed(title=self.L(m.guild, "member_leave"), color=RED, description=f"{m.mention} ({m})")
        roles = [r.mention for r in m.roles if not r.is_default()]
        if roles:
            e.add_field(name=self.L(m.guild, "roles"), value=" ".join(roles)[:1024])
        e.set_footer(text=f"ID {m.id}")
        await self._send(m.guild, "member_leave", e)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        g = after.guild
        if before.nick != after.nick:
            e = discord.Embed(title=self.L(g, "member_nickname"), color=BLUE, description=f"{after.mention}")
            e.add_field(name=self.L(g, "before"), value=before.nick or "—")
            e.add_field(name=self.L(g, "after"), value=after.nick or "—")
            await self._send(g, "member_nickname", e)
        if before.roles != after.roles:
            added = [r.mention for r in after.roles if r not in before.roles]
            removed = [r.mention for r in before.roles if r not in after.roles]
            e = discord.Embed(title=self.L(g, "member_roles"), color=BLUE, description=f"{after.mention}")
            if added:
                e.add_field(name=self.L(g, "added"), value=" ".join(added)[:1024])
            if removed:
                e.add_field(name=self.L(g, "removed"), value=" ".join(removed)[:1024])
            await self._send(g, "member_roles", e)

    # --- roles y canales ----------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_role_create(self, r: discord.Role) -> None:
        await self._send(r.guild, "role_create", discord.Embed(title=self.L(r.guild, "role_create"), color=GREEN,
                                                               description=f"{r.mention} ({r.name})"))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, r: discord.Role) -> None:
        await self._send(r.guild, "role_delete", discord.Embed(title=self.L(r.guild, "role_delete"), color=RED,
                                                               description=r.name))

    @commands.Cog.listener()
    async def on_guild_role_update(self, b: discord.Role, a: discord.Role) -> None:
        if (b.name, b.color, b.permissions, b.hoist, b.mentionable) == (a.name, a.color, a.permissions, a.hoist,
                                                                         a.mentionable):
            return
        e = discord.Embed(title=self.L(a.guild, "role_update"), color=AMBER, description=a.mention)
        if b.name != a.name:
            e.add_field(name=self.L(a.guild, "name"), value=f"{b.name} → {a.name}")
        if b.permissions != a.permissions:
            e.add_field(name=self.L(a.guild, "permissions"), value=self.L(a.guild, "changed"))
        await self._send(a.guild, "role_update", e)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, c: discord.abc.GuildChannel) -> None:
        await self._send(c.guild, "channel_create", discord.Embed(title=self.L(c.guild, "channel_create"), color=GREEN,
                                                                  description=f"{c.mention} ({c.name})"))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, c: discord.abc.GuildChannel) -> None:
        await self._send(c.guild, "channel_delete", discord.Embed(title=self.L(c.guild, "channel_delete"), color=RED,
                                                                  description=c.name))

    @commands.Cog.listener()
    async def on_guild_channel_update(self, b: discord.abc.GuildChannel, a: discord.abc.GuildChannel) -> None:
        if b.name == a.name and getattr(b, "topic", None) == getattr(a, "topic", None) and \
                b.overwrites == a.overwrites:
            return
        e = discord.Embed(title=self.L(a.guild, "channel_update"), color=AMBER, description=a.mention)
        if b.name != a.name:
            e.add_field(name=self.L(a.guild, "name"), value=f"{b.name} → {a.name}")
        if b.overwrites != a.overwrites:
            e.add_field(name=self.L(a.guild, "permissions"), value=self.L(a.guild, "changed"))
        await self._send(a.guild, "channel_update", e)


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Logging(bot))
