"""Eventos con inscripción: tarjeta con botones, cupos, recordatorio por MD y aviso al empezar."""

from __future__ import annotations

import io
import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from nexus_core import media as M
from nexus_core.db import sessionmaker
from nexus_core.db.models import Event, EventRsvp, ScheduledJob
from nexus_core.db.repo import utcnow
from nexus_core.i18n import t
from nexus_core.modules import parse_config
from nexus_core.modules.events import EventsConfig, parse_when

from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.events")
STYLES = {"going": discord.ButtonStyle.success, "maybe": discord.ButtonStyle.secondary, "no": discord.ButtonStyle.danger}
EMOJI = {"going": "✅", "maybe": "❔", "no": "❌"}


class RsvpButton(discord.ui.DynamicItem[discord.ui.Button], template=r"nexus:ev:(?P<id>\d+):(?P<status>going|maybe|no)"):
    def __init__(self, event_id: int, status: str, label: str, disabled: bool = False) -> None:
        super().__init__(discord.ui.Button(label=label, emoji=EMOJI[status], style=STYLES[status], disabled=disabled,
                                           custom_id=f"nexus:ev:{event_id}:{status}"))
        self.event_id, self.status = event_id, status

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):  # type: ignore[no-untyped-def]
        inst = cls.__new__(cls)
        discord.ui.DynamicItem.__init__(inst, item)
        inst.event_id, inst.status = int(match["id"]), match["status"]
        return inst

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Events = interaction.client.get_cog("Events")  # type: ignore[union-attr,assignment]
        await cog.rsvp(interaction, self.event_id, self.status)


