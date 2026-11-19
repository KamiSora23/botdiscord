"""Comandos de moderación, herramientas de canal y anti-raid."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select, update

from nexus_core.cases import active_warn_count
from nexus_core.db import sessionmaker
from nexus_core.db.models import MemberNote, ModerationCase
from nexus_core.db.repo import add_audit, utcnow
from nexus_core.i18n import t

from nexus_bot.modservice import ACTION_COLORS, ModError, ModService, human_duration, parse_duration
from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

def _desc(k: str) -> app_commands.locale_str:
    return key(f"cmd.{k}.description")


class ConfirmView(discord.ui.View):
    """Botones «Confirmar / Cancelar» para acciones que no se pueden deshacer. Solo los usa quien lanzó el comando."""

    def __init__(self, author_id: int, loc: str, label: str,
                 on_confirm: Callable[[discord.Interaction], Awaitable[None]]) -> None:
        super().__init__(timeout=60)
        self.author_id, self.loc, self.on_confirm = author_id, loc, on_confirm
        self.confirm.label = label
        self.cancel.label = t(loc, "nuke.cancel")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:  # type: ignore[override]
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(t(self.loc, "nuke.only_author"), ephemeral=True)
            return False
        return True

    @discord.ui.button(style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        await self.on_confirm(interaction)

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content=t(self.loc, "nuke.cancelled"), view=None)


class Moderation(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self.svc = ModService(bot)
        bot.rpc_handlers["mod.action"] = self.rpc_action

    async def rpc_action(self, params: dict) -> dict:
        """Acción desde el panel (Miembros): mismas reglas que los comandos."""
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        if guild is None:
            raise RpcFailure("not_found")
        if self.bot.cache.get(guild.id).module("moderation") is None:
            raise RpcFailure("module_disabled")
        moderator = guild.get_member(int(params["moderator_id"]))
        if moderator is None:
            try:
                moderator = await guild.fetch_member(int(params["moderator_id"]))
            except discord.NotFound as exc:
                raise RpcFailure("moderator_not_member") from exc
        uid = int(params["user_id"])
        target: discord.Member | discord.User | None = guild.get_member(uid)
        if target is None:
            try:
                target = await self.bot.fetch_user(uid)
            except discord.NotFound as exc:
                raise RpcFailure("not_found") from exc
        case = await self.svc.apply(guild, target, params["action"], moderator=moderator, reason=params.get("reason"),
                                    duration=params.get("duration"), source="dashboard")
        return {"case": case.case_number}

    def loc(self, i: discord.Interaction) -> str:
        return self.bot.cache.get(i.guild_id or 0).locale

    async def interaction_check(self, i: discord.Interaction) -> bool:  # type: ignore[override]
        if i.guild_id and self.bot.cache.get(i.guild_id).module("moderation") is None:
            await i.response.send_message(f"⚠️ {t(self.loc(i), 'mod.module_disabled')}", ephemeral=True)
            return False
        return True

    async def _run(self, i: discord.Interaction, target: discord.Member | discord.User, action: str,
                   reason: str | None, duration: int | None = None, **kw: object) -> None:
        assert i.guild and isinstance(i.user, discord.Member)
        loc = self.loc(i)
        await i.response.defer(ephemeral=True)
        try:
            case = await self.svc.apply(i.guild, target, action, moderator=i.user, reason=reason, duration=duration,
                                        **kw)  # type: ignore[arg-type]
        except ModError as exc:
            await i.followup.send(f"❌ {t(loc, exc.key, **exc.params)}", ephemeral=True)
            return
        msg = t(loc, "mod.done", action=t(loc, f"mod.action_{action}"), user=str(target), number=case.case_number)
        if duration:
            msg += f" · {human_duration(duration, loc)}"
        await i.followup.send(f"✅ {msg}", ephemeral=True)

    @app_commands.command(name=key("cmd.warn.name"), description=_desc("warn"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(user=key("arg.user"), reason=key("arg.reason"))
    async def warn(self, i: discord.Interaction, user: discord.Member, reason: str | None = None) -> None:
        await self._run(i, user, "warn", reason)

    @app_commands.command(name=key("cmd.timeout.name"), description=_desc("timeout"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(user=key("arg.user"), duration=key("arg.duration"), reason=key("arg.reason"))
    async def timeout(self, i: discord.Interaction, user: discord.Member, duration: str,
                      reason: str | None = None) -> None:
        seconds = parse_duration(duration)
        if not seconds or seconds > 2419200:
            await i.response.send_message(f"❌ {t(self.loc(i), 'mod.err_duration')}", ephemeral=True)
            return
        await self._run(i, user, "timeout", reason, seconds)

    @app_commands.command(name=key("cmd.untimeout.name"), description=_desc("untimeout"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(user=key("arg.user"), reason=key("arg.reason"))
    async def untimeout(self, i: discord.Interaction, user: discord.Member, reason: str | None = None) -> None:
        await self._run(i, user, "untimeout", reason)

    @app_commands.command(name=key("cmd.kick.name"), description=_desc("kick"))
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(user=key("arg.user"), reason=key("arg.reason"))
    async def kick(self, i: discord.Interaction, user: discord.Member, reason: str | None = None) -> None:
        await self._run(i, user, "kick", reason)

    @app_commands.command(name=key("cmd.ban.name"), description=_desc("ban"))
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(user=key("arg.user"), reason=key("arg.reason"), duration=key("arg.ban_duration"),
                           delete_days=key("arg.delete_days"))
    async def ban(self, i: discord.Interaction, user: discord.User, reason: str | None = None,
                  duration: str | None = None, delete_days: app_commands.Range[int, 0, 7] | None = None) -> None:
        seconds = parse_duration(duration) if duration else None
        if duration and not seconds:
            await i.response.send_message(f"❌ {t(self.loc(i), 'mod.err_duration')}", ephemeral=True)
            return
        await self._run(i, user, "ban", reason, seconds, delete_message_days=delete_days)

    @app_commands.command(name=key("cmd.unban.name"), description=_desc("unban"))
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(user_id=key("arg.user_id"), reason=key("arg.reason"))
    async def unban(self, i: discord.Interaction, user_id: str, reason: str | None = None) -> None:
        if not user_id.isdigit():
            await i.response.send_message(f"❌ {t(self.loc(i), 'mod.err_not_found')}", ephemeral=True)
            return
        try:
            user = await self.bot.fetch_user(int(user_id))
        except discord.NotFound:
            await i.response.send_message(f"❌ {t(self.loc(i), 'mod.err_not_found')}", ephemeral=True)
            return
        await self._run(i, user, "unban", reason)

    @app_commands.command(name=key("cmd.warnings.name"), description=_desc("warnings"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(user=key("arg.user"))
    async def warnings(self, i: discord.Interaction, user: discord.User) -> None:
        assert i.guild
        await i.response.send_message(embed=await self.history_embed(i.guild.id, user, self.loc(i)), ephemeral=True)

    async def history_embed(self, guild_id: int, user: discord.User | discord.Member, loc: str) -> discord.Embed:
        """Historial de sanciones (lo usan /historial y el menú contextual)."""
        async with sessionmaker()() as db:
            count = await active_warn_count(db, guild_id, user.id)
            cases = (await db.scalars(select(ModerationCase).where(
                ModerationCase.guild_id == guild_id, ModerationCase.target_id == user.id)
                .order_by(ModerationCase.case_number.desc()).limit(10))).all()
        embed = discord.Embed(title=t(loc, "mod.history_title", user=str(user)), color=0x7465F7,
                              description=t(loc, "mod.active_warns", count=count))
        for c in cases:
            embed.add_field(
                name=f"#{c.case_number} · {t(loc, f'mod.action_{c.action}')}{'' if c.active else ' ~~'}",
                value=f"{(c.reason or t(loc, 'mod.no_reason'))[:200]}\n<t:{int(c.created_at.timestamp())}:R>",
                inline=False)
        return embed

    @app_commands.command(name=key("cmd.case.name"), description=_desc("case"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(number=key("arg.case_number"))
    async def case(self, i: discord.Interaction, number: int) -> None:
        assert i.guild
        loc = self.loc(i)
        async with sessionmaker()() as db:
            c = await db.scalar(select(ModerationCase).where(ModerationCase.guild_id == i.guild.id,
                                                             ModerationCase.case_number == number))
        if c is None:
            await i.response.send_message(f"❌ {t(loc, 'mod.err_case_not_found')}", ephemeral=True)
            return
        embed = discord.Embed(title=t(loc, "mod.case_title", number=c.case_number, action=t(loc, f"mod.action_{c.action}")),
                              color=ACTION_COLORS.get(c.action, 0x6B7280), timestamp=c.created_at)
        embed.add_field(name=t(loc, "mod.user"), value=f"<@{c.target_id}> ({c.target_name})")
        embed.add_field(name=t(loc, "mod.moderator"), value=c.moderator_name or "NEXUS")
        embed.add_field(name=t(loc, "mod.reason"), value=c.reason or t(loc, "mod.no_reason"), inline=False)
        await i.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name=key("cmd.purge.name"), description=_desc("purge"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(amount=key("arg.amount"), user=key("arg.purge_user"), only=key("arg.purge_filter"))
    @app_commands.choices(only=[app_commands.Choice(name=key("purge.bots"), value="bots"),
                                app_commands.Choice(name=key("purge.links"), value="links"),
                                app_commands.Choice(name=key("purge.files"), value="files")])
    async def purge(self, i: discord.Interaction, amount: app_commands.Range[int, 1, 100],
                    user: discord.User | None = None, only: app_commands.Choice[str] | None = None) -> None:
        loc = self.loc(i)
        if not isinstance(i.channel, discord.TextChannel):
            await i.response.send_message(f"❌ {t(loc, 'mod.err_channel')}", ephemeral=True)
            return
        kind = only.value if only else None

        def check(m: discord.Message) -> bool:
            if user and m.author.id != user.id:
                return False
            if kind == "bots":
                return m.author.bot
            if kind == "links":
                return "http://" in m.content or "https://" in m.content
            if kind == "files":
                return bool(m.attachments)
            return True

        await i.response.defer(ephemeral=True)
        try:
            deleted = await i.channel.purge(limit=amount, check=check, reason=f"{i.user}: purge")
        except discord.Forbidden:
            await i.followup.send(f"❌ {t(loc, 'mod.err_bot_permission')}", ephemeral=True)
            return
        await i.followup.send(f"🧹 {t(loc, 'mod.purged', count=len(deleted))}", ephemeral=True)

    @app_commands.command(name=key("cmd.softban.name"), description=_desc("softban"))
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(user=key("arg.user"), reason=key("arg.reason"))
    async def softban(self, i: discord.Interaction, user: discord.Member, reason: str | None = None) -> None:
        await self._run(i, user, "softban", reason)

    @app_commands.command(name=key("cmd.pardon.name"), description=_desc("pardon"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(number=key("arg.case_number"))
    async def pardon(self, i: discord.Interaction, number: int) -> None:
        loc = self.loc(i)
        async with sessionmaker()() as db:
            case = await db.scalar(select(ModerationCase).where(
                ModerationCase.guild_id == i.guild_id, ModerationCase.case_number == number))
            if case is None or case.action != "warn" or not case.active:
                await i.response.send_message(f"❌ {t(loc, 'pardon.not_warn', number=number)}", ephemeral=True)
                return
            case.active = False
            await add_audit(db, guild_id=i.guild_id, action="moderation.pardon", source="bot", actor_id=i.user.id,
                            module="moderation", changes={"case": {"old": number, "new": None}})
            await db.commit()
        await i.response.send_message(f"✅ {t(loc, 'pardon.done', number=number)}", ephemeral=True)

    @app_commands.command(name=key("cmd.clearwarns.name"), description=_desc("clearwarns"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(user=key("arg.user"))
    async def clearwarns(self, i: discord.Interaction, user: discord.User) -> None:
        loc = self.loc(i)
        async with sessionmaker()() as db:
            res = await db.execute(update(ModerationCase).where(
                ModerationCase.guild_id == i.guild_id, ModerationCase.target_id == user.id,
                ModerationCase.action == "warn", ModerationCase.active.is_(True)).values(active=False))
            count = res.rowcount or 0
            if count:
                await add_audit(db, guild_id=i.guild_id, action="moderation.clearwarns", source="bot",
                                actor_id=i.user.id, module="moderation",
                                changes={"user": {"old": str(user.id), "new": count}})
            await db.commit()
        await i.response.send_message(f"✅ {t(loc, 'clearwarns.done', count=count, user=str(user))}", ephemeral=True)

    @app_commands.command(name=key("cmd.slowmode.name"), description=_desc("slowmode"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(seconds=key("arg.seconds"))
    async def slowmode(self, i: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]) -> None:
        loc = self.loc(i)
        if not isinstance(i.channel, discord.TextChannel):
            await i.response.send_message(f"❌ {t(loc, 'mod.err_channel')}", ephemeral=True)
            return
        try:
            await i.channel.edit(slowmode_delay=seconds, reason=f"{i.user}: slowmode")
        except discord.Forbidden:
            await i.response.send_message(f"❌ {t(loc, 'mod.err_bot_permission')}", ephemeral=True)
            return
        k = "mod.slowmode_on" if seconds else "mod.slowmode_off"
        await i.response.send_message(f"🐢 {t(loc, k, seconds=seconds, channel=i.channel.mention)}", ephemeral=True)

    @staticmethod
    async def lock_channel(channel: discord.TextChannel, locked: bool, reason: str) -> None:
        everyone = channel.guild.default_role
        ow = channel.overwrites_for(everyone)
        # Al desbloquear se vuelve a "heredar" (None), no a permitir explícitamente.
        ow.send_messages = False if locked else None
        ow.send_messages_in_threads = False if locked else None
        await channel.set_permissions(everyone, overwrite=None if ow.is_empty() else ow, reason=reason)

    async def _set_lock(self, i: discord.Interaction, locked: bool, channel: discord.TextChannel | None,
                        reason: str | None) -> None:
        loc = self.loc(i)
        target = channel or i.channel
        if not isinstance(target, discord.TextChannel) or i.guild is None:
            await i.response.send_message(f"❌ {t(loc, 'mod.err_channel')}", ephemeral=True)
            return
        try:
            await self.lock_channel(target, locked, f"{i.user}: {'lock' if locked else 'unlock'}"
                                    + (f" · {reason}" if reason else ""))
        except discord.Forbidden:
            await i.response.send_message(f"❌ {t(loc, 'mod.err_bot_permission')}", ephemeral=True)
            return
        await i.response.send_message(
            t(loc, "mod.locked" if locked else "mod.unlocked", channel=target.mention), ephemeral=True)
        notice = t(loc, "mod.lock_notice" if locked else "mod.unlock_notice")
        try:
            await target.send(notice + (f"\n{t(loc, 'mod.reason_line', reason=reason)}" if reason else ""),
                              allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @app_commands.command(name=key("cmd.lock.name"), description=_desc("lock"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(channel=key("arg.lock_channel"), reason=key("arg.reason"))
    async def lock(self, i: discord.Interaction, channel: discord.TextChannel | None = None,
                   reason: str | None = None) -> None:
        await self._set_lock(i, True, channel, reason)

    @app_commands.command(name=key("cmd.unlock.name"), description=_desc("unlock"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(channel=key("arg.lock_channel"), reason=key("arg.reason"))
    async def unlock(self, i: discord.Interaction, channel: discord.TextChannel | None = None,
                     reason: str | None = None) -> None:
        await self._set_lock(i, False, channel, reason)

    # --- Anti-raid y herramientas de emergencia ----------------------------------
    @app_commands.command(name=key("cmd.lockdown.name"), description=_desc("lockdown"))
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(on=key("arg.lockdown_on"), reason=key("arg.reason"))
    async def lockdown(self, i: discord.Interaction, on: bool, reason: str | None = None) -> None:
        assert i.guild
        loc = self.loc(i)
        await i.response.defer(ephemeral=True)
        count = 0
        everyone = i.guild.default_role
        for ch in i.guild.text_channels:
            # Solo los canales donde @everyone puede escribir (al activar) o que bloqueó NEXUS (al quitar).
            ow = ch.overwrites_for(everyone)
            if on and (ow.send_messages is False or not ch.permissions_for(everyone).send_messages):
                continue
            if not on and ow.send_messages is not False:
                continue
            try:
                await self.lock_channel(ch, on, f"{i.user}: lockdown" + (f" · {reason}" if reason else ""))
                count += 1
            except discord.HTTPException:
                continue
        await i.followup.send(t(loc, "lockdown.on" if on else "lockdown.off", count=count), ephemeral=True)

    @app_commands.command(name=key("cmd.nuke.name"), description=_desc("nuke"))
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(channel=key("arg.lock_channel"))
    async def nuke(self, i: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        loc = self.loc(i)
        target = channel or i.channel
        if not isinstance(target, discord.TextChannel):
            await i.response.send_message(f"❌ {t(loc, 'mod.err_channel')}", ephemeral=True)
            return

        async def run(inter: discord.Interaction) -> None:
            try:
                clone = await target.clone(reason=f"{i.user}: nuke")
                await clone.edit(position=target.position)
                await target.delete(reason=f"{i.user}: nuke")
            except discord.Forbidden:
                await inter.response.edit_message(content=f"❌ {t(loc, 'mod.err_bot_permission')}", view=None)
                return
            await inter.response.edit_message(content="✅", view=None)
            await clone.send(t(loc, "nuke.done", user=i.user.mention), allowed_mentions=discord.AllowedMentions.none())

        await i.response.send_message(t(loc, "nuke.confirm", channel=target.mention),
                                      view=ConfirmView(i.user.id, loc, t(loc, "nuke.button"), run), ephemeral=True)

    @app_commands.command(name=key("cmd.massban.name"), description=_desc("massban"))
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(user_ids=key("arg.user_ids"), reason=key("arg.reason"))
    async def massban(self, i: discord.Interaction, user_ids: str, reason: str | None = None) -> None:
        assert i.guild
        loc = self.loc(i)
        ids = list(dict.fromkeys(int(x) for x in re.findall(r"\d{15,21}", user_ids)))[:50]
        ids = [x for x in ids if x not in (i.user.id, i.guild.owner_id, self.bot.user.id)]  # type: ignore[union-attr]
        if not ids:
            await i.response.send_message(f"❌ {t(loc, 'massban.none')}", ephemeral=True)
            return

        async def run(inter: discord.Interaction) -> None:
            await inter.response.edit_message(content="⏳", view=None)
            users = [discord.Object(x) for x in ids]
            try:
                result = await i.guild.bulk_ban(users, reason=f"{i.user}: massban" + (f" · {reason}" if reason else ""))
                ok, fail = len(result.banned), len(result.failed)
            except discord.HTTPException:
                ok, fail = 0, len(ids)
            await inter.edit_original_response(content=t(loc, "massban.done", ok=ok, fail=fail))

        await i.response.send_message(t(loc, "massban.confirm", count=len(ids)),
                                      view=ConfirmView(i.user.id, loc, t(loc, "massban.button"), run), ephemeral=True)

    @app_commands.command(name=key("cmd.modstats.name"), description=_desc("modstats"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(moderator=key("arg.moderator"))
    async def modstats(self, i: discord.Interaction, moderator: discord.Member | None = None) -> None:
        loc = self.loc(i)
        who = moderator or i.user
        since = utcnow() - timedelta(days=30)
        async with sessionmaker()() as db:
            rows = (await db.execute(
                select(ModerationCase.action, func.count(), func.count().filter(ModerationCase.created_at >= since))
                .where(ModerationCase.guild_id == i.guild_id, ModerationCase.moderator_id == who.id)
                .group_by(ModerationCase.action))).all()
        e = discord.Embed(title=t(loc, "modstats.title", user=who.display_name),
                          color=self.bot.cache.get(i.guild_id or 0).embed_color)
        e.set_thumbnail(url=who.display_avatar.url)
        total = sum(r[1] for r in rows)
        last30 = sum(r[2] for r in rows)
        lines = [f"**{t(loc, f'mod.action_{a}')}**: {n} ({n30})" for a, n, n30 in sorted(rows, key=lambda r: -r[1])]
        e.description = "\n".join(lines) or "—"
        e.add_field(name=t(loc, "modstats.total"), value=str(total))
        e.add_field(name=t(loc, "modstats.last30"), value=str(last30))
        await i.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name=key("cmd.note.name"), description=_desc("note"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(user=key("arg.user"), note=key("arg.note"))
    async def note(self, i: discord.Interaction, user: discord.User,
                   note: app_commands.Range[str, 1, 1000]) -> None:
        assert i.guild_id
        async with sessionmaker()() as db:
            db.add(MemberNote(guild_id=i.guild_id, user_id=user.id, author_id=i.user.id,
                              author_name=str(i.user), note=note))
            await db.commit()
        await i.response.send_message(f"📝 {t(self.loc(i), 'mod.note_added', user=str(user))}", ephemeral=True)


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Moderation(bot))
