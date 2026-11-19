"""Comandos personalizados: cada servidor registra los suyos como comandos slash propios."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select, update

from nexus_core.db import sessionmaker
from nexus_core.db.models import CustomCommand, ScheduledMessage
from nexus_core.db.repo import utcnow
from nexus_core.messages import MessageTemplate, render_payload
from nexus_core.scheduling import schedule_message_job

from nexus_bot.cogs.welcome import context_for, with_media

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.custom")


class CustomCommands(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self._registered: dict[int, set[str]] = {}
        bot.job_handlers["scheduled_message.send"] = self.job_scheduled
        bot.rpc_handlers["scheduled.send_now"] = self.rpc_send_now

    async def cog_load(self) -> None:
        self.bot.loop.create_task(self._initial_sync())

    async def _initial_sync(self) -> None:
        await self.bot.wait_until_ready()
        async with sessionmaker()() as db:
            guild_ids = set((await db.scalars(select(CustomCommand.guild_id).distinct())).all())
        for gid in guild_ids:
            if self.bot.get_guild(gid):
                await self.sync_guild(gid)

    def _make(self, cmd: CustomCommand) -> app_commands.Command:
        cmd_id = cmd.id

        async def callback(interaction: discord.Interaction) -> None:
            await self.run(interaction, cmd_id)

        return app_commands.Command(name=cmd.name, description=cmd.description[:100], callback=callback,
                                    guild_ids=None)

    async def sync_guild(self, guild_id: int) -> None:
        """Vuelve a registrar los comandos del servidor (se llama cuando cambian en el panel)."""
        guild = discord.Object(id=guild_id)
        for name in self._registered.get(guild_id, set()):
            self.bot.tree.remove_command(name, guild=guild)
        async with sessionmaker()() as db:
            cmds = (await db.scalars(select(CustomCommand).where(CustomCommand.guild_id == guild_id,
                                                                 CustomCommand.enabled.is_(True)))).all()
        names: set[str] = set()
        for c in cmds:
            try:
                self.bot.tree.add_command(self._make(c), guild=guild, override=True)
                names.add(c.name)
            except app_commands.CommandAlreadyRegistered:
                log.info("Nombre de comando repetido en %s: %s", guild_id, c.name)
        self._registered[guild_id] = names
        if self.bot.settings.dev_guild_id == guild_id:
            self.bot.tree.copy_global_to(guild=guild)
        try:
            await self.bot.tree.sync(guild=guild)
        except discord.HTTPException as exc:
            log.warning("No se pudieron registrar los comandos de %s: %s", guild_id, exc)

    async def run(self, interaction: discord.Interaction, cmd_id: int) -> None:
        async with sessionmaker()() as db:
            cmd = await db.get(CustomCommand, cmd_id)
            if cmd is None or not cmd.enabled or cmd.guild_id != interaction.guild_id:
                await interaction.response.send_message("❌", ephemeral=True)
                return
            await db.execute(update(CustomCommand).where(CustomCommand.id == cmd_id).values(uses=CustomCommand.uses + 1))
            await db.commit()
        guild, member = interaction.guild, interaction.user
        assert guild and isinstance(member, discord.Member)
        if cmd.allowed_role_ids and not member.guild_permissions.manage_guild and \
                not {r.id for r in member.roles} & set(cmd.allowed_role_ids):
            await interaction.response.send_message("🔒", ephemeral=True)
            return
        state = self.bot.cache.get(guild.id)
        payload = render_payload(MessageTemplate.model_validate(cmd.response),
                                 context_for(member, guild, interaction.channel_id, state.locale, state.timezone),
                                 state.embed_color)
        kwargs = await with_media(guild.id, payload)
        kwargs["allowed_mentions"] = discord.AllowedMentions(users=[member], everyone=False, roles=False)
        await interaction.response.send_message(**kwargs, ephemeral=cmd.ephemeral)
        me = guild.me
        add = [r for x in cmd.add_role_ids if (r := guild.get_role(x)) and r < me.top_role]
        rem = [r for x in cmd.remove_role_ids if (r := guild.get_role(x)) and r < me.top_role]
        try:
            if add:
                await member.add_roles(*add, reason=f"NEXUS /{cmd.name}")
            if rem:
                await member.remove_roles(*rem, reason=f"NEXUS /{cmd.name}")
        except discord.HTTPException:
            pass
        self.bot.stats.incr(guild.id, "commands_used")

    # --- Mensajes programados -----------------------------------------------
    async def send_scheduled(self, m: ScheduledMessage) -> discord.Message:
        guild = self.bot.get_guild(m.guild_id)
        channel = guild.get_channel(m.channel_id) if guild else None
        if guild is None or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise RuntimeError("channel_not_found")
        state = self.bot.cache.get(guild.id)
        payload = render_payload(MessageTemplate.model_validate(m.message),
                                 context_for(guild.me, guild, channel.id, state.locale, state.timezone),
                                 state.embed_color)
        kwargs = await with_media(guild.id, payload)
        kwargs["allowed_mentions"] = discord.AllowedMentions(everyone=True, roles=True, users=True)
        return await channel.send(**kwargs)

    async def job_scheduled(self, job: Any) -> None:
        async with sessionmaker()() as db:
            m = await db.get(ScheduledMessage, int(job.payload["id"]))
            if m is None or m.status != "scheduled":
                return
            if self.bot.cache.get(m.guild_id).module("scheduled_messages") is None:
                return
            try:
                await self.send_scheduled(m)
                m.last_sent_at, m.last_error = utcnow(), None
            except Exception as exc:  # noqa: BLE001 - se guarda el error para mostrarlo en el panel
                m.last_error = str(exc)[:300]
            if m.repeat == "none":
                m.status = "sent" if m.last_error is None else "failed"
                m.next_run_at = None
            else:
                await schedule_message_job(db, m, self.bot.cache.get(m.guild_id).timezone)
            await db.commit()

    async def rpc_send_now(self, p: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        async with sessionmaker()() as db:
            m = await db.get(ScheduledMessage, int(p["id"]))
            if m is None or m.guild_id != int(p["guild_id"]):
                raise RpcFailure("not_found")
            try:
                msg = await self.send_scheduled(m)
            except discord.Forbidden as exc:
                raise RpcFailure("bot_cannot_send") from exc
            except RuntimeError as exc:
                raise RpcFailure("channel_not_found") from exc
            m.last_sent_at = utcnow()
            await db.commit()
        return {"jump_url": msg.jump_url}


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(CustomCommands(bot))
