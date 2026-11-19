"""Bot principal: conexión, caché, sincronización con Redis, heartbeat y tareas."""

from __future__ import annotations

import asyncio
import functools
import json
import math
import logging
from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from discord.ext import commands, tasks

from nexus_core.config import get_settings
from nexus_core.db import dispose_engine, get_engine, sessionmaker
from nexus_core.db.models import ScheduledJob
from nexus_core.db.repo import add_audit, mark_bot_joined, mark_bot_left, upsert_guild, utcnow
from nexus_core.i18n import t
from nexus_core.redis_client import make_redis
from nexus_core.rpc import RPC_CHANNEL
from nexus_core.rpc import reply as rpc_reply
from nexus_core.sync import (
    HEARTBEAT_KEY,
    HEARTBEAT_TTL,
    SYNC_CHANNEL,
    guild_channels_key,
    guild_member_key,
    guild_roles_key,
    parse_event,
)

from nexus_bot.config_cache import ConfigCache
from nexus_bot.stats import StatsBuffer
from nexus_bot.translator import NexusTranslator
from nexus_bot.worker import ensure_recurring, run_due_jobs

log = logging.getLogger("nexus.bot")


class RpcFailure(Exception):
    """Error esperado de una petición RPC (se devuelve a la API con su código)."""

    def __init__(self, code: str, **extra: object):
        super().__init__(code)
        self.code = code
        self.extra = extra

EXTENSIONS = (
    "nexus_bot.cogs.general",
    "nexus_bot.cogs.utility",
    "nexus_bot.cogs.extras",
    "nexus_bot.cogs.games",
    "nexus_bot.cogs.tempvoice",
    "nexus_bot.cogs.voice_activity",
    "nexus_bot.cogs.counters",
    "nexus_bot.cogs.events",
    "nexus_bot.cogs.welcome",
    "nexus_bot.cogs.moderation",
    "nexus_bot.cogs.automod",
    "nexus_bot.cogs.antiraid",
    "nexus_bot.cogs.honeypot",
    "nexus_bot.cogs.logging_cog",
    "nexus_bot.cogs.autoroles",
    "nexus_bot.cogs.reaction_roles",
    "nexus_bot.cogs.tickets",
    "nexus_bot.cogs.community",
    "nexus_bot.cogs.custom_commands",
    "nexus_bot.cogs.responses",
    "nexus_bot.cogs.media",
    "nexus_bot.cogs.progression",
    "nexus_bot.cogs.integrations",
    "nexus_bot.cogs.ai_moderation",
)


def build_intents(message_content: bool = True) -> discord.Intents:
    intents = discord.Intents.none()
    intents.guilds = True
    intents.members = True  # privilegiado: entradas y salidas (Welcome/Goodbye), logs de miembros
    intents.moderation = True  # bans
    intents.guild_messages = True  # AutoMod y logs de mensajes
    intents.invites = True  # AutoMod: invitaciones del propio servidor
    intents.guild_reactions = True  # Reaction Roles por reacción (y Starboard en la fase 5)
    intents.voice_states = True  # canales de voz temporales (no es privilegiado)
    intents.message_content = message_content  # privilegiado: AutoMod necesita leer el texto
    return intents


