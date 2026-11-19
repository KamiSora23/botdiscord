"""Comandos de utilidad: embeds, mensajes del staff, roles, apodos, recordatorios, información y diversión."""

from __future__ import annotations

import io
import logging
import random
import re
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from pydantic import ValidationError
from sqlalchemy import func, select

from nexus_core import media as M
from nexus_core.config import get_settings
from nexus_core.db import sessionmaker
from nexus_core.db.models import ScheduledJob
from nexus_core.db.repo import utcnow
from nexus_core.discord.permissions import invite_url
from nexus_core.i18n import t
from nexus_core.messages.template import Embed

from nexus_bot.modservice import parse_duration
from nexus_bot import groups
from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.utility")

MAX_REMINDERS = 10
MESSAGE_LINK = re.compile(r"https://(?:\w+\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")
HEX_COLOR = re.compile(r"^#?([0-9a-fA-F]{6})$")
KEY_PERMS = ("administrator", "manage_guild", "manage_roles", "manage_channels", "ban_members", "kick_members",
             "moderate_members", "manage_messages", "mention_everyone")


def _no_mentions() -> discord.AllowedMentions:
    return discord.AllowedMentions.none()


def build_embed(loc: str, default_color: int, *, title: str | None, description: str | None, color: str | None,
                image: str | None, thumbnail: str | None = None, footer: str | None = None,
                ) -> tuple[discord.Embed | None, str | None]:
    """Embed listo para enviar, o (None, clave del error)."""
    title, description = (title or "").strip(), (description or "").strip().replace("\\n", "\n")
    if not title and not description:
        return None, "embed.empty"
    raw = (color or "").strip()
    m = HEX_COLOR.match(raw) if raw else None
    if raw and not m:
        return None, "embed.bad_color"
    image, thumbnail = (image or "").strip() or None, (thumbnail or "").strip() or None
    try:  # mismas reglas que el editor del panel (longitudes, URL https)
        Embed(title=title or None, description=description or None, image_url=image, thumbnail_url=thumbnail)
    except ValidationError:
        return None, "embed.bad_url"
    embed = discord.Embed(title=title or None, description=description or None,
                          color=int(m.group(1), 16) if m else default_color)
    if image:
        embed.set_image(url=image)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if footer and footer.strip():
        embed.set_footer(text=footer.strip()[:2048])
    return embed, None


async def read_upload(att: discord.Attachment) -> tuple[discord.File | None, str | None]:
    """Imagen adjuntada a un comando, lista para reenviar dentro del embed (o la clave del error)."""
    if att.size > M.MAX_SIZE:
        return None, "embed.file_too_big"
    try:
        data = await att.read()
    except discord.HTTPException:
        return None, "embed.file_type"
    ctype = M.sniff(data)
    if ctype is None:
        return None, "embed.file_type"
    return discord.File(io.BytesIO(data), filename=M.file_name(M.new_id(), ctype)), None


