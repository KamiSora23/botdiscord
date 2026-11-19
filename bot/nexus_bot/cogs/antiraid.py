"""Anti-raid: verificación (botón o captcha), cuentas nuevas, detección de raids, modo raid y cuarentena."""

from __future__ import annotations

import logging
import random
import re
import time
from collections import deque
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import update

from nexus_core.db import sessionmaker
from nexus_core.db.models import MemberQuarantine, ModuleConfig
from nexus_core.db.repo import add_audit, utcnow
from nexus_core.i18n import t
from nexus_core.messages import render_payload
from nexus_core.modules import parse_config
from nexus_core.modules.antiraid import AntiraidConfig, GateChannel, plan_gate

from nexus_bot.cogs.welcome import context_for, for_edit, with_media
from nexus_bot.translator import key

if TYPE_CHECKING:
    from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot.antiraid")

MAX_FAILS = 5
FAIL_WINDOW = 600  # segundos


def raid_key(guild_id: int) -> str:
    return f"nexus:raid:{guild_id}"


class VerifyButton(discord.ui.DynamicItem[discord.ui.Button], template=r"nexus:vf:start"):
    def __init__(self, label: str = "Verify") -> None:
        super().__init__(discord.ui.Button(label=label, style=discord.ButtonStyle.success, emoji="✅",
                                           custom_id="nexus:vf:start"))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):  # type: ignore[no-untyped-def]
        inst = cls.__new__(cls)
        discord.ui.DynamicItem.__init__(inst, item)
        return inst

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Antiraid = interaction.client.get_cog("Antiraid")  # type: ignore[union-attr,assignment]
        await cog.start_verification(interaction)


class CaptchaModal(discord.ui.Modal):
    def __init__(self, cog: "Antiraid", loc: str) -> None:
        super().__init__(title=t(loc, "vf.modal_title"), timeout=300)
        self.cog, self.loc = cog, loc
        a, b = random.randint(2, 12), random.randint(2, 12)
        self.expected = str(a + b)
        self.answer = discord.ui.TextInput(label=t(loc, "vf.question", a=a, b=b), max_length=4)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.answer.value.strip() == self.expected:
            await self.cog.grant(interaction)
            return
        await self.cog.register_fail(interaction)
        await interaction.response.send_message(t(self.loc, "vf.wrong"), ephemeral=True)