class Events(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        bot.add_dynamic_items(RsvpButton)
        bot.job_handlers["event.reminder"] = self.job_reminder
        bot.job_handlers["event.start"] = self.job_start
        bot.rpc_handlers["events.create"] = self.rpc_create
        bot.rpc_handlers["events.cancel"] = self.rpc_cancel

    def cfg(self, guild_id: int) -> EventsConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("events")
        return parse_config("events", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    def loc(self, guild_id: int | None) -> str:
        return self.bot.cache.get(guild_id or 0).locale

    # --- Tarjeta del evento -------------------------------------------------------------------
    async def render(self, ev: Event) -> tuple[discord.Embed, discord.ui.View]:
        loc = self.loc(ev.guild_id)
        async with sessionmaker()() as db:
            rows = (await db.execute(select(EventRsvp.status, EventRsvp.user_id)
                                     .where(EventRsvp.event_id == ev.id).order_by(EventRsvp.updated_at))).all()
        by: dict[str, list[int]] = {"going": [], "maybe": [], "no": []}
        for status, uid in rows:
            by[status].append(uid)
        color = 0x7465F7 if ev.status == "scheduled" else (0x22C55E if ev.status == "started" else 0x6B7280)
        title = ev.title if ev.status == "scheduled" else f"{t(loc, f'ev.status_{ev.status}')} · {ev.title}"
        e = discord.Embed(title=title[:256], description=ev.description[:3500] or None, color=color)
        ts = int(ev.starts_at.timestamp())
        e.add_field(name=t(loc, "ev.when"), value=f"<t:{ts}:F>\n<t:{ts}:R>", inline=False)  # cada uno lo ve en su zona

        def people(ids: list[int], limit: int = 20) -> str:
            if not ids:
                return t(loc, "ev.nobody")
            shown = " ".join(f"<@{u}>" for u in ids[:limit])
            return shown + (f" +{len(ids) - limit}" if len(ids) > limit else "")

        slots = f" ({len(by['going'])}/{ev.max_slots})" if ev.max_slots else f" ({len(by['going'])})"
        e.add_field(name=t(loc, "ev.going") + slots, value=people(by["going"]), inline=False)
        e.add_field(name=f"{t(loc, 'ev.maybe')} ({len(by['maybe'])})", value=people(by["maybe"], 10))
        e.add_field(name=f"{t(loc, 'ev.no')} ({len(by['no'])})", value=str(len(by["no"])))
        if ev.image_url and ev.image_url.startswith("https://"):
            e.set_image(url=ev.image_url)
        elif ev.image_url:  # imagen subida: va adjunta a la tarjeta y el embed la referencia por nombre
            async with sessionmaker()() as db:
                if name := await M.attachment_name(db, ev.guild_id, ev.image_url):
                    e.set_image(url=f"attachment://{name}")
        e.set_footer(text=f"#{ev.id}")
        view = discord.ui.View(timeout=None)
        closed = ev.status != "scheduled"
        for st in ("going", "maybe", "no"):
            view.add_item(RsvpButton(ev.id, st, t(loc, f"ev.btn_{st}"), disabled=closed))
        return e, view

    async def refresh_message(self, ev: Event) -> None:
        channel = self.bot.get_channel(ev.channel_id)
        if not isinstance(channel, discord.abc.Messageable) or not ev.message_id:
            return
        embed, view = await self.render(ev)
        try:
            await channel.get_partial_message(ev.message_id).edit(embed=embed, view=view)  # type: ignore[union-attr]
        except discord.HTTPException:
            pass

    # --- Crear / cancelar ------------------------------------------------------------------------
    async def create(self, guild: discord.Guild, *, title: str, description: str, starts_at, channel_id: int,  # type: ignore[no-untyped-def]
                     max_slots: int | None, image_url: str | None, creator_id: int) -> Event:
        from nexus_bot.client import RpcFailure

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise RpcFailure("channel_not_found")
        cfg = self.cfg(guild.id) or EventsConfig()
        async with sessionmaker()() as db:
            ev = Event(guild_id=guild.id, title=title, description=description, starts_at=starts_at,
                       channel_id=channel.id, max_slots=max_slots, image_url=image_url, created_by=creator_id)
            db.add(ev)
            await db.flush()
            if cfg.reminder_minutes:
                remind_at = starts_at - timedelta(minutes=cfg.reminder_minutes)
                if remind_at > utcnow():
                    db.add(ScheduledJob(guild_id=guild.id, job_type="event.reminder", run_at=remind_at,
                                        payload={"event_id": str(ev.id)}, dedupe_key=f"event.reminder:{ev.id}"))
            db.add(ScheduledJob(guild_id=guild.id, job_type="event.start", run_at=starts_at,
                                payload={"event_id": str(ev.id)}, dedupe_key=f"event.start:{ev.id}"))
            await db.commit()
            await db.refresh(ev)
        embed, view = await self.render(ev)
        files: list[discord.File] = []
        if mid := M.media_id(ev.image_url):
            async with sessionmaker()() as db:
                files = [discord.File(io.BytesIO(f.data), filename=f.name)
                         for f in await M.load(db, guild.id, [mid])]
        try:
            msg = await channel.send(embed=embed, view=view, files=files,
                                     allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden as exc:
            await self._set_status(ev.id, "cancelled")
            raise RpcFailure("bot_cannot_send") from exc
        async with sessionmaker()() as db:
            await db.execute(update(Event).where(Event.id == ev.id).values(message_id=msg.id))
            await db.commit()
        ev.message_id = msg.id
        log.info("Evento %s creado en %s", ev.id, guild.id)
        return ev

    async def _set_status(self, event_id: int, status: str) -> Event | None:
        async with sessionmaker()() as db:
            ev = await db.get(Event, event_id)
            if ev is None:
                return None
            ev.status = status
            if status == "cancelled":
                await db.execute(update(ScheduledJob).where(
                    ScheduledJob.status == "pending", ScheduledJob.job_type.in_(("event.reminder", "event.start")),
                    ScheduledJob.payload["event_id"].astext == str(event_id)).values(status="cancelled"))
            await db.commit()
            await db.refresh(ev)
            return ev

    async def cancel(self, guild_id: int, event_id: int) -> bool:
        async with sessionmaker()() as db:
            ev = await db.get(Event, event_id)
        if ev is None or ev.guild_id != guild_id or ev.status == "cancelled":
            return False
        ev = await self._set_status(event_id, "cancelled")
        if ev:
            await self.refresh_message(ev)
        return True

    # --- Inscripción -------------------------------------------------------------------------------
    async def rsvp(self, i: discord.Interaction, event_id: int, status: str) -> None:
        loc = self.loc(i.guild_id)
        async with sessionmaker()() as db:
            ev = await db.get(Event, event_id)
            if ev is None or ev.status != "scheduled":
                await i.response.send_message(t(loc, "ev.closed"), ephemeral=True)
                return
            if status == "going" and ev.max_slots:
                going = await db.scalar(select(func.count()).select_from(EventRsvp).where(
                    EventRsvp.event_id == ev.id, EventRsvp.status == "going", EventRsvp.user_id != i.user.id))
                if going >= ev.max_slots:
                    await i.response.send_message(t(loc, "ev.full"), ephemeral=True)
                    return
            await db.execute(insert(EventRsvp).values(event_id=ev.id, user_id=i.user.id, user_name=str(i.user)[:100],
                                                      status=status, updated_at=utcnow())
                             .on_conflict_do_update(index_elements=[EventRsvp.event_id, EventRsvp.user_id],
                                                    set_={"status": status, "updated_at": utcnow()}))
            await db.commit()
        await i.response.send_message(t(loc, f"ev.rsvp_{status}", title=ev.title), ephemeral=True)
        await self.refresh_message(ev)

    # --- Tareas programadas ------------------------------------------------------------------------
    async def _attendees(self, event_id: int, statuses: tuple[str, ...]) -> list[int]:
        async with sessionmaker()() as db:
            return list((await db.scalars(select(EventRsvp.user_id).where(
                EventRsvp.event_id == event_id, EventRsvp.status.in_(statuses)))).all())

    async def job_reminder(self, job: ScheduledJob) -> None:
        async with sessionmaker()() as db:
            ev = await db.get(Event, int(job.payload["event_id"]))
        guild = self.bot.get_guild(ev.guild_id) if ev else None
        if ev is None or guild is None or ev.status != "scheduled":
            return
        loc = self.loc(ev.guild_id)
        link = f"https://discord.com/channels/{ev.guild_id}/{ev.channel_id}/{ev.message_id}" if ev.message_id else ""
        text = t(loc, "ev.reminder", title=ev.title, when=f"<t:{int(ev.starts_at.timestamp())}:R>",
                 server=guild.name, link=link)
        for uid in await self._attendees(ev.id, ("going", "maybe")):
            member = guild.get_member(uid)
            if member:
                try:
                    await member.send(text)
                except discord.HTTPException:
                    pass  # MD cerrados

    async def job_start(self, job: ScheduledJob) -> None:
        ev = await self._set_status(int(job.payload["event_id"]), "started")
        if ev is None:
            return
        await self.refresh_message(ev)
        cfg = self.cfg(ev.guild_id)
        channel = self.bot.get_channel(ev.channel_id)
        if not (cfg and cfg.ping_at_start) or not isinstance(channel, discord.abc.Messageable):
            return
        going = (await self._attendees(ev.id, ("going",)))[:50]
        if not going:
            return
        try:
            await channel.send(t(self.loc(ev.guild_id), "ev.starting", title=ev.title,
                                 mentions=" ".join(f"<@{u}>" for u in going)),
                               allowed_mentions=discord.AllowedMentions(users=[discord.Object(u) for u in going]))
        except discord.HTTPException:
            pass

    # --- Comandos ------------------------------------------------------------------------------------
    group = app_commands.Group(name=key("cmd.event.name"), description=key("cmd.event.description"), guild_only=True)

    def _can_manage(self, i: discord.Interaction) -> bool:
        if not isinstance(i.user, discord.Member):
            return False
        p = i.user.guild_permissions
        cfg = self.cfg(i.guild_id or 0)
        return (p.manage_events or p.manage_guild or p.administrator
                or bool(cfg and {r.id for r in i.user.roles} & set(cfg.manager_role_ids)))

    async def _check(self, i: discord.Interaction, manage: bool) -> bool:
        loc = self.loc(i.guild_id)
        if self.cfg(i.guild_id or 0) is None:
            await i.response.send_message(t(loc, "ev.disabled"), ephemeral=True)
            return False
        if manage and not self._can_manage(i):
            await i.response.send_message(t(loc, "ev.no_perm"), ephemeral=True)
            return False
        return True

    @group.command(name=key("cmd.event_create.name"), description=key("cmd.event_create.description"))
    @app_commands.describe(title=key("arg.title"), when=key("arg.event_when"), description=key("arg.event_description"),
                           slots=key("arg.event_slots"), channel=key("arg.target_channel"), image=key("arg.image_url"),
                           file=key("arg.event_image_file"))
    async def create_cmd(self, i: discord.Interaction, title: app_commands.Range[str, 1, 100], when: str,
                         description: app_commands.Range[str, 1, 1500] | None = None,
                         slots: app_commands.Range[int, 1, 1000] | None = None,
                         channel: discord.TextChannel | None = None, image: str | None = None,
                         file: discord.Attachment | None = None) -> None:
        from nexus_bot.client import RpcFailure

        if not await self._check(i, manage=True):
            return
        assert i.guild
        loc, state = self.loc(i.guild_id), self.bot.cache.get(i.guild.id)
        starts = parse_when(when, state.timezone, utcnow())
        if starts is None:
            await i.response.send_message(t(loc, "ev.bad_when", tz=state.timezone), ephemeral=True)
            return
        if starts <= utcnow() + timedelta(minutes=1):
            await i.response.send_message(t(loc, "ev.past"), ephemeral=True)
            return
        cfg = self.cfg(i.guild.id)
        target = channel or (i.guild.get_channel(cfg.default_channel_id or 0) if cfg else None) or i.channel
        if image and not image.startswith("https://"):
            image = None
        await i.response.defer(ephemeral=True)
        if file is not None:
            # La tarjeta se edita con cada respuesta: la imagen se guarda en «Imágenes» (no caduca).
            if file.size > M.MAX_SIZE:
                await i.followup.send(f"❌ {t(loc, 'embed.file_too_big')}", ephemeral=True)
                return
            try:
                data = await file.read()
                async with sessionmaker()() as db:
                    row = await M.store(db, i.guild.id, file.filename, data, i.user.id)
                    await db.commit()
                image = f"media://{row.id}"
            except (M.MediaError, discord.HTTPException) as exc:
                code = exc.code if isinstance(exc, M.MediaError) else "image_type"
                msg = {"file_too_large": "embed.file_too_big", "media_quota": "error.media_quota"}.get(
                    code, "embed.file_type")
                await i.followup.send(f"❌ {t(loc, msg)}", ephemeral=True)
                return
        try:
            await self.create(i.guild, title=title, description=(description or "").replace("\\n", "\n"),
                              starts_at=starts, channel_id=target.id, max_slots=slots, image_url=image,  # type: ignore[union-attr]
                              creator_id=i.user.id)
        except RpcFailure as exc:
            await i.followup.send(f"❌ {t(loc, 'error.' + exc.code)}", ephemeral=True)
            return
        await i.followup.send(f"✅ {t(loc, 'ev.created', channel=target.mention)}", ephemeral=True)  # type: ignore[union-attr]

    @group.command(name=key("cmd.event_cancel.name"), description=key("cmd.event_cancel.description"))
    @app_commands.describe(event=key("arg.event"))
    async def cancel_cmd(self, i: discord.Interaction, event: str) -> None:
        if not await self._check(i, manage=True):
            return
        loc = self.loc(i.guild_id)
        ok = event.isdigit() and await self.cancel(i.guild_id or 0, int(event))
        await i.response.send_message(f"✅ {t(loc, 'ev.cancelled_ok')}" if ok else f"❌ {t(loc, 'ev.not_found')}",
                                      ephemeral=True)

    @cancel_cmd.autocomplete("event")
    async def _event_autocomplete(self, i: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        async with sessionmaker()() as db:
            rows = (await db.scalars(select(Event).where(Event.guild_id == i.guild_id, Event.status == "scheduled")
                                     .order_by(Event.starts_at).limit(25))).all()
        return [app_commands.Choice(name=f"#{e.id} · {e.title}"[:100], value=str(e.id)) for e in rows
                if current.lower() in e.title.lower()]

    @group.command(name=key("cmd.event_list.name"), description=key("cmd.event_list.description"))
    async def list_cmd(self, i: discord.Interaction) -> None:
        if not await self._check(i, manage=False):
            return
        loc = self.loc(i.guild_id)
        async with sessionmaker()() as db:
            rows = (await db.scalars(select(Event).where(Event.guild_id == i.guild_id, Event.status == "scheduled",
                                                         Event.starts_at > utcnow())
                                     .order_by(Event.starts_at).limit(10))).all()
        lines = [f"**{e.title}** · <t:{int(e.starts_at.timestamp())}:F> · "
                 f"[↪](https://discord.com/channels/{e.guild_id}/{e.channel_id}/{e.message_id})" for e in rows]
        e = discord.Embed(title=t(loc, "ev.list_title"), color=0x7465F7,
                          description="\n".join(lines) or t(loc, "ev.list_empty"))
        await i.response.send_message(embed=e, ephemeral=True)

    # --- Panel ---------------------------------------------------------------------------------------
    async def rpc_create(self, p: dict[str, Any]) -> dict[str, Any]:
        from datetime import datetime

        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(p["guild_id"]))
        if guild is None or self.cfg(guild.id) is None:
            raise RpcFailure("module_disabled")
        ev = await self.create(guild, title=p["title"], description=p.get("description", ""),
                               starts_at=datetime.fromisoformat(p["starts_at"]), channel_id=int(p["channel_id"]),
                               max_slots=p.get("max_slots"), image_url=p.get("image_url"), creator_id=int(p["creator_id"]))
        return {"id": str(ev.id), "message_id": str(ev.message_id)}

    async def rpc_cancel(self, p: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        if not await self.cancel(int(p["guild_id"]), int(p["event_id"])):
            raise RpcFailure("not_found")
        return {"cancelled": True}


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Events(bot))
