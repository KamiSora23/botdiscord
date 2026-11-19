"""Canales de voz temporales: «➕ Crear sala» crea una sala propia; se borra al quedar vacía. Comandos /voz."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks
from sqlalchemy import delete, select, update

from nexus_core.db import sessionmaker
from nexus_core.db.models import TempVoiceChannel
from nexus_core.i18n import t
from nexus_core.modules import parse_config
from nexus_core.modules.tempvoice import TempVoiceConfig, room_name

from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.tempvoice")

CREATE_COOLDOWN = 10  # segundos entre salas de una misma persona (evita abusos entrando y saliendo)
OWNER_PERMS = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True,
                                          manage_channels=True, move_members=True, mute_members=True)


def _only_granted(ow: discord.PermissionOverwrite, mine: discord.Permissions) -> discord.PermissionOverwrite:
    """Copia de ``ow`` sin los permisos permitidos que el bot no tiene en el servidor."""
    if mine.administrator:
        return ow
    allow, deny = ow.pair()
    return discord.PermissionOverwrite.from_pair(discord.Permissions(allow.value & mine.value), deny)


class TempVoice(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self.rooms: dict[int, int] = {}  # canal → dueño (copia en memoria de la tabla)
        self._last_create: dict[tuple[int, int], float] = {}
        bot.rpc_handlers["tempvoice.setup"] = self.rpc_setup
        self.cleanup.start()

    def cog_unload(self) -> None:
        self.cleanup.cancel()

    def cfg(self, guild_id: int) -> TempVoiceConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("tempvoice")
        return parse_config("tempvoice", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    def loc(self, guild_id: int | None) -> str:
        return self.bot.cache.get(guild_id or 0).locale

    # --- Creación y borrado -------------------------------------------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if before.channel and before.channel.id in self.rooms and before.channel != after.channel:
            await self._maybe_delete(before.channel)  # type: ignore[arg-type]
        if after.channel is None or member.bot:
            return
        cfg = self.cfg(member.guild.id)
        if cfg and cfg.hub_channel_id and after.channel.id == cfg.hub_channel_id:
            await self._create_room(member, after.channel, cfg)  # type: ignore[arg-type]

    async def _create_room(self, member: discord.Member, hub: discord.VoiceChannel, cfg: TempVoiceConfig) -> None:
        guild = member.guild
        owned = [cid for cid, owner in self.rooms.items() if owner == member.id and guild.get_channel(cid)]
        if len(owned) >= cfg.max_rooms_per_user:
            room = guild.get_channel(owned[0])
            if isinstance(room, discord.VoiceChannel):
                await self._move(member, room)
            return
        k = (guild.id, member.id)
        if time.monotonic() - self._last_create.get(k, 0) < CREATE_COOLDOWN:
            await self._move(member, None)  # lo saca del hub para que no se quede ahí
            return
        self._last_create[k] = time.monotonic()
        category = guild.get_channel(cfg.category_id or 0)
        if not isinstance(category, discord.CategoryChannel):
            category = hub.category
        overwrites = dict(category.overwrites) if category else {}
        # Discord no deja conceder en un canal permisos que el bot no tiene: solo se dan los que sí tiene.
        mine = guild.me.guild_permissions
        overwrites[member] = _only_granted(OWNER_PERMS, mine)
        overwrites[guild.me] = _only_granted(discord.PermissionOverwrite(
            view_channel=True, connect=True, manage_channels=True, move_members=True), mine)
        if not mine.move_members:
            log.warning("Salas temporales en %s: a NEXUS le falta «Mover miembros»; no podrá mover a nadie", guild.id)
        try:
            room = await guild.create_voice_channel(
                room_name(cfg.name_template, member.display_name), category=category, overwrites=overwrites,
                user_limit=cfg.default_limit, reason=f"NEXUS sala temporal de {member}")
        except discord.HTTPException as exc:
            log.warning("No se pudo crear la sala temporal en %s: %s", guild.id, exc)
            return
        self.rooms[room.id] = member.id
        async with sessionmaker()() as db:
            db.add(TempVoiceChannel(channel_id=room.id, guild_id=guild.id, owner_id=member.id))
            await db.commit()
        if not await self._move(member, room):
            await self._maybe_delete(room)  # se fue antes de poder moverlo
        else:
            log.info("Sala temporal %s creada en %s para %s", room.id, guild.id, member.id)

    async def _move(self, member: discord.Member, channel: discord.VoiceChannel | None) -> bool:
        try:
            await member.move_to(channel, reason="NEXUS sala temporal")
            return True
        except discord.HTTPException:
            return False

    async def _maybe_delete(self, channel: discord.abc.GuildChannel) -> None:
        if not isinstance(channel, discord.VoiceChannel) or any(not m.bot for m in channel.members):
            return
        await self._forget(channel.id)
        try:
            await channel.delete(reason="NEXUS: sala temporal vacía")
        except discord.NotFound:
            pass
        except discord.HTTPException as exc:
            log.info("No se pudo borrar la sala %s: %s", channel.id, exc)

    async def _forget(self, channel_id: int) -> None:
        self.rooms.pop(channel_id, None)
        async with sessionmaker()() as db:
            await db.execute(delete(TempVoiceChannel).where(TempVoiceChannel.channel_id == channel_id))
            await db.commit()

    @tasks.loop(minutes=5)
    async def cleanup(self) -> None:
        """Recupera las salas de la base de datos (tras un reinicio) y borra las vacías o desaparecidas."""
        async with sessionmaker()() as db:
            rows = (await db.execute(select(TempVoiceChannel.channel_id, TempVoiceChannel.owner_id))).all()
        for cid, owner in rows:
            self.rooms.setdefault(cid, owner)
            channel = self.bot.get_channel(cid)
            if channel is None:
                if self.bot.is_ready():
                    await self._forget(cid)
                continue
            await self._maybe_delete(channel)  # type: ignore[arg-type]

    @cleanup.before_loop
    async def _wait_ready(self) -> None:
        await self.bot.wait_until_ready()

    # --- RPC: crear categoría y «➕ Crear sala» desde el panel ---------------------------
    async def rpc_setup(self, params: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        if guild is None:
            raise RpcFailure("not_found")
        es = self.loc(guild.id) == "es"
        try:
            category = await guild.create_category("🔊 Salas temporales" if es else "🔊 Temporary rooms",
                                                   reason="NEXUS salas temporales")
            hub = await guild.create_voice_channel("➕ Crear sala" if es else "➕ Create room", category=category,
                                                   reason="NEXUS salas temporales")
        except discord.Forbidden as exc:
            raise RpcFailure("bot_missing_permissions") from exc
        return {"category_id": str(category.id), "hub_channel_id": str(hub.id)}

    # --- Comandos /voz --------------------------------------------------------------------
    voice = app_commands.Group(name=key("cmd.voice.name"), description=key("cmd.voice.description"), guild_only=True)

    async def _room(self, i: discord.Interaction, *, owner_only: bool = True) -> discord.VoiceChannel | None:
        loc = self.loc(i.guild_id)
        if i.guild_id and self.cfg(i.guild_id) is None:
            await i.response.send_message(t(loc, "tv.disabled"), ephemeral=True)
            return None
        state = i.user.voice if isinstance(i.user, discord.Member) else None
        channel = state.channel if state else None
        if not isinstance(channel, discord.VoiceChannel) or channel.id not in self.rooms:
            await i.response.send_message(t(loc, "tv.not_in_room"), ephemeral=True)
            return None
        if owner_only and self.rooms[channel.id] != i.user.id:
            await i.response.send_message(t(loc, "tv.not_owner"), ephemeral=True)
            return None
        return channel

    async def _reply(self, i: discord.Interaction, text: str) -> None:
        await i.response.send_message(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @voice.command(name=key("cmd.voice_lock.name"), description=key("cmd.voice_lock.description"))
    async def lock(self, i: discord.Interaction) -> None:
        room = await self._room(i)
        if room:
            await room.set_permissions(room.guild.default_role, connect=False, reason="NEXUS /voz cerrar")
            await self._reply(i, t(self.loc(i.guild_id), "tv.locked"))

    @voice.command(name=key("cmd.voice_unlock.name"), description=key("cmd.voice_unlock.description"))
    async def unlock(self, i: discord.Interaction) -> None:
        room = await self._room(i)
        if room:
            await room.set_permissions(room.guild.default_role, connect=None, reason="NEXUS /voz abrir")
            await self._reply(i, t(self.loc(i.guild_id), "tv.unlocked"))

    @voice.command(name=key("cmd.voice_limit.name"), description=key("cmd.voice_limit.description"))
    @app_commands.describe(limit=key("arg.limit"))
    async def limit(self, i: discord.Interaction, limit: app_commands.Range[int, 0, 99]) -> None:
        room = await self._room(i)
        if room:
            await room.edit(user_limit=limit, reason="NEXUS /voz limite")
            loc = self.loc(i.guild_id)
            await self._reply(i, t(loc, "tv.limit", limit=limit) if limit else t(loc, "tv.no_limit"))

    @voice.command(name=key("cmd.voice_name.name"), description=key("cmd.voice_name.description"))
    @app_commands.describe(name=key("arg.room_name"))
    async def name(self, i: discord.Interaction, name: app_commands.Range[str, 1, 100]) -> None:
        room = await self._room(i)
        if not room:
            return
        loc = self.loc(i.guild_id)
        try:
            await room.edit(name=name, reason="NEXUS /voz nombre")
        except discord.HTTPException:
            await self._reply(i, t(loc, "tv.rename_wait"))
            return
        await self._reply(i, t(loc, "tv.renamed", name=discord.utils.escape_markdown(name)))

    @voice.command(name=key("cmd.voice_permit.name"), description=key("cmd.voice_permit.description"))
    @app_commands.describe(user=key("arg.user"))
    async def permit(self, i: discord.Interaction, user: discord.Member) -> None:
        room = await self._room(i)
        if room:
            await room.set_permissions(user, view_channel=True, connect=True, reason="NEXUS /voz permitir")
            await self._reply(i, t(self.loc(i.guild_id), "tv.permitted", user=user.mention))

    @voice.command(name=key("cmd.voice_reject.name"), description=key("cmd.voice_reject.description"))
    @app_commands.describe(user=key("arg.user"))
    async def reject(self, i: discord.Interaction, user: discord.Member) -> None:
        room = await self._room(i)
        if not room:
            return
        loc = self.loc(i.guild_id)
        if user.id == i.user.id:
            await self._reply(i, t(loc, "tv.self"))
            return
        await room.set_permissions(user, connect=False, reason="NEXUS /voz echar")
        if user.voice and user.voice.channel == room:
            await self._move(user, None)
        await self._reply(i, t(loc, "tv.rejected", user=user.mention))

    @voice.command(name=key("cmd.voice_claim.name"), description=key("cmd.voice_claim.description"))
    async def claim(self, i: discord.Interaction) -> None:
        room = await self._room(i, owner_only=False)
        if not room:
            return
        loc = self.loc(i.guild_id)
        owner_id = self.rooms[room.id]
        if owner_id == i.user.id or any(m.id == owner_id for m in room.members):
            await self._reply(i, t(loc, "tv.owner_here"))
            return
        old = room.guild.get_member(owner_id)
        if old:
            await room.set_permissions(old, overwrite=None, reason="NEXUS /voz reclamar")
        await room.set_permissions(i.user, overwrite=OWNER_PERMS, reason="NEXUS /voz reclamar")  # type: ignore[arg-type]
        self.rooms[room.id] = i.user.id
        async with sessionmaker()() as db:
            await db.execute(update(TempVoiceChannel).where(TempVoiceChannel.channel_id == room.id)
                             .values(owner_id=i.user.id))
            await db.commit()
        await self._reply(i, t(loc, "tv.claimed"))

    @voice.command(name=key("cmd.voice_bitrate.name"), description=key("cmd.voice_bitrate.description"))
    @app_commands.describe(kbps=key("arg.kbps"))
    async def bitrate(self, i: discord.Interaction, kbps: app_commands.Range[int, 8, 384]) -> None:
        room = await self._room(i)
        if not room:
            return
        loc = self.loc(i.guild_id)
        limit = int(room.guild.bitrate_limit // 1000)
        if kbps > limit:
            await self._reply(i, t(loc, "tv.bitrate_max", max=limit))
            return
        await room.edit(bitrate=kbps * 1000, reason="NEXUS /voz calidad")
        await self._reply(i, t(loc, "tv.bitrate", kbps=kbps))


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(TempVoice(bot))
