"""Tickets: canal privado por ticket, botones Reclamar/Cerrar, transcripción en archivo y cierre automático."""

from __future__ import annotations

import html
import io
import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks
from sqlalchemy import func, select, update

from nexus_core.db import sessionmaker
from nexus_core.db.models import ModuleConfig, Ticket
from nexus_core.db.repo import next_number, utcnow
from nexus_core.i18n import t
from nexus_core.messages import render_payload
from nexus_core.messages.render import substitute, variables
from nexus_core.modules import parse_config
from nexus_core.modules.community import TicketPanel, TicketsConfig

from nexus_bot.cogs.welcome import context_for, for_edit, with_media
from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.tickets")


def _emoji(v: str | None) -> discord.PartialEmoji | str | None:
    if not v:
        return None
    return discord.PartialEmoji.from_str(v) if v.startswith("<") else v


class OpenButton(discord.ui.DynamicItem[discord.ui.Button], template=r"nexus:tk:open:(?P<panel>[a-f0-9]{8})"):
    def __init__(self, panel: TicketPanel) -> None:
        super().__init__(discord.ui.Button(label=panel.button_label, emoji=_emoji(panel.button_emoji),
                                           style=discord.ButtonStyle.primary, custom_id=f"nexus:tk:open:{panel.id}"))
        self.panel_id = panel.id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):  # type: ignore[no-untyped-def]
        inst = cls.__new__(cls)
        discord.ui.DynamicItem.__init__(inst, item)
        inst.panel_id = match["panel"]
        return inst

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Tickets = interaction.client.get_cog("Tickets")  # type: ignore[union-attr,assignment]
        await cog.open_from_button(interaction, self.panel_id)


class TicketButton(discord.ui.DynamicItem[discord.ui.Button], template=r"nexus:tk:(?P<action>close|claim)"):
    def __init__(self, action: str, label: str) -> None:
        style = discord.ButtonStyle.danger if action == "close" else discord.ButtonStyle.secondary
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=f"nexus:tk:{action}",
                                           emoji="🔒" if action == "close" else "🙋"))
        self.action = action

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):  # type: ignore[no-untyped-def]
        inst = cls.__new__(cls)
        discord.ui.DynamicItem.__init__(inst, item)
        inst.action = match["action"]
        return inst

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Tickets = interaction.client.get_cog("Tickets")  # type: ignore[union-attr,assignment]
        if self.action == "close":
            await cog.close_from_interaction(interaction, None)
        else:
            await cog.claim(interaction)


class SubjectModal(discord.ui.Modal):
    def __init__(self, cog: "Tickets", panel_id: str, title: str, label: str) -> None:
        super().__init__(title=title[:45])
        self.cog, self.panel_id = cog, panel_id
        self.subject = discord.ui.TextInput(label=label[:45], style=discord.TextStyle.paragraph, max_length=500)
        self.add_item(self.subject)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.open_ticket(interaction, self.panel_id, str(self.subject.value))


