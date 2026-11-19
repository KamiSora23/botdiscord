"""Comandos generales: /ping, /help, /dashboard, /serverinfo, /userinfo, /avatar."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from nexus_core.config import get_settings
from nexus_core.i18n import t

from nexus_bot import groups
from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot


class General(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        groups.bind(self, self.serverinfo, self.userinfo, self.avatar)

    def _locale(self, interaction: discord.Interaction) -> str:
        if interaction.guild_id:
            return self.bot.cache.get(interaction.guild_id).locale
        return "es" if str(interaction.locale).startswith("es") else "en"

    @app_commands.command(name=key("cmd.ping.name"), description=key("cmd.ping.description"))
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            t(self._locale(interaction), "ping.reply", latency=latency), ephemeral=True)

    @app_commands.command(name=key("cmd.help.name"), description=key("cmd.help.description"))
    async def help(self, interaction: discord.Interaction) -> None:
        loc = self._locale(interaction)
        color = self.bot.cache.get(interaction.guild_id).embed_color if interaction.guild_id else 0x7465F7
        embed = discord.Embed(title=t(loc, "help.title"), description=t(loc, "help.body"), color=color)
        embed.set_footer(text=t(loc, "help.footer"))
        await interaction.response.send_message(embed=embed, view=self._dashboard_view(interaction, loc),
                                                ephemeral=True)

    @app_commands.command(name=key("cmd.dashboard.name"), description=key("cmd.dashboard.description"))
    @app_commands.guild_only()
    async def dashboard(self, interaction: discord.Interaction) -> None:
        loc = self._locale(interaction)
        server = interaction.guild.name if interaction.guild else ""
        await interaction.response.send_message(
            f"{t(loc, 'dashboard.reply', server=server)} {self._dashboard_url(interaction)}",
            view=self._dashboard_view(interaction, loc), ephemeral=True)

    def _color(self, interaction: discord.Interaction) -> int:
        return self.bot.cache.get(interaction.guild_id).embed_color if interaction.guild_id else 0x7465F7

    @groups.info.command(name=key("sub.info.server"), description=key("cmd.serverinfo.description"))
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        g = interaction.guild
        assert g is not None
        loc = self._locale(interaction)
        e = discord.Embed(title=g.name, description=g.description or None, color=self._color(interaction))
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        e.add_field(name=t(loc, "info.owner"), value=f"<@{g.owner_id}>")
        e.add_field(name=t(loc, "info.created"), value=discord.utils.format_dt(g.created_at, "D"))
        e.add_field(name=t(loc, "info.members"), value=str(g.member_count or len(g.members)))
        e.add_field(name=t(loc, "info.channels"), value=str(len(g.channels)))
        e.add_field(name=t(loc, "info.roles"), value=str(len(g.roles) - 1))
        level = t(loc, "info.level", level=g.premium_tier)
        e.add_field(name=t(loc, "info.boosts"), value=f"{g.premium_subscription_count or 0} · {level}")
        e.set_footer(text=f"{t(loc, 'info.id')}: {g.id}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @groups.info.command(name=key("sub.info.user"), description=key("cmd.userinfo.description"))
    @app_commands.describe(user=key("arg.target_user"))
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member | None = None) -> None:
        member = user or interaction.user
        loc = self._locale(interaction)
        e = discord.Embed(title=str(member), color=self._color(interaction))
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name=t(loc, "info.account"), value=discord.utils.format_dt(member.created_at, "R"))
        if isinstance(member, discord.Member):
            if member.joined_at:
                e.add_field(name=t(loc, "info.joined"), value=discord.utils.format_dt(member.joined_at, "R"))
            if len(member.roles) > 1:
                e.add_field(name=t(loc, "info.top_role"), value=member.top_role.mention)
                roles = [r.mention for r in reversed(member.roles[1:])][:15]
                e.add_field(name=f"{t(loc, 'info.roles')} ({len(member.roles) - 1})", value=" ".join(roles),
                            inline=False)
        e.set_footer(text=f"{t(loc, 'info.id')}: {member.id}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @groups.info.command(name=key("sub.info.avatar"), description=key("cmd.avatar.description"))
    @app_commands.describe(user=key("arg.target_user"))
    async def avatar(self, interaction: discord.Interaction, user: discord.User | None = None) -> None:
        target = user or interaction.user
        e = discord.Embed(title=str(target), color=self._color(interaction))
        e.set_image(url=target.display_avatar.with_size(1024).url)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @staticmethod
    def _dashboard_url(interaction: discord.Interaction) -> str:
        base = get_settings().dashboard_url.rstrip("/")
        if interaction.guild_id:
            return f"{base}/dashboard/{interaction.guild_id}/overview"
        return f"{base}/dashboard"

    def _dashboard_view(self, interaction: discord.Interaction, loc: str) -> discord.ui.View:
        view = discord.ui.View()
        url = self._dashboard_url(interaction)
        # Discord solo acepta botones con enlaces públicos; en local (http://localhost) va en el texto.
        if url.startswith("https://"):
            view.add_item(discord.ui.Button(label=t(loc, "dashboard.button"), url=url))
        return view


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(General(bot))