class EmbedModal(discord.ui.Modal):
    """Formulario de 5 campos (el máximo de Discord) para crear o editar un embed."""

    def __init__(self, cog: "Utility", loc: str, *, channel: discord.TextChannel | None = None,
                 message: discord.Message | None = None, initial: dict[str, str | None] | None = None,
                 upload: discord.Attachment | None = None) -> None:
        super().__init__(title=t(loc, "embed.modal_edit" if message else "embed.modal_title"))
        self.cog, self.loc, self.channel, self.message, self.upload = cog, loc, channel, message, upload
        old = message.embeds[0] if message and message.embeds else None
        if old is None and initial:
            old = discord.Embed(title=initial.get("title"), description=initial.get("description"))
            if initial.get("image"):
                old.set_image(url=initial["image"])
            if initial.get("footer"):
                old.set_footer(text=initial["footer"])
        self.thumbnail = (initial or {}).get("thumbnail") or (old.thumbnail.url if old and old.thumbnail else None)
        color = (initial or {}).get("color") or (f"#{old.color.value:06X}" if old and old.color else "")
        self.f_title = discord.ui.TextInput(label=t(loc, "embed.f_title"), max_length=256, required=False,
                                            default=(old.title if old else None))
        self.f_desc = discord.ui.TextInput(label=t(loc, "embed.f_description"), style=discord.TextStyle.paragraph,
                                           max_length=4000, required=False, default=(old.description if old else None))
        self.f_color = discord.ui.TextInput(label=t(loc, "embed.f_color"), max_length=7, required=False,
                                            default=color or None, placeholder="#7465F7")
        self.f_image = discord.ui.TextInput(label=t(loc, "embed.f_image"), required=False, max_length=500,
                                            default=(old.image.url if old and old.image else None))
        self.f_footer = discord.ui.TextInput(label=t(loc, "embed.f_footer"), max_length=2048, required=False,
                                             default=(old.footer.text if old and old.footer else None))
        for item in (self.f_title, self.f_desc, self.f_color, self.f_image, self.f_footer):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        loc = self.loc
        embed, err = build_embed(loc, self.cog.bot.cache.get(interaction.guild_id or 0).embed_color,
                                 title=self.f_title.value, description=self.f_desc.value, color=self.f_color.value,
                                 image=self.f_image.value, thumbnail=self.thumbnail, footer=self.f_footer.value)
        if embed is None:
            await interaction.response.send_message(f"❌ {t(loc, err or 'embed.empty')}", ephemeral=True)
            return
        file = None
        if self.upload:
            file, err = await read_upload(self.upload)
            if file is None:
                await interaction.response.send_message(f"❌ {t(loc, err or 'embed.file_type')}", ephemeral=True)
                return
            embed.set_image(url=f"attachment://{file.filename}")
        try:
            if self.message:
                keep = list(self.message.attachments)
                # Imagen sin tocar que era un adjunto del mensaje: seguir apuntando al adjunto (no a su enlace,
                # que caduca).
                for att in keep:
                    if embed.image and (embed.image.url or "").split("?")[0] == att.url.split("?")[0]:
                        embed.set_image(url=f"attachment://{att.filename}")
                await self.message.edit(embed=embed, attachments=keep + ([file] if file else []))
                await interaction.response.send_message(f"✅ {t(loc, 'embed.edited')}", ephemeral=True)
            else:
                assert self.channel
                await self.channel.send(embed=embed, allowed_mentions=_no_mentions(),
                                        **({"file": file} if file else {}))
                await interaction.response.send_message(
                    f"✅ {t(loc, 'embed.sent', channel=self.channel.mention)}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f"❌ {t(loc, 'util.cannot_send')}", ephemeral=True)


class Utility(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        groups.bind(self, self.roleinfo, self.botinfo, self.eightball, self.coin, self.dice, self.choose)
        self.started = utcnow()
        bot.job_handlers["reminder.send"] = self.job_reminder

    def loc(self, i: discord.Interaction) -> str:
        if i.guild_id:
            return self.bot.cache.get(i.guild_id).locale
        return "es" if str(i.locale).startswith("es") else "en"

    def color(self, i: discord.Interaction) -> int:
        return self.bot.cache.get(i.guild_id).embed_color if i.guild_id else 0x7465F7

    # --- Embeds y mensajes del staff -------------------------------------------
    @app_commands.command(name=key("cmd.embed.name"), description=key("cmd.embed.description"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(channel=key("arg.target_channel"), title=key("arg.embed_title"),
                           description=key("arg.embed_description"), color=key("arg.hex"),
                           image=key("arg.image_url"), thumbnail=key("arg.thumbnail_url"), footer=key("arg.footer"),
                           file=key("arg.image_file"))
    async def embed(self, i: discord.Interaction, channel: discord.TextChannel | None = None,
                    title: app_commands.Range[str, 1, 256] | None = None,
                    description: app_commands.Range[str, 1, 4000] | None = None,
                    color: app_commands.Range[str, 1, 7] | None = None, image: str | None = None,
                    thumbnail: str | None = None, footer: app_commands.Range[str, 1, 2048] | None = None,
                    file: discord.Attachment | None = None) -> None:
        loc = self.loc(i)
        target = channel or i.channel
        if not isinstance(target, discord.TextChannel):
            await i.response.send_message(f"❌ {t(loc, 'mod.err_channel')}", ephemeral=True)
            return
        values = {"title": title, "description": description, "color": color, "image": image,
                  "thumbnail": thumbnail, "footer": footer}
        if not title and not description:
            # Sin texto: se abre el formulario, ya relleno con lo que se haya escrito.
            await i.response.send_modal(EmbedModal(self, loc, channel=target, initial=values, upload=file))
            return
        embed, err = build_embed(loc, self.color(i), **values)
        if embed is None:
            await i.response.send_message(f"❌ {t(loc, err or 'embed.empty')}", ephemeral=True)
            return
        await i.response.defer(ephemeral=True, thinking=True)
        upload = None
        if file:
            upload, err = await read_upload(file)
            if upload is None:
                await i.followup.send(f"❌ {t(loc, err or 'embed.file_type')}", ephemeral=True)
                return
            embed.set_image(url=f"attachment://{upload.filename}")
        try:
            await target.send(embed=embed, allowed_mentions=_no_mentions(), **({"file": upload} if upload else {}))
        except discord.Forbidden:
            await i.followup.send(f"❌ {t(loc, 'util.cannot_send')}", ephemeral=True)
            return
        await i.followup.send(f"✅ {t(loc, 'embed.sent', channel=target.mention)}", ephemeral=True)

    @app_commands.command(name=key("cmd.embed_edit.name"), description=key("cmd.embed_edit.description"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(link=key("arg.message_link"))
    async def embed_edit(self, i: discord.Interaction, link: str) -> None:
        loc = self.loc(i)
        m = MESSAGE_LINK.search(link)
        if not m or int(m.group(1)) != i.guild_id or i.guild is None:
            await i.response.send_message(f"❌ {t(loc, 'embed.bad_link')}", ephemeral=True)
            return
        channel = i.guild.get_channel_or_thread(int(m.group(2)))
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await i.response.send_message(f"❌ {t(loc, 'embed.not_found')}", ephemeral=True)
            return
        try:
            message = await channel.fetch_message(int(m.group(3)))
        except discord.HTTPException:
            await i.response.send_message(f"❌ {t(loc, 'embed.not_found')}", ephemeral=True)
            return
        if message.author.id != self.bot.user.id:  # type: ignore[union-attr]
            await i.response.send_message(f"❌ {t(loc, 'embed.not_mine')}", ephemeral=True)
            return
        await i.response.send_modal(EmbedModal(self, loc, message=message))

    @app_commands.command(name=key("cmd.say.name"), description=key("cmd.say.description"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(text=key("arg.text"), channel=key("arg.target_channel"))
    async def say(self, i: discord.Interaction, text: app_commands.Range[str, 1, 2000],
                  channel: discord.TextChannel | None = None) -> None:
        loc = self.loc(i)
        target = channel or i.channel
        if not isinstance(target, discord.TextChannel):
            await i.response.send_message(f"❌ {t(loc, 'mod.err_channel')}", ephemeral=True)
            return
        try:
            # Sin @everyone ni menciones de roles: evita usar al bot para mencionar a todos.
            await target.send(text, allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True))
        except discord.Forbidden:
            await i.response.send_message(f"❌ {t(loc, 'util.cannot_send')}", ephemeral=True)
            return
        await i.response.send_message(f"✅ {t(loc, 'say.sent', channel=target.mention)}", ephemeral=True)

    # --- Roles y apodos ---------------------------------------------------------
    role = app_commands.Group(name=key("cmd.role.name"), description=key("cmd.role.description"),
                              guild_only=True, default_permissions=discord.Permissions(manage_roles=True))

    def _role_error(self, i: discord.Interaction, role: discord.Role) -> str | None:
        assert i.guild and isinstance(i.user, discord.Member)
        if role.managed or role.is_default():
            return "role.err_managed"
        if role >= i.guild.me.top_role:
            return "role.err_bot"
        if i.user.id != i.guild.owner_id and role >= i.user.top_role:
            return "role.err_you"
        return None

    @role.command(name=key("cmd.role_add.name"), description=key("cmd.role_add.description"))
    @app_commands.describe(user=key("arg.user"), role=key("arg.role"))
    async def role_add(self, i: discord.Interaction, user: discord.Member, role: discord.Role) -> None:
        await self._change_role(i, user, role, add=True)

    @role.command(name=key("cmd.role_remove.name"), description=key("cmd.role_remove.description"))
    @app_commands.describe(user=key("arg.user"), role=key("arg.role"))
    async def role_remove(self, i: discord.Interaction, user: discord.Member, role: discord.Role) -> None:
        await self._change_role(i, user, role, add=False)

    async def _change_role(self, i: discord.Interaction, user: discord.Member, role: discord.Role, *, add: bool) -> None:
        loc = self.loc(i)
        if err := self._role_error(i, role):
            await i.response.send_message(f"❌ {t(loc, err)}", ephemeral=True)
            return
        if add == (role in user.roles):
            await i.response.send_message(t(loc, "role.already" if add else "role.missing", user=user.mention),
                                          ephemeral=True)
            return
        try:
            if add:
                await user.add_roles(role, reason=f"{i.user}: /rol")
            else:
                await user.remove_roles(role, reason=f"{i.user}: /rol")
        except discord.Forbidden:
            await i.response.send_message(f"❌ {t(loc, 'mod.err_bot_permission')}", ephemeral=True)
            return
        await i.response.send_message(
            f"✅ {t(loc, 'role.added' if add else 'role.removed', role=role.mention, user=user.mention)}", ephemeral=True)

    @app_commands.command(name=key("cmd.nick.name"), description=key("cmd.nick.description"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.describe(user=key("arg.user"), nickname=key("arg.nickname"))
    async def nick(self, i: discord.Interaction, user: discord.Member,
                   nickname: app_commands.Range[str, 1, 32] | None = None) -> None:
        loc = self.loc(i)
        assert i.guild and isinstance(i.user, discord.Member)
        if user.id == i.guild.owner_id or user.top_role >= i.guild.me.top_role:
            await i.response.send_message(f"❌ {t(loc, 'mod.err_hierarchy_bot')}", ephemeral=True)
            return
        if i.user.id != i.guild.owner_id and user.id != i.user.id and user.top_role >= i.user.top_role:
            await i.response.send_message(f"❌ {t(loc, 'mod.err_hierarchy_you')}", ephemeral=True)
            return
        try:
            await user.edit(nick=nickname, reason=f"{i.user}: /apodo")
        except discord.Forbidden:
            await i.response.send_message(f"❌ {t(loc, 'mod.err_bot_permission')}", ephemeral=True)
            return
        await i.response.send_message(f"✅ {t(loc, 'nick.changed' if nickname else 'nick.reset', user=user.mention)}",
                                      ephemeral=True)

    # --- Recordatorios ----------------------------------------------------------
    @app_commands.command(name=key("cmd.remind.name"), description=key("cmd.remind.description"))
    @app_commands.guild_only()
    @app_commands.describe(when=key("arg.when"), text=key("arg.reminder"), private=key("arg.remind_private"))
    async def remind(self, i: discord.Interaction, when: str, text: app_commands.Range[str, 1, 500],
                     private: bool = False) -> None:
        loc = self.loc(i)
        seconds = parse_duration(when)
        if not seconds or seconds < 60 or seconds > 365 * 86400:
            await i.response.send_message(f"❌ {t(loc, 'remind.bad_time')}", ephemeral=True)
            return
        run_at = utcnow() + timedelta(seconds=seconds)
        async with sessionmaker()() as db:
            pending = await db.scalar(select(func.count()).select_from(ScheduledJob).where(
                ScheduledJob.job_type == "reminder.send", ScheduledJob.status == "pending",
                ScheduledJob.payload["user_id"].astext == str(i.user.id)))
            if (pending or 0) >= MAX_REMINDERS:
                await i.response.send_message(f"❌ {t(loc, 'remind.limit', max=MAX_REMINDERS)}", ephemeral=True)
                return
            db.add(ScheduledJob(guild_id=i.guild_id, job_type="reminder.send", run_at=run_at, payload={
                "user_id": str(i.user.id), "channel_id": str(i.channel_id), "text": text, "private": private}))
            await db.commit()
        await i.response.send_message(f"⏰ {t(loc, 'remind.set', when=discord.utils.format_dt(run_at, 'R'))}",
                                      ephemeral=True)

    async def job_reminder(self, job: ScheduledJob) -> None:
        p = job.payload
        loc = self.bot.cache.get(job.guild_id or 0).locale
        text = t(loc, "remind.message", user=f"<@{p['user_id']}>", text=p["text"])
        mentions = discord.AllowedMentions(users=[discord.Object(int(p["user_id"]))], everyone=False, roles=False)
        channel = None if p.get("private") else self.bot.get_channel(int(p["channel_id"]))
        try:
            if isinstance(channel, discord.abc.Messageable):
                await channel.send(text, allowed_mentions=mentions)
                return
        except discord.HTTPException:
            pass
        user = await self.bot.fetch_user(int(p["user_id"]))  # canal borrado o sin permiso: por mensaje privado
        try:
            await user.send(text)
        except discord.HTTPException:
            log.info("No se pudo entregar el recordatorio %s", job.id)

    # --- Información -------------------------------------------------------------
    @groups.info.command(name=key("sub.info.role"), description=key("cmd.roleinfo.description"))
    @app_commands.describe(role=key("arg.role"))
    async def roleinfo(self, i: discord.Interaction, role: discord.Role) -> None:
        loc = self.loc(i)
        yes, no = t(loc, "info.yes"), t(loc, "info.no")
        e = discord.Embed(title=role.name, color=role.color.value or self.color(i))
        e.add_field(name=t(loc, "info.members"), value=str(len(role.members)))
        e.add_field(name=t(loc, "info.color"), value=f"#{role.color.value:06X}")
        e.add_field(name=t(loc, "info.position"), value=str(role.position))
        e.add_field(name=t(loc, "info.mentionable"), value=yes if role.mentionable else no)
        e.add_field(name=t(loc, "info.hoisted"), value=yes if role.hoist else no)
        e.add_field(name=t(loc, "info.created"), value=discord.utils.format_dt(role.created_at, "D"))
        perms = [p for p in KEY_PERMS if getattr(role.permissions, p)]
        if perms:
            e.add_field(name=t(loc, "info.perms"), value=", ".join(f"`{p}`" for p in perms), inline=False)
        e.set_footer(text=f"{t(loc, 'info.id')}: {role.id}")
        await i.response.send_message(embed=e, ephemeral=True)

    @groups.info.command(name=key("sub.info.bot"), description=key("cmd.botinfo.description"))
    async def botinfo(self, i: discord.Interaction) -> None:
        loc = self.loc(i)
        me = self.bot.user
        assert me
        e = discord.Embed(title=me.name, color=self.color(i))
        e.set_thumbnail(url=me.display_avatar.url)
        e.add_field(name=t(loc, "info.servers"), value=str(len(self.bot.guilds)))
        e.add_field(name=t(loc, "info.latency"), value=f"{round(self.bot.latency * 1000)} ms")
        e.add_field(name=t(loc, "info.uptime"), value=discord.utils.format_dt(self.started, "R"))
        e.add_field(name=t(loc, "info.version"), value=f"discord.py {discord.__version__}")
        await i.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name=key("cmd.invite.name"), description=key("cmd.invite.description"))
    async def invite(self, i: discord.Interaction) -> None:
        url = invite_url(get_settings().discord_client_id)
        await i.response.send_message(t(self.loc(i), "invite.reply", url=url), ephemeral=True)

    # --- Diversión ----------------------------------------------------------------
    @groups.fun.command(name=key("sub.fun.8ball"), description=key("cmd.eightball.description"))
    @app_commands.describe(question=key("arg.question"))
    async def eightball(self, i: discord.Interaction, question: app_commands.Range[str, 1, 200]) -> None:
        loc = self.loc(i)
        answer = random.choice(t(loc, "fun.8ball_answers").split("|"))
        await i.response.send_message(t(loc, "fun.8ball", question=question, answer=answer),
                                      allowed_mentions=_no_mentions())

    @groups.fun.command(name=key("sub.fun.coin"), description=key("cmd.coin.description"))
    async def coin(self, i: discord.Interaction) -> None:
        loc = self.loc(i)
        await i.response.send_message(t(loc, "fun.coin", side=t(loc, random.choice(("fun.heads", "fun.tails")))))

    @groups.fun.command(name=key("sub.fun.dice"), description=key("cmd.dice.description"))
    @app_commands.describe(sides=key("arg.sides"))
    async def dice(self, i: discord.Interaction, sides: app_commands.Range[int, 2, 1000] = 6) -> None:
        await i.response.send_message(t(self.loc(i), "fun.dice", n=random.randint(1, sides), sides=sides))

    @groups.fun.command(name=key("sub.fun.choose"), description=key("cmd.choose.description"))
    @app_commands.describe(options=key("arg.options"))
    async def choose(self, i: discord.Interaction, options: app_commands.Range[str, 1, 500]) -> None:
        loc = self.loc(i)
        items = [o.strip() for o in options.split(",") if o.strip()]
        if len(items) < 2:
            await i.response.send_message(t(loc, "fun.choose_few"), ephemeral=True)
            return
        await i.response.send_message(t(loc, "fun.choose", choice=random.choice(items)),
                                      allowed_mentions=_no_mentions())


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Utility(bot))