class Tickets(commands.GroupCog, group_name=key("cmd.ticket.name"), group_description=key("cmd.ticket.description")):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self._activity: dict[int, float] = {}
        bot.add_dynamic_items(OpenButton, TicketButton)
        bot.rpc_handlers["tickets.publish"] = self.rpc_publish
        bot.rpc_handlers["tickets.close"] = self.rpc_close
        self.auto_close.start()
        super().__init__()

    def cog_unload(self) -> None:
        self.auto_close.cancel()

    def _cfg(self, guild_id: int) -> TicketsConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("tickets")
        return parse_config("tickets", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    def _loc(self, guild_id: int | None) -> str:
        return self.bot.cache.get(guild_id or 0).locale

    def _is_staff(self, member: discord.Member, panel: TicketPanel | None) -> bool:
        if member.guild_permissions.manage_guild or member.guild_permissions.manage_channels:
            return True
        return bool(panel and {r.id for r in member.roles} & set(panel.support_role_ids))

    # --- abrir ------------------------------------------------------------
    async def open_from_button(self, interaction: discord.Interaction, panel_id: str) -> None:
        log.info("Botón de ticket pulsado: panel %s en %s por %s", panel_id, interaction.guild_id, interaction.user.id)
        cfg = self._cfg(interaction.guild_id or 0)
        loc = self._loc(interaction.guild_id)
        panel = next((p for p in cfg.panels if p.id == panel_id), None) if cfg else None
        if panel is None:
            log.warning("Ticket: panel %s no encontrado o módulo apagado en %s", panel_id, interaction.guild_id)
            await interaction.response.send_message(t(loc, "tk.disabled"), ephemeral=True)
            return
        if panel.ask_subject:
            await interaction.response.send_modal(SubjectModal(self, panel_id, panel.name, t(loc, "tk.subject")))
            return
        await self.open_ticket(interaction, panel_id, None)

    async def open_ticket(self, interaction: discord.Interaction, panel_id: str, subject: str | None) -> None:
        guild, user = interaction.guild, interaction.user
        assert guild and isinstance(user, discord.Member)
        loc = self._loc(guild.id)
        cfg = self._cfg(guild.id)
        panel = next((p for p in cfg.panels if p.id == panel_id), None) if cfg else None
        if cfg is None or panel is None:
            await interaction.response.send_message(t(loc, "tk.disabled"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with sessionmaker()() as db:
            open_count = await db.scalar(select(func.count()).select_from(Ticket).where(
                Ticket.guild_id == guild.id, Ticket.creator_id == user.id, Ticket.status == "open"))
            if open_count >= cfg.max_open_per_user:
                await interaction.followup.send(t(loc, "tk.limit", max=cfg.max_open_per_user), ephemeral=True)
                return
            number = await next_number(db, Ticket, guild.id)
            category = guild.get_channel(panel.category_channel_id or 0)
            overwrites: dict[Any, discord.PermissionOverwrite] = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True,
                                                  read_message_history=True, embed_links=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True,
                                                      read_message_history=True, embed_links=True, attach_files=True),
            }
            for rid in panel.support_role_ids:
                if role := guild.get_role(rid):
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                                   read_message_history=True, attach_files=True)
            try:
                channel = await guild.create_text_channel(
                    f"ticket-{number:04d}", overwrites=overwrites,
                    category=category if isinstance(category, discord.CategoryChannel) else None,
                    topic=f"{user} · {panel.name}" + (f" · {subject[:100]}" if subject else ""),
                    reason=f"NEXUS ticket #{number}")
            except discord.Forbidden as exc:
                log.warning("Ticket: Discord no dejó crear el canal en %s: %s", guild.id, exc)
                await interaction.followup.send(t(loc, "tk.no_permission"), ephemeral=True)
                return
            db.add(Ticket(guild_id=guild.id, number=number, panel_id=panel.id, creator_id=user.id,
                          creator_name=str(user), channel_id=channel.id, subject=subject))
            await db.commit()
        state = self.bot.cache.get(guild.id)
        values = variables(context_for(user, guild, channel.id, state.locale, state.timezone))
        mentions = " ".join(f"<@&{r}>" for r in panel.support_role_ids)
        embed = discord.Embed(title=t(loc, "tk.title", number=number), color=state.embed_color,
                              description=substitute(panel.opening_message, values))
        if subject:
            embed.add_field(name=t(loc, "tk.subject"), value=subject[:1024], inline=False)
        view = discord.ui.View(timeout=None)
        view.add_item(TicketButton("claim", t(loc, "tk.claim")))
        view.add_item(TicketButton("close", t(loc, "tk.close")))
        await channel.send(content=f"{user.mention} {mentions}".strip(), embed=embed, view=view,
                           allowed_mentions=discord.AllowedMentions(users=True, roles=True))
        await interaction.followup.send(t(loc, "tk.created", channel=channel.mention), ephemeral=True)

    # --- reclamar / cerrar ------------------------------------------------
    async def _ticket_for(self, channel_id: int) -> Ticket | None:
        async with sessionmaker()() as db:
            return await db.scalar(select(Ticket).where(Ticket.channel_id == channel_id, Ticket.status == "open"))

    async def claim(self, interaction: discord.Interaction) -> None:
        loc = self._loc(interaction.guild_id)
        ticket = await self._ticket_for(interaction.channel_id or 0)
        cfg = self._cfg(interaction.guild_id or 0)
        panel = next((p for p in cfg.panels if ticket and p.id == ticket.panel_id), None) if cfg else None
        if ticket is None or not isinstance(interaction.user, discord.Member) or not self._is_staff(interaction.user, panel):
            await interaction.response.send_message(t(loc, "tk.staff_only"), ephemeral=True)
            return
        async with sessionmaker()() as db:
            await db.execute(update(Ticket).where(Ticket.id == ticket.id).values(claimed_by=interaction.user.id))
            await db.commit()
        await interaction.response.send_message(t(loc, "tk.claimed", user=interaction.user.mention))

    async def close_from_interaction(self, interaction: discord.Interaction, reason: str | None) -> None:
        loc = self._loc(interaction.guild_id)
        ticket = await self._ticket_for(interaction.channel_id or 0)
        if ticket is None:
            await interaction.response.send_message(t(loc, "tk.not_ticket"), ephemeral=True)
            return
        cfg = self._cfg(ticket.guild_id)
        panel = next((p for p in cfg.panels if p.id == ticket.panel_id), None) if cfg else None
        member = interaction.user
        if not isinstance(member, discord.Member) or (member.id != ticket.creator_id and not self._is_staff(member, panel)):
            await interaction.response.send_message(t(loc, "tk.staff_only"), ephemeral=True)
            return
        await interaction.response.send_message(t(loc, "tk.closing"))
        await self.close_ticket(ticket, member, reason)

    async def close_ticket(self, ticket: Ticket, closer: discord.abc.User | None, reason: str | None) -> None:
        guild = self.bot.get_guild(ticket.guild_id)
        if guild is None:
            return
        loc = self._loc(guild.id)
        channel = guild.get_channel(ticket.channel_id or 0)
        cfg = self._cfg(guild.id)
        transcript: discord.File | None = None
        if isinstance(channel, discord.TextChannel):
            transcript = await self._transcript(channel, ticket)
        async with sessionmaker()() as db:
            await db.execute(update(Ticket).where(Ticket.id == ticket.id).values(
                status="closed", closed_at=utcnow(), closed_by=closer.id if closer else None,
                close_reason=(reason or "")[:500] or None))
            await db.commit()
        summary = discord.Embed(title=t(loc, "tk.closed_title", number=ticket.number), color=0x6B7280,
                                description=t(loc, "tk.closed_body", creator=f"<@{ticket.creator_id}>",
                                              closer=closer.mention if closer else "NEXUS",
                                              reason=reason or t(loc, "mod.no_reason")))
        if cfg and cfg.transcript_channel_id and transcript:
            target = guild.get_channel(cfg.transcript_channel_id)
            if isinstance(target, discord.abc.Messageable):
                try:
                    await target.send(embed=summary, file=transcript, allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    pass
        if cfg and cfg.dm_transcript and isinstance(channel, discord.TextChannel):
            creator = guild.get_member(ticket.creator_id)
            if creator:
                try:
                    await creator.send(embed=summary, file=await self._transcript(channel, ticket))
                except discord.HTTPException:
                    pass
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.delete(reason=f"NEXUS ticket #{ticket.number} closed")
            except discord.HTTPException:
                log.info("No se pudo borrar el canal del ticket %s", ticket.id)

    async def _transcript(self, channel: discord.TextChannel, ticket: Ticket) -> discord.File:
        rows = []
        async for m in channel.history(limit=2000, oldest_first=True):
            content = html.escape(m.clean_content).replace("\n", "<br>")
            files = "".join(f'<div class="a"><a href="{html.escape(a.url)}">{html.escape(a.filename)}</a></div>' for a in m.attachments)
            embeds = "".join(f'<div class="e">{html.escape(e.title or "")}<br>{html.escape(e.description or "")}</div>' for e in m.embeds)
            rows.append(f'<div class="m"><span class="t">{m.created_at:%Y-%m-%d %H:%M}</span> '
                        f'<b>{html.escape(str(m.author))}</b><div>{content}</div>{embeds}{files}</div>')
        doc = ("<!doctype html><meta charset='utf-8'><title>Ticket #{n}</title><style>body{{font-family:sans-serif;"
               "background:#313338;color:#dbdee1;padding:24px}}.m{{margin:10px 0}}.t{{color:#949ba4;font-size:12px}}"
               ".e{{border-left:4px solid #7465f7;padding:6px 10px;background:#2b2d31;margin-top:4px}}a{{color:#00a8fc}}"
               "</style><h1>Ticket #{n} · {c}</h1>{rows}").format(n=ticket.number, c=html.escape(ticket.creator_name),
                                                                    rows="".join(rows))
        return discord.File(io.BytesIO(doc.encode()), filename=f"ticket-{ticket.number:04d}.html")

    # --- comandos ---------------------------------------------------------
    @app_commands.command(name=key("cmd.ticket_close.name"), description=key("cmd.ticket_close.description"))
    @app_commands.describe(reason=key("arg.reason"))
    async def cmd_close(self, interaction: discord.Interaction, reason: str | None = None) -> None:
        await self.close_from_interaction(interaction, reason)

    @app_commands.command(name=key("cmd.ticket_open.name"), description=key("cmd.ticket_open.description"))
    @app_commands.describe(panel=key("arg.ticket_panel"), subject=key("arg.ticket_subject"))
    async def cmd_open(self, interaction: discord.Interaction, panel: str | None = None,
                       subject: app_commands.Range[str, 1, 500] | None = None) -> None:
        cfg = self._cfg(interaction.guild_id or 0)
        loc = self._loc(interaction.guild_id)
        panels = [p for p in (cfg.panels if cfg else []) if p.channel_id]
        chosen = next((p for p in panels if p.id == panel), None) if panel else (panels[0] if panels else None)
        if chosen is None:
            await interaction.response.send_message(t(loc, "tk.disabled"), ephemeral=True)
            return
        await self.open_ticket(interaction, chosen.id, subject)

    @cmd_open.autocomplete("panel")
    async def _panel_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        cfg = self._cfg(interaction.guild_id or 0)
        return [app_commands.Choice(name=p.name[:100], value=p.id) for p in (cfg.panels if cfg else [])
                if p.channel_id and current.lower() in p.name.lower()][:25]

    @app_commands.command(name=key("cmd.ticket_claim.name"), description=key("cmd.ticket_claim.description"))
    async def cmd_claim(self, interaction: discord.Interaction) -> None:
        await self.claim(interaction)

    @app_commands.command(name=key("cmd.ticket_rename.name"), description=key("cmd.ticket_rename.description"))
    @app_commands.describe(name=key("arg.room_name"))
    async def cmd_rename(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 90]) -> None:
        loc = self._loc(interaction.guild_id)
        ticket = await self._ticket_for(interaction.channel_id or 0)
        cfg = self._cfg(interaction.guild_id or 0)
        panel = next((p for p in cfg.panels if ticket and p.id == ticket.panel_id), None) if cfg else None
        if ticket is None or not isinstance(interaction.user, discord.Member) or not self._is_staff(interaction.user, panel):
            await interaction.response.send_message(t(loc, "tk.staff_only"), ephemeral=True)
            return
        assert isinstance(interaction.channel, discord.TextChannel)
        try:
            await interaction.channel.edit(name=name, reason=f"{interaction.user}: /ticket renombrar")
        except discord.HTTPException:
            await interaction.response.send_message(t(loc, "tv.rename_wait"), ephemeral=True)
            return
        await interaction.response.send_message(t(loc, "tk.renamed", name=interaction.channel.mention))

    @app_commands.command(name=key("cmd.ticket_add.name"), description=key("cmd.ticket_add.description"))
    @app_commands.describe(user=key("arg.user"))
    async def cmd_add(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await self._set_access(interaction, user, True)

    @app_commands.command(name=key("cmd.ticket_remove.name"), description=key("cmd.ticket_remove.description"))
    @app_commands.describe(user=key("arg.user"))
    async def cmd_remove(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await self._set_access(interaction, user, False)

    async def _set_access(self, interaction: discord.Interaction, user: discord.Member, allow: bool) -> None:
        loc = self._loc(interaction.guild_id)
        ticket = await self._ticket_for(interaction.channel_id or 0)
        cfg = self._cfg(interaction.guild_id or 0)
        panel = next((p for p in cfg.panels if ticket and p.id == ticket.panel_id), None) if cfg else None
        if ticket is None or not isinstance(interaction.user, discord.Member) or not self._is_staff(interaction.user, panel):
            await interaction.response.send_message(t(loc, "tk.staff_only"), ephemeral=True)
            return
        assert isinstance(interaction.channel, discord.TextChannel)
        await interaction.channel.set_permissions(user, view_channel=allow, send_messages=allow,
                                                  read_message_history=allow)
        await interaction.response.send_message(t(loc, "tk.added" if allow else "tk.removed", user=user.mention))

    # --- RPC y tareas -------------------------------------------------------
    async def rpc_publish(self, params: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        async with sessionmaker()() as db:
            row = await db.get(ModuleConfig, (int(params["guild_id"]), "tickets"))
        if guild is None or row is None:
            raise RpcFailure("module_disabled")
        cfg: TicketsConfig = parse_config("tickets", row.config, self._loc(guild.id))  # type: ignore[assignment]
        panel = next((p for p in cfg.panels if p.id == params["panel_id"]), None)
        if panel is None:
            raise RpcFailure("not_found")
        channel = guild.get_channel(panel.channel_id or 0)
        if not isinstance(channel, discord.TextChannel):
            raise RpcFailure("channel_not_found")
        state = self.bot.cache.get(guild.id)
        kwargs = await with_media(guild.id, render_payload(panel.message, context_for(guild.me, guild, channel.id, state.locale,
                                                                      state.timezone), state.embed_color))
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
        view = discord.ui.View(timeout=None)
        view.add_item(OpenButton(panel))
        try:
            msg = None
            if panel.message_id:
                try:
                    msg = await channel.fetch_message(panel.message_id)
                    await msg.edit(**for_edit(kwargs), view=view)
                except discord.NotFound:
                    msg = None
            if msg is None:
                msg = await channel.send(**kwargs, view=view)
        except discord.Forbidden as exc:
            raise RpcFailure("bot_cannot_send") from exc
        # Guardar el ID del mensaje en la configuración del módulo.
        data = cfg.model_dump(mode="json")
        for p in data["panels"]:
            if p["id"] == panel.id:
                p["message_id"] = str(msg.id)
        async with sessionmaker()() as db:
            await db.execute(update(ModuleConfig).where(ModuleConfig.guild_id == guild.id, ModuleConfig.module == "tickets")
                             .values(config=data, version=ModuleConfig.version + 1, updated_at=utcnow()))
            await db.commit()
        await self.bot.cache.reload_module(guild.id, "tickets")
        return {"message_id": str(msg.id)}

    async def rpc_close(self, params: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        async with sessionmaker()() as db:
            ticket = await db.scalar(select(Ticket).where(Ticket.guild_id == int(params["guild_id"]),
                                                          Ticket.number == int(params["number"]), Ticket.status == "open"))
        if ticket is None:
            raise RpcFailure("not_found")
        closer = self.bot.get_user(int(params["closer_id"])) or await self.bot.fetch_user(int(params["closer_id"]))
        await self.close_ticket(ticket, closer, params.get("reason"))
        return {"closed": True}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not message.channel.name.startswith("ticket-"):  # type: ignore[union-attr]
            return
        import time

        now = time.monotonic()
        if now - self._activity.get(message.channel.id, 0) < 300:
            return
        self._activity[message.channel.id] = now
        async with sessionmaker()() as db:
            await db.execute(update(Ticket).where(Ticket.channel_id == message.channel.id, Ticket.status == "open")
                             .values(last_activity_at=utcnow()))
            await db.commit()

    @tasks.loop(minutes=10)
    async def auto_close(self) -> None:
        for guild in self.bot.guilds:
            cfg = self._cfg(guild.id)
            if not cfg or not cfg.auto_close_hours:
                continue
            limit = utcnow() - timedelta(hours=cfg.auto_close_hours)
            async with sessionmaker()() as db:
                stale = (await db.scalars(select(Ticket).where(Ticket.guild_id == guild.id, Ticket.status == "open",
                                                               Ticket.last_activity_at < limit))).all()
            for ticket in stale:
                await self.close_ticket(ticket, None, t(self._loc(guild.id), "tk.auto_closed",
                                                        hours=cfg.auto_close_hours))

    @auto_close.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Tickets(bot))



