"""AFK, snipe, banner, anuncios, color, reportes y menús contextuales (clic derecho)."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands

from nexus_core.i18n import t

from nexus_bot import groups
from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.extras")

SNIPE_TTL = 600  # 10 minutos: solo en memoria, nunca en la base de datos
HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _afk_key(guild_id: int) -> str:
    return f"nexus:afk:{guild_id}"


class Extras(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        groups.bind(self, self.banner, self.color_cmd)
        self.deleted: dict[int, dict[str, Any]] = {}
        self.edited: dict[int, dict[str, Any]] = {}
        self._afk_notice: dict[int, float] = {}  # canal → último aviso (evita spam)
        self.menus = [
            app_commands.ContextMenu(name=key("ctx.report_message"), callback=self.ctx_report),
            app_commands.ContextMenu(name=key("ctx.save_dm"), callback=self.ctx_save),
            app_commands.ContextMenu(name=key("ctx.avatar"), callback=self.ctx_avatar),
            app_commands.ContextMenu(name=key("ctx.warnings"), callback=self.ctx_warnings),
            app_commands.ContextMenu(name=key("ctx.quick_timeout"), callback=self.ctx_timeout),
        ]
        self.menus[3].default_permissions = discord.Permissions(moderate_members=True)
        self.menus[4].default_permissions = discord.Permissions(moderate_members=True)
        for n, m in enumerate(self.menus):
            if n != 1:  # «Guardar en mis MD» también funciona fuera de servidores
                m.guild_only = True
            bot.tree.add_command(m)

    async def cog_unload(self) -> None:
        for m in self.menus:
            self.bot.tree.remove_command(m.name, type=m.type)

    def loc(self, i: discord.Interaction | None = None, guild_id: int | None = None) -> str:
        gid = guild_id or (i.guild_id if i else None)
        if gid:
            return self.bot.cache.get(gid).locale
        return "es" if i and str(i.locale).startswith("es") else "en"

    def color(self, guild_id: int | None) -> int:
        return self.bot.cache.get(guild_id).embed_color if guild_id else 0x7465F7

    # --- AFK (en Redis, sobrevive a reinicios) -----------------------------------
    @app_commands.command(name=key("cmd.afk.name"), description=key("cmd.afk.description"))
    @app_commands.guild_only()
    @app_commands.describe(reason=key("arg.afk_reason"))
    async def afk(self, i: discord.Interaction, reason: app_commands.Range[str, 1, 100] | None = None) -> None:
        data = json.dumps({"reason": reason, "since": int(time.time())})
        await self.bot.redis.hset(_afk_key(i.guild_id or 0), str(i.user.id), data)
        await i.response.send_message(f"💤 {t(self.loc(i), 'afk.set', reason=f': {reason}' if reason else '')}",
                                      ephemeral=True)

    @commands.Cog.listener("on_message")
    async def afk_listener(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        k = _afk_key(message.guild.id)
        try:
            if await self.bot.redis.hdel(k, str(message.author.id)):
                await message.channel.send(t(self.loc(guild_id=message.guild.id), "afk.back",
                                             user=message.author.mention), delete_after=8,
                                           allowed_mentions=discord.AllowedMentions.none())
            mentioned = [u for u in message.mentions if not u.bot and u.id != message.author.id][:3]
            if not mentioned:
                return
            values = await self.bot.redis.hmget(k, [str(u.id) for u in mentioned])
        except Exception:  # Redis caído: el AFK no es crítico
            return
        now = time.monotonic()
        if now - self._afk_notice.get(message.channel.id, 0) < 10:
            return
        loc = self.loc(guild_id=message.guild.id)
        lines = []
        for user, raw in zip(mentioned, values):
            if raw:
                d = json.loads(raw)
                lines.append(t(loc, "afk.notice", user=user.display_name,
                               reason=f": {d['reason']}" if d.get("reason") else "", since=f"<t:{d['since']}:R>"))
        if lines:
            self._afk_notice[message.channel.id] = now
            await message.reply("\n".join(lines), delete_after=15, mention_author=False,
                                allowed_mentions=discord.AllowedMentions.none())

    # --- Snipe (solo staff, solo en memoria) ----------------------------------------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not (message.content or message.attachments):
            return
        self.deleted[message.channel.id] = {
            "author": message.author, "content": message.content, "at": time.time(),
            "files": [a.filename for a in message.attachments][:5]}

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild is None or before.author.bot or before.content == after.content:
            return
        self.edited[before.channel.id] = {"author": before.author, "before": before.content, "after": after.content,
                                          "at": time.time(), "url": after.jump_url}

    def _fresh(self, store: dict[int, dict[str, Any]], channel_id: int) -> dict[str, Any] | None:
        d = store.get(channel_id)
        if d and time.time() - d["at"] < SNIPE_TTL:
            return d
        store.pop(channel_id, None)
        return None

    @app_commands.command(name=key("cmd.snipe.name"), description=key("cmd.snipe.description"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def snipe(self, i: discord.Interaction) -> None:
        loc = self.loc(i)
        d = self._fresh(self.deleted, i.channel_id or 0)
        if not d:
            await i.response.send_message(t(loc, "snipe.none"), ephemeral=True)
            return
        e = discord.Embed(description=d["content"][:4000] or None, color=self.color(i.guild_id),
                          timestamp=datetime.fromtimestamp(d["at"], UTC))
        e.set_author(name=str(d["author"]), icon_url=d["author"].display_avatar.url)
        if d["files"]:
            e.add_field(name=t(loc, "snipe.files"), value="\n".join(d["files"]))
        await i.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name=key("cmd.editsnipe.name"), description=key("cmd.editsnipe.description"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def editsnipe(self, i: discord.Interaction) -> None:
        loc = self.loc(i)
        d = self._fresh(self.edited, i.channel_id or 0)
        if not d:
            await i.response.send_message(t(loc, "snipe.none"), ephemeral=True)
            return
        e = discord.Embed(color=self.color(i.guild_id), url=d["url"], title="↪",
                          timestamp=datetime.fromtimestamp(d["at"], UTC))
        e.set_author(name=str(d["author"]), icon_url=d["author"].display_avatar.url)
        e.add_field(name=t(loc, "snipe.before"), value=(d["before"] or "—")[:1024], inline=False)
        e.add_field(name=t(loc, "snipe.after"), value=(d["after"] or "—")[:1024], inline=False)
        await i.response.send_message(embed=e, ephemeral=True)

    # --- Información y anuncios ------------------------------------------------------
    @groups.info.command(name=key("sub.info.banner"), description=key("cmd.banner.description"))
    @app_commands.describe(user=key("arg.target_user"))
    async def banner(self, i: discord.Interaction, user: discord.User | None = None) -> None:
        target = await self.bot.fetch_user((user or i.user).id)  # el banner solo llega con fetch_user
        if not target.banner:
            await i.response.send_message(t(self.loc(i), "banner.none", user=target.display_name), ephemeral=True)
            return
        e = discord.Embed(title=str(target), color=self.color(i.guild_id))
        e.set_image(url=target.banner.with_size(1024).url)
        await i.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name=key("cmd.announce.name"), description=key("cmd.announce.description"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(title=key("arg.title"), text=key("arg.announce_text"), channel=key("arg.target_channel"),
                           mention=key("arg.announce_mention"), color=key("arg.hex"), image=key("arg.image_url"),
                           file=key("arg.image_file"))
    async def announce(self, i: discord.Interaction, title: app_commands.Range[str, 1, 256],
                       text: app_commands.Range[str, 1, 4000], channel: discord.TextChannel | None = None,
                       mention: discord.Role | None = None, color: app_commands.Range[str, 1, 7] | None = None,
                       image: str | None = None, file: discord.Attachment | None = None) -> None:
        from nexus_bot.cogs.utility import build_embed, read_upload

        loc = self.loc(i)
        target = channel or i.channel
        if not isinstance(target, discord.TextChannel) or not isinstance(i.user, discord.Member):
            await i.response.send_message(f"❌ {t(loc, 'mod.err_channel')}", ephemeral=True)
            return
        e, err = build_embed(loc, self.color(i.guild_id), title=f"📢 {title}", description=text, color=color,
                             image=image)
        if e is None:
            await i.response.send_message(f"❌ {t(loc, err or 'embed.empty')}", ephemeral=True)
            return
        e.timestamp = discord.utils.utcnow()
        if i.guild and i.guild.icon:
            e.set_footer(text=i.guild.name, icon_url=i.guild.icon.url)
        # Mencionar un rol (o @everyone) solo si quien lo usa podría hacerlo él mismo en Discord.
        content, allowed = None, discord.AllowedMentions.none()
        if mention is not None:
            if not (mention.mentionable or target.permissions_for(i.user).mention_everyone):
                await i.response.send_message(f"❌ {t(loc, 'announce.no_mention')}", ephemeral=True)
                return
            content = "@everyone" if mention.is_default() else mention.mention
            allowed = discord.AllowedMentions(everyone=mention.is_default(), roles=[] if mention.is_default()
                                              else [mention], users=False)
        await i.response.defer(ephemeral=True, thinking=True)
        upload = None
        if file:
            upload, err = await read_upload(file)
            if upload is None:
                await i.followup.send(f"❌ {t(loc, err or 'embed.file_type')}", ephemeral=True)
                return
            e.set_image(url=f"attachment://{upload.filename}")
        try:
            await target.send(content=content, embed=e, allowed_mentions=allowed,
                              **({"file": upload} if upload else {}))
        except discord.Forbidden:
            await i.followup.send(f"❌ {t(loc, 'util.cannot_send')}", ephemeral=True)
            return
        await i.followup.send(f"✅ {t(loc, 'embed.sent', channel=target.mention)}", ephemeral=True)

    @groups.info.command(name=key("sub.info.color"), description=key("cmd.color.description"))
    @app_commands.describe(hex=key("arg.hex"))
    async def color_cmd(self, i: discord.Interaction, hex: str) -> None:
        m = HEX.match(hex.strip())
        if not m:
            await i.response.send_message(f"❌ {t(self.loc(i), 'embed.bad_color')}", ephemeral=True)
            return
        v = int(m.group(1), 16)
        r, g, b = v >> 16, (v >> 8) & 255, v & 255
        e = discord.Embed(title=f"#{m.group(1).upper()}", color=v,
                          description=f"RGB: `{r}, {g}, {b}`\nDecimal: `{v}`")
        await i.response.send_message(embed=e, ephemeral=True)

    # --- Reportes al staff -------------------------------------------------------------
    def _staff_channel(self, guild: discord.Guild) -> discord.abc.Messageable | None:
        mod = self.bot.get_cog("Moderation")
        if mod is None:
            return None
        svc = mod.svc  # type: ignore[attr-defined]
        from nexus_core.modules.moderation import channel_for

        cfg, lcfg = svc.config(guild.id), svc.logging_config(guild.id)
        cid = (cfg.log_channel_id if cfg else None) or (channel_for(lcfg, "mod_case") if lcfg else None)
        ch = guild.get_channel(cid or 0)
        return ch if isinstance(ch, discord.abc.Messageable) else None

    async def _send_report(self, i: discord.Interaction, target: discord.abc.User, reason: str | None,
                           message: discord.Message | None = None) -> None:
        assert i.guild
        loc = self.loc(i)
        channel = self._staff_channel(i.guild)
        if channel is None:
            await i.response.send_message(f"❌ {t(loc, 'report.no_channel')}", ephemeral=True)
            return
        e = discord.Embed(title=t(loc, "report.title"), color=0xEF4444, timestamp=discord.utils.utcnow())
        e.add_field(name=t(loc, "report.reported"), value=f"{target.mention} (`{target.id}`)")
        e.add_field(name=t(loc, "report.reporter"), value=f"{i.user.mention} (`{i.user.id}`)")
        if message:
            e.add_field(name=t(loc, "report.channel"), value=message.channel.mention)  # type: ignore[union-attr]
            e.add_field(name=t(loc, "report.message"),
                        value=f"{(message.content or '—')[:900]}\n[↪]({message.jump_url})", inline=False)
        if reason:
            e.add_field(name=t(loc, "mod.reason"), value=reason[:1000], inline=False)
        try:
            await channel.send(embed=e, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            await i.response.send_message(f"❌ {t(loc, 'report.no_channel')}", ephemeral=True)
            return
        await i.response.send_message(f"✅ {t(loc, 'report.sent')}", ephemeral=True)

    @app_commands.command(name=key("cmd.report.name"), description=key("cmd.report.description"))
    @app_commands.guild_only()
    @app_commands.describe(user=key("arg.user"), reason=key("arg.reason"))
    async def report(self, i: discord.Interaction, user: discord.Member,
                     reason: app_commands.Range[str, 1, 1000]) -> None:
        await self._send_report(i, user, reason)

    # --- Menús contextuales -----------------------------------------------------------
    async def ctx_report(self, i: discord.Interaction, message: discord.Message) -> None:
        await self._send_report(i, message.author, None, message)

    async def ctx_save(self, i: discord.Interaction, message: discord.Message) -> None:
        loc = self.loc(i)
        e = discord.Embed(title=t(loc, "save.title"), description=(message.content or "—")[:4000],
                          color=self.color(i.guild_id), timestamp=message.created_at, url=message.jump_url)
        e.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        img = next((a.url for a in message.attachments if (a.content_type or "").startswith("image/")), None)
        if img:
            e.set_image(url=img)
        try:
            await i.user.send(embed=e)
        except discord.HTTPException:
            await i.response.send_message(t(loc, "save.closed"), ephemeral=True)
            return
        await i.response.send_message(f"✅ {t(loc, 'save.done')}", ephemeral=True)

    async def ctx_avatar(self, i: discord.Interaction, user: discord.Member) -> None:
        e = discord.Embed(title=str(user), color=self.color(i.guild_id))
        e.set_image(url=user.display_avatar.with_size(1024).url)
        await i.response.send_message(embed=e, ephemeral=True)

    async def ctx_warnings(self, i: discord.Interaction, user: discord.Member) -> None:
        mod = self.bot.get_cog("Moderation")
        assert mod and i.guild
        await i.response.send_message(embed=await mod.history_embed(i.guild.id, user, self.loc(i)),  # type: ignore[attr-defined]
                                      ephemeral=True)

    async def ctx_timeout(self, i: discord.Interaction, user: discord.Member) -> None:
        mod = self.bot.get_cog("Moderation")
        assert mod
        if not await mod.interaction_check(i):  # módulo de moderación activado
            return
        await mod._run(i, user, "timeout", None, duration=600)  # type: ignore[attr-defined]


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Extras(bot))
