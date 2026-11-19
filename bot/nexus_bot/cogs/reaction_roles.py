"""Reaction Roles: paneles con botones, menú desplegable o reacciones.

Los botones y menús usan custom_id persistentes (``nexus:rp:…``), así siguen funcionando tras reiniciar el bot.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from nexus_core.db import sessionmaker
from nexus_core.db.models import RolePanel
from nexus_core.db.repo import utcnow
from nexus_core.discord.permissions import is_dangerous
from nexus_core.i18n import t
from nexus_core.messages import MessageTemplate, render_payload

from nexus_bot.cogs.welcome import context_for, for_edit, with_media

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.rr")
STYLES = {"primary": discord.ButtonStyle.primary, "secondary": discord.ButtonStyle.secondary,
          "success": discord.ButtonStyle.success, "danger": discord.ButtonStyle.danger}


async def load_panel(panel_id: int) -> RolePanel | None:
    async with sessionmaker()() as db:
        return await db.get(RolePanel, panel_id)


def _emoji(v: str | None) -> discord.PartialEmoji | str | None:
    if not v:
        return None
    return discord.PartialEmoji.from_str(v) if v.startswith("<") else v


async def apply_choice(bot: NexusBot, interaction: discord.Interaction, panel: RolePanel,
                       chosen: list[str], *, from_select: bool) -> None:
    """Calcula y aplica los roles a añadir/quitar según el modo del panel."""
    guild = interaction.guild
    member = interaction.user
    assert guild and isinstance(member, discord.Member)
    loc = bot.cache.get(guild.id).locale
    if bot.cache.get(guild.id).module("reaction_roles") is None:
        await interaction.response.send_message(t(loc, "rr.disabled"), ephemeral=True)
        return
    options = {o["id"]: o for o in panel.options}
    panel_roles = {int(o["role_id"]) for o in panel.options}
    want = {int(options[c]["role_id"]) for c in chosen if c in options}
    have = {r.id for r in member.roles} & panel_roles
    if from_select:
        add, remove = want - have, (panel_roles - want) & have
    else:
        rid = next(iter(want), None)
        if rid is None:
            return
        if rid in have:
            add, remove = set(), {rid}
        else:
            add, remove = {rid}, set()
            if panel.mode == "unique":
                remove = have - {rid}
    if panel.mode == "verify":
        remove = set()
    if panel.mode == "drop":
        add = set()
    me = guild.me
    to_add = [r for x in add if (r := guild.get_role(x)) and r < me.top_role and not is_dangerous(r.permissions.value)]
    to_remove = [r for x in remove if (r := guild.get_role(x)) and r < me.top_role]
    if len(to_add) < len(add) or len(to_remove) < len(remove):
        await interaction.response.send_message(t(loc, "rr.hierarchy"), ephemeral=True)
        return
    try:
        if to_add:
            await member.add_roles(*to_add, reason=f"NEXUS reaction roles: {panel.name}")
        if to_remove:
            await member.remove_roles(*to_remove, reason=f"NEXUS reaction roles: {panel.name}")
    except discord.Forbidden:
        await interaction.response.send_message(t(loc, "rr.no_permission"), ephemeral=True)
        return
    parts = []
    if to_add:
        parts.append(t(loc, "rr.added", roles=", ".join(r.mention for r in to_add)))
    if to_remove:
        parts.append(t(loc, "rr.removed", roles=", ".join(r.mention for r in to_remove)))
    await interaction.response.send_message("\n".join(parts) or t(loc, "rr.nothing"), ephemeral=True,
                                            allowed_mentions=discord.AllowedMentions.none())


class PanelButton(discord.ui.DynamicItem[discord.ui.Button], template=r"nexus:rp:(?P<panel>\d+):(?P<opt>[a-f0-9]{8})"):
    def __init__(self, panel_id: int, option: dict[str, Any]) -> None:
        super().__init__(discord.ui.Button(
            label=option.get("label") or None, emoji=_emoji(option.get("emoji")),
            style=STYLES.get(option.get("style", "secondary"), discord.ButtonStyle.secondary),
            custom_id=f"nexus:rp:{panel_id}:{option['id']}"))
        self.panel_id = panel_id
        self.option_id = option["id"]

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button,
                             match: re.Match[str]) -> "PanelButton":
        inst = cls.__new__(cls)
        discord.ui.DynamicItem.__init__(inst, item)
        inst.panel_id = int(match["panel"])
        inst.option_id = match["opt"]
        return inst

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = await load_panel(self.panel_id)
        if panel is None or panel.guild_id != interaction.guild_id:
            await interaction.response.send_message("❌", ephemeral=True)
            return
        await apply_choice(interaction.client, interaction, panel, [self.option_id], from_select=False)  # type: ignore[arg-type]


class PanelSelect(discord.ui.DynamicItem[discord.ui.Select], template=r"nexus:rps:(?P<panel>\d+)"):
    def __init__(self, panel: RolePanel) -> None:
        opts = [discord.SelectOption(label=o.get("label") or o.get("emoji") or "·", value=o["id"],
                                     description=o.get("description") or None, emoji=_emoji(o.get("emoji")))
                for o in panel.options]
        max_values = len(opts) if panel.mode != "unique" else 1
        if panel.max_choices:
            max_values = min(max_values, panel.max_choices)
        super().__init__(discord.ui.Select(custom_id=f"nexus:rps:{panel.id}", options=opts, min_values=0,
                                           max_values=max_values, placeholder=panel.placeholder or None))
        self.panel_id = panel.id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select,
                             match: re.Match[str]) -> "PanelSelect":
        inst = cls.__new__(cls)
        discord.ui.DynamicItem.__init__(inst, item)
        inst.panel_id = int(match["panel"])
        return inst

    async def callback(self, interaction: discord.Interaction) -> None:
        panel = await load_panel(self.panel_id)
        if panel is None or panel.guild_id != interaction.guild_id:
            await interaction.response.send_message("❌", ephemeral=True)
            return
        await apply_choice(interaction.client, interaction, panel, list(self.item.values), from_select=True)  # type: ignore[arg-type]


class ReactionRoles(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        bot.add_dynamic_items(PanelButton, PanelSelect)
        bot.rpc_handlers["role_panel.publish"] = self.rpc_publish

    async def rpc_publish(self, params: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        panel = await load_panel(int(params["panel_id"]))
        if guild is None or panel is None or panel.guild_id != guild.id:
            raise RpcFailure("not_found")
        channel = guild.get_channel(panel.channel_id or 0)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise RpcFailure("channel_not_found")
        me = guild.me
        too_high = [o["role_id"] for o in panel.options
                    if (r := guild.get_role(int(o["role_id"]))) is None or r >= me.top_role or r.managed]
        if too_high:
            raise RpcFailure("roles_too_high", role_ids=too_high)
        state = self.bot.cache.get(guild.id)
        ctx = context_for(me, guild, channel.id, state.locale, state.timezone)
        kwargs = await with_media(guild.id, render_payload(MessageTemplate.model_validate(panel.message), ctx, state.embed_color))
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
        view: discord.ui.View | None = None
        if panel.panel_type == "buttons":
            view = discord.ui.View(timeout=None)
            for o in panel.options:
                view.add_item(PanelButton(panel.id, o))
        elif panel.panel_type == "select":
            view = discord.ui.View(timeout=None)
            view.add_item(PanelSelect(panel))
        try:
            msg: discord.Message | None = None
            if panel.message_id:
                try:
                    msg = await channel.fetch_message(panel.message_id)
                    await msg.edit(**for_edit(kwargs), view=view)
                except discord.NotFound:
                    msg = None
            if msg is None:
                msg = await channel.send(**kwargs, view=view) if view else await channel.send(**kwargs)
            if panel.panel_type == "reactions":
                if panel.message_id:
                    try:
                        await msg.clear_reactions()
                    except discord.HTTPException:
                        pass  # sin «Gestionar mensajes»: se dejan las reacciones antiguas
                for o in panel.options:
                    await msg.add_reaction(_emoji(o["emoji"]))  # type: ignore[arg-type]
        except discord.Forbidden as exc:
            raise RpcFailure("bot_cannot_send") from exc
        except discord.HTTPException as exc:
            raise RpcFailure("discord_error", detail=str(exc)[:200]) from exc
        async with sessionmaker()() as db:
            p = await db.get(RolePanel, panel.id)
            if p:
                p.message_id = msg.id
                p.published_at = utcnow()
                await db.commit()
        return {"message_id": str(msg.id)}

    async def _reaction(self, payload: discord.RawReactionActionEvent, added: bool) -> None:
        if payload.guild_id is None or (self.bot.user and payload.user_id == self.bot.user.id):
            return
        state = self.bot.cache.get(payload.guild_id)
        if state.module("reaction_roles") is None:
            return
        async with sessionmaker()() as db:
            from sqlalchemy import select

            panel = await db.scalar(select(RolePanel).where(RolePanel.message_id == payload.message_id,
                                                            RolePanel.panel_type == "reactions"))
        if panel is None:
            return
        emoji = str(payload.emoji)
        opt = next((o for o in panel.options if o.get("emoji") == emoji or
                    (payload.emoji.id and str(payload.emoji.id) in (o.get("emoji") or ""))), None)
        guild = self.bot.get_guild(payload.guild_id)
        if opt is None or guild is None:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(opt["role_id"]))
        if member is None or member.bot or role is None or role >= guild.me.top_role:
            return
        if added and is_dangerous(role.permissions.value):
            log.warning("Rol con permisos de staff en un panel de %s: no se reparte (%s)", guild.id, role.name)
            return
        try:
            if added and panel.mode != "drop":
                if panel.mode == "unique":
                    others = [r for o in panel.options if (r := guild.get_role(int(o["role_id"]))) and r in member.roles
                              and r.id != role.id]
                    if others:
                        await member.remove_roles(*others, reason=f"NEXUS reaction roles: {panel.name}")
                await member.add_roles(role, reason=f"NEXUS reaction roles: {panel.name}")
            elif not added and panel.mode not in ("verify",):
                await member.remove_roles(role, reason=f"NEXUS reaction roles: {panel.name}")
        except discord.HTTPException:
            log.info("No se pudo cambiar el rol por reacción en %s", guild.id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._reaction(payload, True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._reaction(payload, False)


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(ReactionRoles(bot))