class NexusBot(commands.Bot):
    def __init__(self, *, message_content: bool = True) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=build_intents(message_content),
                         help_command=None, allowed_mentions=discord.AllowedMentions(
                             everyone=False, roles=False, users=True))
        self.settings = get_settings()
        self.cache = ConfigCache()
        self.stats = StatsBuffer()
        self.redis = make_redis()
        self._listener_task: asyncio.Task | None = None
        self._ready_once = False
        # Tipos de tarea que necesitan el cliente de Discord (los cogs añaden los suyos).
        self.job_handlers: dict[str, Callable[[ScheduledJob], Awaitable[None]]] = {}
        # Peticiones de la API por Redis (nexus_core.rpc). Los cogs registran sus métodos.
        self.rpc_handlers: dict[str, Callable[[dict], Awaitable[dict]]] = {}

    # --- arranque ---------------------------------------------------------
    async def _on_command_error(self, interaction: discord.Interaction,
                                error: app_commands.AppCommandError) -> None:
        """Cualquier fallo de un comando: respuesta clara al usuario y la traza completa en el registro."""
        loc = self.cache.get(interaction.guild_id or 0).locale
        if isinstance(error, app_commands.CommandOnCooldown):
            text = f"⏳ {t(loc, 'error.cooldown', seconds=int(error.retry_after) + 1)}"
        elif isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            text = f"❌ {t(loc, 'staff.only')}"
        else:
            cmd = interaction.command.qualified_name if interaction.command else "?"
            log.error("Error en el comando /%s (servidor %s)", cmd, interaction.guild_id,
                      exc_info=getattr(error, "original", error))
            text = f"❌ {t(loc, 'error.command_failed')}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        except discord.HTTPException:
            pass

    async def setup_hook(self) -> None:
        get_engine()
        await self.tree.set_translator(NexusTranslator())
        self.tree.on_error = self._on_command_error  # type: ignore[method-assign]
        for ext in EXTENSIONS:
            await self.load_extension(ext)
        from nexus_bot import groups

        for group in groups.ALL:  # /info, /juego (subcomandos de varios cogs)
            if self.tree.get_command(group.name) is None:
                self.tree.add_command(group)
        from nexus_bot.cogs.welcome import delete_message_job
        from nexus_bot.modservice import ban_expire_job

        self.job_handlers["message.delete"] = functools.partial(delete_message_job, self)
        self.job_handlers["ban.expire"] = functools.partial(ban_expire_job, self)
        dev = self.settings.dev_guild_id
        if dev:
            guild = discord.Object(id=dev)
            self.tree.copy_global_to(guild=guild)
            try:
                synced = await self.tree.sync(guild=guild)
                log.info("%d comandos registrados en el servidor de pruebas %s", len(synced), dev)
            except discord.Forbidden:
                log.warning(
                    "El bot todavía no está en el servidor de pruebas %s (DEV_GUILD_ID). "
                    "Invítalo desde el dashboard; los comandos se registrarán al entrar.", dev)
        elif self.settings.is_production:
            synced = await self.tree.sync()
            log.info("%d comandos registrados globalmente", len(synced))
        await ensure_recurring()
        self._listener_task = asyncio.create_task(self._sync_listener(), name="nexus-sync")
        for loop in (self.heartbeat, self.flush_stats, self.reconcile_config, self.job_worker, self.watchdog):
            loop.start()

    async def close(self) -> None:
        for loop in (self.heartbeat, self.flush_stats, self.reconcile_config, self.job_worker, self.watchdog):
            loop.cancel()
        if self._listener_task:
            self._listener_task.cancel()
        await self.stats.flush()
        try:
            await self.redis.delete(HEARTBEAT_KEY)
        except Exception:
            pass
        await self.redis.aclose()
        await super().close()
        await dispose_engine()

    async def on_ready(self) -> None:
        log.info("Conectado como %s (%s) en %d servidores", self.user, self.user and self.user.id,
                 len(self.guilds))
        if self._ready_once:
            return
        self._ready_once = True
        await self._reconcile_guilds()
        await self.cache.load_all([g.id for g in self.guilds])

    async def _reconcile_guilds(self) -> None:
        """Corrige guilds.bot_present por si el bot entró o salió estando apagado."""
        from sqlalchemy import select

        from nexus_core.db.models import Guild

        current = {g.id: g for g in self.guilds}
        async with sessionmaker()() as db:
            marked = set((await db.scalars(select(Guild.id).where(Guild.bot_present.is_(True)))).all())
            for g in current.values():
                await upsert_guild(db, guild_id=g.id, name=g.name, icon=g.icon.key if g.icon else None,
                                   owner_id=g.owner_id or 0, member_count=g.member_count or 0)
                if await mark_bot_joined(db, g.id):
                    await add_audit(db, guild_id=g.id, action="bot.join", source="bot")
            for gid in marked - set(current):
                await mark_bot_left(db, gid)
                await add_audit(db, guild_id=gid, action="bot.leave", source="bot")
            await db.commit()

    # --- servidores -------------------------------------------------------
    async def on_guild_join(self, guild: discord.Guild) -> None:
        async with sessionmaker()() as db:
            await upsert_guild(db, guild_id=guild.id, name=guild.name,
                               icon=guild.icon.key if guild.icon else None,
                               owner_id=guild.owner_id or 0, member_count=guild.member_count or 0)
            await mark_bot_joined(db, guild.id)
            await add_audit(db, guild_id=guild.id, action="bot.join", source="bot")
            await db.commit()
        await self.cache.reload_guild(guild.id)
        if self.settings.dev_guild_id == guild.id:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        log.info("Entré al servidor %s (%s)", guild.name, guild.id)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        async with sessionmaker()() as db:
            await mark_bot_left(db, guild.id)
            await add_audit(db, guild_id=guild.id, action="bot.leave", source="bot")
            await db.commit()
        self.cache.forget(guild.id)
        log.info("Salí del servidor %s (%s)", guild.name, guild.id)

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if (before.name, before.icon, before.owner_id) != (after.name, after.icon, after.owner_id):
            async with sessionmaker()() as db:
                await upsert_guild(db, guild_id=after.id, name=after.name,
                                   icon=after.icon.key if after.icon else None,
                                   owner_id=after.owner_id or 0)
                await db.commit()

    # --- miembros ---------------------------------------------------------
    async def on_member_join(self, member: discord.Member) -> None:
        self.stats.incr(member.guild.id, "members_joined")
        self.stats.set_member_count(member.guild.id, member.guild.member_count or 0)

    async def on_member_remove(self, member: discord.Member) -> None:
        self.stats.incr(member.guild.id, "members_left")
        self.stats.set_member_count(member.guild.id, member.guild.member_count or 0)

    async def on_app_command_completion(self, interaction: discord.Interaction, command) -> None:  # type: ignore[no-untyped-def]
        if interaction.guild_id:
            self.stats.incr(interaction.guild_id, "commands_used")

    # --- caché de canales y roles que usa la API --------------------------
    async def _drop_keys(self, *keys: str) -> None:
        try:
            await self.redis.delete(*keys)
        except Exception:
            pass

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self._drop_keys(guild_channels_key(channel.guild.id))

    on_guild_channel_delete = on_guild_channel_create

    async def on_guild_channel_update(self, before: discord.abc.GuildChannel,
                                      after: discord.abc.GuildChannel) -> None:
        await self._drop_keys(guild_channels_key(after.guild.id))

    async def on_guild_role_create(self, role: discord.Role) -> None:
        gid = role.guild.id
        await self._drop_keys(guild_roles_key(gid), guild_member_key(gid, self.user.id if self.user else 0))

    on_guild_role_delete = on_guild_role_create

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        await self.on_guild_role_create(after)

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if self.user and after.id == self.user.id and before.roles != after.roles:
            await self._drop_keys(guild_member_key(after.guild.id, after.id))

    # --- sincronización con el dashboard ----------------------------------
    async def _sync_listener(self) -> None:
        backoff = 1
        while not self.is_closed():
            try:
                pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
                await pubsub.subscribe(SYNC_CHANNEL, RPC_CHANNEL)
                log.info("Escuchando cambios del dashboard en Redis (%s, %s)", SYNC_CHANNEL, RPC_CHANNEL)
                if self.is_ready():
                    # Pudimos perder avisos mientras Redis no estaba: recarga completa.
                    await self.cache.load_all([g.id for g in self.guilds])
                backoff = 1
                async for message in pubsub.listen():
                    if message.get("channel") == RPC_CHANNEL:
                        asyncio.create_task(self._handle_rpc(message.get("data", "")))
                        continue
                    event = parse_event(message.get("data", ""))
                    if event:
                        await self._handle_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Conexión con Redis perdida (%s). Reintento en %ss", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _handle_rpc(self, raw: str) -> None:
        from nexus_bot.modservice import ModError

        try:
            req = json.loads(raw)
            rid, method, params = req["id"], req["method"], req.get("params", {})
        except (ValueError, KeyError, TypeError):
            return
        handler = self.rpc_handlers.get(method)
        if handler is None:
            await rpc_reply(self.redis, rid, error="unknown_method")
            return
        try:
            await rpc_reply(self.redis, rid, result=await handler(params))
        except ModError as exc:
            from nexus_core.i18n import t

            loc = self.cache.get(int(params.get("guild_id", 0))).locale
            await rpc_reply(self.redis, rid, error=exc.key.replace(".", "_"),
                            extra={"detail": t(loc, exc.key, **exc.params)})
        except RpcFailure as exc:
            await rpc_reply(self.redis, rid, error=exc.code, extra=exc.extra)
        except Exception:
            log.exception("Error en la petición %s", method)
            await rpc_reply(self.redis, rid, error="bot_error")

    async def _handle_event(self, event: dict) -> None:
        gid = event["guild_id"]
        if self.get_guild(gid) is None:
            return
        kind = event.get("type")
        if kind in ("module.updated", "module.toggled") and event.get("module"):
            await self.cache.reload_module(gid, event["module"], event.get("version"))
        elif kind == "settings.updated":
            await self.cache.reload_settings(gid, event.get("version"))
        elif kind == "guild.reload":
            await self.cache.reload_guild(gid)
        elif kind == "commands.sync":
            cog = self.get_cog("CustomCommands")
            if cog is not None:
                await cog.sync_guild(gid)  # type: ignore[attr-defined]
        log.info("Configuración actualizada: %s en %s", kind, gid)

    # --- tareas periódicas ------------------------------------------------
    @tasks.loop(seconds=10)
    async def heartbeat(self) -> None:
        payload = {
            # Sin conexión la latencia es NaN o infinita: entonces se envía None (antes rompía esta tarea para siempre).
            "latency_ms": round(self.latency * 1000) if math.isfinite(self.latency) else None,
            "guilds": len(self.guilds),
            "shard": self.shard_id,
            "at": utcnow().isoformat(),
            "intents": {"guild_members": self.intents.members,
                        "message_content": self.intents.message_content},
        }
        try:
            await self.redis.set(HEARTBEAT_KEY, json.dumps(payload), ex=HEARTBEAT_TTL)
        except Exception as exc:
            log.debug("Heartbeat no enviado: %s", exc)

    @heartbeat.before_loop
    async def _before_heartbeat(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(seconds=60)
    async def flush_stats(self) -> None:
        await self.stats.flush()

    @tasks.loop(minutes=5)
    async def reconcile_config(self) -> None:
        changed = await self.cache.check_updates()
        if changed:
            log.info("Revisión periódica: %d configuraciones recargadas", changed)

    @reconcile_config.before_loop
    async def _before_reconcile(self) -> None:
        await self.wait_until_ready()
        await asyncio.sleep(300)

    def _all_loops(self) -> list[tuple[str, tasks.Loop]]:  # type: ignore[type-arg]
        """Tareas periódicas del bot y de todos los cogs."""
        found = [(name, getattr(self, name)) for name in ("heartbeat", "flush_stats", "reconcile_config", "job_worker")]
        for cog_name, cog in self.cogs.items():
            for attr in dir(cog):
                value = getattr(cog, attr, None)
                if isinstance(value, tasks.Loop):
                    found.append((f"{cog_name}.{attr}", value))
        return found

    @tasks.loop(seconds=60)
    async def watchdog(self) -> None:
        """discord.py detiene para siempre una tarea periódica si lanza un error inesperado: aquí se reinicia."""
        for name, lp in self._all_loops():
            if lp.failed() or (not lp.is_running() and not lp.is_being_cancelled() and lp.current_loop > 0):
                log.error("La tarea periódica %s se detuvo por un error; reiniciándola", name)
                try:
                    lp.restart() if lp.is_running() else lp.start()
                except RuntimeError:
                    pass

    @watchdog.before_loop
    async def _before_watchdog(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(seconds=5)
    async def job_worker(self) -> None:
        try:
            await run_due_jobs(self.job_handlers)
        except Exception:
            log.exception("Error en el worker de tareas")

    @job_worker.before_loop
    async def _before_worker(self) -> None:
        await self.wait_until_ready()