class Antiraid(commands.Cog):
    def __init__(self, bot: NexusBot) -> None:
        self.bot = bot
        self.joins: dict[int, deque[tuple[float, int]]] = {}
        bot.add_dynamic_items(VerifyButton)
        bot.rpc_handlers["antiraid.publish"] = self.rpc_publish
        bot.rpc_handlers["antiraid.quarantine_role"] = self.rpc_quarantine_role
        bot.rpc_handlers["antiraid.gate"] = self.rpc_gate

    def cfg(self, guild_id: int) -> AntiraidConfig | None:
        state = self.bot.cache.get(guild_id)
        mod = state.module("antiraid")
        return parse_config("antiraid", mod.config, state.locale) if mod else None  # type: ignore[return-value]

    def loc(self, guild_id: int | None) -> str:
        return self.bot.cache.get(guild_id or 0).locale

    # --- Verificación ---------------------------------------------------------------
    async def start_verification(self, i: discord.Interaction) -> None:
        loc = self.loc(i.guild_id)
        cfg = self.cfg(i.guild_id or 0)
        if cfg is None or not cfg.verification.enabled or not isinstance(i.user, discord.Member):
            await i.response.send_message(t(loc, "ar.verify_not_configured"), ephemeral=True)
            return
        if any(r.id == cfg.verification.role_id for r in i.user.roles):
            await i.response.send_message(t(loc, "vf.already"), ephemeral=True)
            return
        try:
            fails = int(await self.bot.redis.get(self._fail_key(i)) or 0)
        except Exception:
            fails = 0
        if fails >= MAX_FAILS:
            await i.response.send_message(t(loc, "vf.too_many"), ephemeral=True)
            return
        if cfg.verification.method == "button":
            await self.grant(i)
        else:
            await i.response.send_modal(CaptchaModal(self, loc))

    def _fail_key(self, i: discord.Interaction) -> str:
        return f"nexus:vf:fail:{i.guild_id}:{i.user.id}"

    async def register_fail(self, i: discord.Interaction) -> None:
        try:
            k = self._fail_key(i)
            if await self.bot.redis.incr(k) == 1:
                await self.bot.redis.expire(k, FAIL_WINDOW)
        except Exception:
            pass

    async def grant(self, i: discord.Interaction) -> None:
        loc = self.loc(i.guild_id)
        cfg = self.cfg(i.guild_id or 0)
        role = i.guild.get_role(cfg.verification.role_id or 0) if cfg and i.guild else None
        if role is None or not isinstance(i.user, discord.Member) or role >= i.guild.me.top_role:  # type: ignore[union-attr]
            await i.response.send_message(t(loc, "vf.error"), ephemeral=True)
            return
        try:
            await i.user.add_roles(role, reason="NEXUS: verificación")
        except discord.HTTPException:
            await i.response.send_message(t(loc, "vf.error"), ephemeral=True)
            return
        log.info("Verificación superada en %s por %s", i.guild_id, i.user.id)
        await i.response.send_message(t(loc, "vf.done"), ephemeral=True)

    async def publish_panel(self, guild: discord.Guild) -> discord.Message:
        """Publica o actualiza el panel; devuelve el mensaje. Lanza RpcFailure si falta algo."""
        from nexus_bot.client import RpcFailure

        async with sessionmaker()() as db:
            row = await db.get(ModuleConfig, (guild.id, "antiraid"))
        if row is None or not row.enabled:
            raise RpcFailure("module_disabled")
        cfg: AntiraidConfig = parse_config("antiraid", row.config, self.loc(guild.id))  # type: ignore[assignment]
        v = cfg.verification
        channel = guild.get_channel(v.channel_id or 0)
        if not v.channel_id or not v.role_id:
            raise RpcFailure("verification_incomplete")
        if not isinstance(channel, discord.TextChannel):
            raise RpcFailure("channel_not_found")
        state = self.bot.cache.get(guild.id)
        kwargs = await with_media(guild.id, render_payload(v.message, context_for(guild.me, guild, channel.id, state.locale,
                                                                  state.timezone), state.embed_color))
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
        view = discord.ui.View(timeout=None)
        view.add_item(VerifyButton(v.button_label))
        try:
            msg = None
            if v.message_id:
                try:
                    msg = await channel.fetch_message(v.message_id)
                    await msg.edit(**for_edit(kwargs), view=view)
                except discord.NotFound:
                    msg = None
            if msg is None:
                msg = await channel.send(**kwargs, view=view)
        except discord.Forbidden as exc:
            raise RpcFailure("bot_cannot_send") from exc
        data = cfg.model_dump(mode="json")
        data["verification"]["message_id"] = str(msg.id)
        async with sessionmaker()() as db:
            await db.execute(update(ModuleConfig).where(ModuleConfig.guild_id == guild.id,
                                                        ModuleConfig.module == "antiraid")
                             .values(config=data, version=ModuleConfig.version + 1, updated_at=utcnow()))
            await db.commit()
        await self.bot.cache.reload_module(guild.id, "antiraid")
        return msg

    async def rpc_publish(self, params: dict[str, Any]) -> dict[str, Any]:
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        if guild is None:
            raise RpcFailure("not_found")
        msg = await self.publish_panel(guild)
        return {"message_id": str(msg.id), "jump_url": msg.jump_url}

    # --- Restricción de canales hasta verificarse ----------------------------------------
    async def rpc_gate(self, params: dict[str, Any]) -> dict[str, Any]:
        """apply: los no verificados solo ven los canales públicos. undo: deja los permisos como estaban."""
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        async with sessionmaker()() as db:
            row = await db.get(ModuleConfig, (int(params["guild_id"]), "antiraid"))
        if guild is None or row is None or not row.enabled:
            raise RpcFailure("module_disabled")
        cfg: AntiraidConfig = parse_config("antiraid", row.config, self.loc(guild.id))  # type: ignore[assignment]
        v = cfg.verification
        reason = "NEXUS: canales visibles antes de verificarse"
        changed = 0
        try:
            # Deshacer siempre primero: así «aplicar» de nuevo con otra lista no acumula cambios.
            # Orden: @everyone y rol verificado antes que el acceso propio del bot ("b"), que va el último
            # para no quedarse sin ver un canal antes de haberlo restaurado.
            for k in sorted(v.gate_backup, key=lambda k: k.startswith("b:")):
                pair = v.gate_backup[k]
                kind, cid = k.split(":", 1)
                channel = guild.get_channel(int(cid))
                target = {"e": guild.default_role, "r": guild.get_role(v.role_id or 0), "b": guild.me}.get(kind)
                if channel is not None and target is not None:
                    ow = None if pair is None else discord.PermissionOverwrite.from_pair(
                        discord.Permissions(pair[0]), discord.Permissions(pair[1]))
                    await channel.set_permissions(target, overwrite=ow, reason=reason)
                    changed += 1
                del v.gate_backup[k]  # restaurado: si algo falla después, no se repite
            v.gate_active = False
            if params.get("action") == "apply":
                if not v.enabled or not v.role_id or not v.channel_id:
                    raise RpcFailure("verification_incomplete")
                role = guild.get_role(v.role_id)
                if role is None:
                    raise RpcFailure("verification_incomplete")
                everyone = guild.default_role
                infos = [GateChannel(
                    id=ch.id, is_category=isinstance(ch, discord.CategoryChannel), in_category=ch.category is not None,
                    synced=bool(getattr(ch, "permissions_synced", False)),
                    everyone_can_view=ch.permissions_for(everyone).view_channel) for ch in guild.channels]
                public_ids = {*v.public_channel_ids, v.channel_id}
                public, hidden = plan_gate(infos, public_ids)

                def backup(kind: str, ch: discord.abc.GuildChannel, who: discord.Role | discord.Member) -> None:
                    current = ch.overwrites.get(who)
                    if current is None:
                        v.gate_backup[f"{kind}:{ch.id}"] = None
                    else:
                        a, d = current.pair()
                        v.gate_backup[f"{kind}:{ch.id}"] = [a.value, d.value]

                # Primero los públicos (dejan de heredar de su categoría), luego se oculta el resto.
                for cid in public:
                    ch = guild.get_channel(cid)
                    if ch is None:
                        continue
                    backup("e", ch, everyone)
                    ow = ch.overwrites_for(everyone)
                    ow.view_channel = True
                    await ch.set_permissions(everyone, overwrite=ow, reason=reason)
                    changed += 1
                for cid in hidden:
                    ch = guild.get_channel(cid)
                    if ch is None:
                        continue
                    # 1) El bot se asegura su propio acceso: ve los canales gracias a @everyone, y al ocultarlos
                    #    a @everyone se quedaría fuera (sin poder dar acceso al rol verificado ni deshacer).
                    backup("b", ch, guild.me)
                    me_ow = ch.overwrites_for(guild.me)
                    me_ow.view_channel = True
                    if isinstance(ch, (discord.VoiceChannel, discord.StageChannel, discord.CategoryChannel)):
                        me_ow.connect = True
                    await ch.set_permissions(guild.me, overwrite=me_ow, reason=reason)
                    # 2) Acceso para el rol verificado.
                    backup("r", ch, role)
                    row_ow = ch.overwrites_for(role)
                    row_ow.view_channel = True
                    await ch.set_permissions(role, overwrite=row_ow, reason=reason)
                    # 3) Por último se oculta a @everyone.
                    backup("e", ch, everyone)
                    ow = ch.overwrites_for(everyone)
                    ow.view_channel = False
                    await ch.set_permissions(everyone, overwrite=ow, reason=reason)
                    changed += 1
                v.gate_active = True
        except discord.Forbidden as exc:
            raise RpcFailure("bot_missing_permissions") from exc
        finally:
            # Guardar siempre el estado (incluso si falló a medias) para poder deshacer lo aplicado.
            data = cfg.model_dump(mode="json")
            async with sessionmaker()() as db:
                await db.execute(update(ModuleConfig).where(ModuleConfig.guild_id == guild.id,
                                                            ModuleConfig.module == "antiraid")
                                 .values(config=data, version=ModuleConfig.version + 1, updated_at=utcnow()))
                await db.commit()
            await self.bot.cache.reload_module(guild.id, "antiraid")
        log.info("Restricción de canales %s en %s (%s cambios)", "aplicada" if v.gate_active else "deshecha",
                 guild.id, changed)
        return {"active": v.gate_active, "changed": changed}

    async def rpc_quarantine_role(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un rol «Cuarentena» que no ve ningún canal (para usarlo con /cuarentena)."""
        from nexus_bot.client import RpcFailure

        guild = self.bot.get_guild(int(params["guild_id"]))
        if guild is None:
            raise RpcFailure("not_found")
        name = "Cuarentena" if self.loc(guild.id) == "es" else "Quarantine"
        try:
            role = await guild.create_role(name=name, permissions=discord.Permissions.none(),
                                           colour=discord.Colour(0x6B7280), reason="NEXUS anti-raid")
        except discord.Forbidden as exc:
            raise RpcFailure("bot_missing_permissions") from exc
        hidden = 0
        for ch in guild.channels:
            if isinstance(ch, discord.CategoryChannel) or not getattr(ch, "permissions_synced", False):
                try:
                    await ch.set_permissions(role, view_channel=False, send_messages=False, connect=False,
                                             reason="NEXUS anti-raid: rol de cuarentena")
                    hidden += 1
                except discord.HTTPException:
                    continue
        return {"role_id": str(role.id), "channels": hidden}

    # --- Entradas: cuentas nuevas y raids -------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = self.cfg(member.guild.id)
        if cfg is None or member.bot:
            return
        guild = member.guild
        now = time.monotonic()
        # 1) ¿Raid en curso? (detectado antes): aplicar la acción a los que siguen entrando.
        in_raid = False
        try:
            in_raid = bool(await self.bot.redis.exists(raid_key(guild.id)))
        except Exception:
            pass
        if in_raid and cfg.raid_action == "kick":
            await self._kick(member, "ar.kick_reason_raid")
            return
        # 2) Detección de raid.
        if cfg.raid_detection and not in_raid:
            q = self.joins.setdefault(guild.id, deque(maxlen=200))
            q.append((now, member.id))
            while q and now - q[0][0] > cfg.raid_seconds:
                q.popleft()
            if len(q) >= cfg.raid_joins:
                recent = [uid for _, uid in q]
                q.clear()
                await self.trigger_raid(guild, cfg, recent)
                return
        # 3) Cuentas nuevas.
        if cfg.min_account_age_days:
            age_days = (discord.utils.utcnow() - member.created_at).total_seconds() / 86400
            if age_days < cfg.min_account_age_days:
                await self._young(member, cfg)

    async def _kick(self, member: discord.Member, reason_key: str) -> bool:
        try:
            await member.kick(reason=t(self.loc(member.guild.id), reason_key))
            return True
        except discord.HTTPException:
            log.info("Anti-raid: no se pudo expulsar a %s en %s", member.id, member.guild.id)
            return False

    async def _young(self, member: discord.Member, cfg: AntiraidConfig) -> None:
        loc = self.loc(member.guild.id)
        if cfg.young_action == "kick":
            await self._kick(member, "ar.kick_reason_young")
        elif cfg.young_action == "quarantine":
            await self.quarantine(member, None, t(loc, "ar.kick_reason_young"))
        await self.alert(member.guild, cfg, t(loc, "alert.title_young"),
                         t(loc, "alert.young", user=f"{member.mention} (`{member.id}`)",
                           created=discord.utils.format_dt(member.created_at, "R"),
                           action=t(loc, f"alert.action_{cfg.young_action}")))

    async def trigger_raid(self, guild: discord.Guild, cfg: AntiraidConfig, recent: list[int]) -> None:
        loc = self.loc(guild.id)
        log.warning("Raid detectado en %s: %s entradas en %ss", guild.id, len(recent), cfg.raid_seconds)
        try:
            await self.bot.redis.set(raid_key(guild.id), "1", ex=cfg.raid_minutes * 60)
        except Exception:
            pass
        if cfg.raid_action == "kick":
            for uid in recent:
                m = guild.get_member(uid)
                if m:
                    await self._kick(m, "ar.kick_reason_raid")
        elif cfg.raid_action == "lockdown":
            await self.set_raid_mode(guild, True, "NEXUS: raid detectado")
        await self.alert(guild, cfg, t(loc, "alert.title_raid"),
                         t(loc, "alert.raid", count=len(recent), seconds=cfg.raid_seconds,
                           action=t(loc, f"alert.action_{cfg.raid_action}"), minutes=cfg.raid_minutes)
                         + "\n" + t(loc, "alert.undo"))

    async def alert(self, guild: discord.Guild, cfg: AntiraidConfig, title: str, text: str) -> None:
        channel_id = cfg.alert_channel_id
        if not channel_id:
            mod = self.bot.get_cog("Moderation")
            if mod:
                channel_id = mod.svc.config(guild.id).log_channel_id  # type: ignore[attr-defined]
        channel = guild.get_channel(channel_id or 0)
        if not isinstance(channel, discord.abc.Messageable):
            return
        e = discord.Embed(title=title, description=text, color=0xEF4444, timestamp=discord.utils.utcnow())
        try:
            await channel.send(embed=e, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    async def set_raid_mode(self, guild: discord.Guild, on: bool, reason: str) -> tuple[int, bool]:
        """Bloquea/desbloquea los canales de texto y pausa/reanuda las invitaciones."""
        from nexus_bot.cogs.moderation import Moderation

        changed = 0
        everyone = guild.default_role
        for ch in guild.text_channels:
            ow = ch.overwrites_for(everyone)
            if on and (ow.send_messages is False or not ch.permissions_for(everyone).send_messages):
                continue
            if not on and ow.send_messages is not False:
                continue
            try:
                await Moderation.lock_channel(ch, on, reason)
                changed += 1
            except discord.HTTPException:
                continue
        invites = False
        try:
            await guild.edit(invites_disabled=on, reason=reason)
            invites = True
        except (discord.HTTPException, TypeError):
            pass
        return changed, invites

    # --- Cuarentena -----------------------------------------------------------------------
    async def quarantine(self, member: discord.Member, moderator: discord.abc.User | None,
                         reason: str | None) -> int | None:
        """Devuelve los roles retirados, o None si ya estaba en cuarentena / falta el rol."""
        cfg = self.cfg(member.guild.id)
        role = member.guild.get_role(cfg.quarantine_role_id or 0) if cfg else None
        if role is None:
            return None
        async with sessionmaker()() as db:
            if await db.get(MemberQuarantine, (member.guild.id, member.id)):
                return None
            me = member.guild.me
            removable = [r for r in member.roles if not r.is_default() and not r.managed and r < me.top_role
                         and r.id != role.id]
            db.add(MemberQuarantine(guild_id=member.guild.id, user_id=member.id,
                                    role_ids=[str(r.id) for r in removable], reason=reason,
                                    moderator_id=moderator.id if moderator else None))
            await add_audit(db, guild_id=member.guild.id, action="antiraid.quarantine", source="bot",
                            actor_id=moderator.id if moderator else None, module="antiraid",
                            changes={"user": {"old": None, "new": str(member.id)}})
            await db.commit()
        try:
            if removable:
                await member.remove_roles(*removable, reason=f"NEXUS cuarentena: {reason or '-'}")
            await member.add_roles(role, reason=f"NEXUS cuarentena: {reason or '-'}")
        except discord.HTTPException:
            log.info("Cuarentena incompleta para %s en %s", member.id, member.guild.id)
        return len(removable)

    async def release(self, member: discord.Member, moderator: discord.abc.User) -> int | None:
        cfg = self.cfg(member.guild.id)
        async with sessionmaker()() as db:
            row = await db.get(MemberQuarantine, (member.guild.id, member.id))
            if row is None:
                return None
            ids = [int(x) for x in row.role_ids]
            await db.delete(row)
            await add_audit(db, guild_id=member.guild.id, action="antiraid.release", source="bot",
                            actor_id=moderator.id, module="antiraid",
                            changes={"user": {"old": str(member.id), "new": None}})
            await db.commit()
        me = member.guild.me
        roles = [r for x in ids if (r := member.guild.get_role(x)) and r < me.top_role and not r.managed]
        q_role = member.guild.get_role(cfg.quarantine_role_id or 0) if cfg else None
        try:
            if q_role and q_role in member.roles:
                await member.remove_roles(q_role, reason="NEXUS: fin de la cuarentena")
            if roles:
                await member.add_roles(*roles, reason="NEXUS: fin de la cuarentena")
        except discord.HTTPException:
            pass
        return len(roles)

    # --- Comandos -------------------------------------------------------------------------
    async def interaction_check(self, i: discord.Interaction) -> bool:  # type: ignore[override]
        if i.guild_id and self.cfg(i.guild_id) is None:
            await i.response.send_message(f"⚠️ {t(self.loc(i.guild_id), 'ar.disabled')}", ephemeral=True)
            return False
        return True

    @app_commands.command(name=key("cmd.raidmode.name"), description=key("cmd.raidmode.description"))
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(on=key("arg.raid_on"))
    async def raidmode(self, i: discord.Interaction, on: bool) -> None:
        assert i.guild
        cfg = self.cfg(i.guild.id)
        assert cfg
        loc = self.loc(i.guild_id)
        await i.response.defer(ephemeral=True)
        try:
            if on:
                await self.bot.redis.set(raid_key(i.guild.id), "1", ex=cfg.raid_minutes * 60)
            else:
                await self.bot.redis.delete(raid_key(i.guild.id))
        except Exception:
            pass
        changed, invites = await self.set_raid_mode(i.guild, on, f"{i.user}: /modo-raid")
        async with sessionmaker()() as db:
            await add_audit(db, guild_id=i.guild.id, action="antiraid.raid_on" if on else "antiraid.raid_off",
                            source="bot", actor_id=i.user.id, module="antiraid")
            await db.commit()
        if on:
            text = t(loc, "ar.raid_on", minutes=cfg.raid_minutes, locked=changed,
                     invites=t(loc, "ar.invites_paused") if invites else "")
        else:
            text = t(loc, "ar.raid_off", unlocked=changed, invites=t(loc, "ar.invites_resumed") if invites else "")
        await i.followup.send(text, ephemeral=True)

    @app_commands.command(name=key("cmd.quarantine.name"), description=key("cmd.quarantine.description"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True, manage_roles=True)
    @app_commands.describe(user=key("arg.user"), reason=key("arg.reason"))
    async def quarantine_cmd(self, i: discord.Interaction, user: discord.Member, reason: str | None = None) -> None:
        assert i.guild and isinstance(i.user, discord.Member)
        loc = self.loc(i.guild_id)
        cfg = self.cfg(i.guild.id)
        if cfg is None or not cfg.quarantine_role_id or i.guild.get_role(cfg.quarantine_role_id) is None:
            await i.response.send_message(f"❌ {t(loc, 'ar.no_q_role')}", ephemeral=True)
            return
        if user.id == i.guild.owner_id or user.id == i.user.id or user.bot:
            await i.response.send_message(f"❌ {t(loc, 'mod.err_self')}", ephemeral=True)
            return
        if i.user.id != i.guild.owner_id and user.top_role >= i.user.top_role:
            await i.response.send_message(f"❌ {t(loc, 'mod.err_hierarchy_you')}", ephemeral=True)
            return
        await i.response.defer(ephemeral=True)
        count = await self.quarantine(user, i.user, reason)
        if count is None:
            await i.followup.send(t(loc, "ar.q_already", user=user.mention), ephemeral=True)
            return
        await i.followup.send(t(loc, "ar.q_done", user=user.mention, count=count), ephemeral=True)

    @app_commands.command(name=key("cmd.release.name"), description=key("cmd.release.description"))
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True, manage_roles=True)
    @app_commands.describe(user=key("arg.user"))
    async def release_cmd(self, i: discord.Interaction, user: discord.Member) -> None:
        loc = self.loc(i.guild_id)
        await i.response.defer(ephemeral=True)
        count = await self.release(user, i.user)
        if count is None:
            await i.followup.send(t(loc, "ar.q_not", user=user.mention), ephemeral=True)
            return
        await i.followup.send(t(loc, "ar.released", user=user.mention, count=count), ephemeral=True)

    verification = app_commands.Group(name=key("cmd.verification.name"),
                                      description=key("cmd.verification.description"), guild_only=True,
                                      default_permissions=discord.Permissions(manage_guild=True))

    @verification.command(name=key("cmd.verification_publish.name"),
                          description=key("cmd.verification_publish.description"))
    async def verification_publish(self, i: discord.Interaction) -> None:
        from nexus_bot.client import RpcFailure

        assert i.guild
        loc = self.loc(i.guild_id)
        await i.response.defer(ephemeral=True)
        try:
            msg = await self.publish_panel(i.guild)
        except RpcFailure:
            await i.followup.send(f"❌ {t(loc, 'ar.verify_not_configured')}", ephemeral=True)
            return
        await i.followup.send(f"✅ {t(loc, 'ar.published', channel=msg.channel.mention)}", ephemeral=True)  # type: ignore[union-attr]


async def setup(bot: NexusBot) -> None:
    await bot.add_cog(Antiraid(bot))
