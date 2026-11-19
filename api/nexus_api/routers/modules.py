"""Endpoints genéricos de módulos + específicos de Welcome y Embeds (docs/NEXUS_API_SPEC.md §6.5–6.6)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core import media as M
from nexus_core.db.models import GuildConfig, ModuleConfig
from nexus_core.db.repo import add_audit, diff_changes, utcnow
from nexus_core.discord.rest import DiscordError, avatar_url, guild_icon_url
from nexus_core.messages import MessageTemplate, RenderContext, Snowflake, render_payload, unknown_variables
from nexus_core.modules import REGISTRY, parse_config, schemas
from nexus_core.sync import publish

from nexus_api.deps import GuildAccess, get_db, guild_access, rate_limit, require_csrf
from nexus_api.errors import ApiError
from nexus_api.services import guild_data as G

router = APIRouter(prefix="/guilds/{guild_id}/modules", tags=["modules"],
                   dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])
tools = APIRouter(prefix="/guilds/{guild_id}", tags=["modules"],
                  dependencies=[Depends(require_csrf), Depends(rate_limit("api", 120))])

write_limit = Depends(rate_limit("write", 30, per="guild"))
test_limit = Depends(rate_limit("welcome_test", 5, per="guild"))


def _schema_or_404(module: str):
    info = REGISTRY.get(module)
    sch = schemas().get(module)
    if info is None or sch is None or not info.available:
        raise ApiError(404, "not_found")
    return info, sch


def validation_fields(exc: ValidationError, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for err in exc.errors():
        path = ".".join(str(p) for p in err["loc"])
        msg = err.get("msg", "invalid").removeprefix("Value error, ")
        out[(prefix + path) or "_"] = msg
    return out


async def _locale(db: AsyncSession, guild_id: int) -> str:
    cfg = await db.get(GuildConfig, guild_id)
    return cfg.locale if cfg else "es"


def _module_json(module: str, row: ModuleConfig | None, cfg: BaseModel) -> dict[str, Any]:
    return {
        "module": module,
        "enabled": bool(row and row.enabled),
        "config": cfg.model_dump(mode="json"),
        "version": row.version if row else 0,
        "updated_at": row.updated_at.isoformat() if row else None,
        "updated_by": str(row.updated_by) if row and row.updated_by else None,
    }


async def _channel_warnings(request: Request, access: GuildAccess, config: dict[str, Any]) -> list[dict]:
    """Avisos si el bot no puede escribir en los canales elegidos (no bloquean el guardado)."""
    ids: list[tuple[str, str]] = []

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else k
                if k == "channel_id" and v and (obj.get("enabled", True)):
                    ids.append((p, str(v)))
                else:
                    walk(v, p)

    walk(config, "")
    if not ids or access.guild is None:
        return []
    try:
        channels = {c["id"]: c for c in await G.channels_with_bot_perms(request, access.guild_id, access.guild.owner_id)}
    except Exception:
        return []
    warnings = []
    for field, cid in ids:
        ch = channels.get(cid)
        if ch is None:
            warnings.append({"code": "channel_not_found", "field": field})
        elif not ch["bot_can_send"]:
            warnings.append({"code": "bot_cannot_send", "field": field})
        elif not ch["bot_can_embed"]:
            warnings.append({"code": "bot_cannot_embed", "field": field})
    return warnings


@router.get("/{module}")
async def get_module(module: str, access: GuildAccess = Depends(guild_access(1)),
                     db: AsyncSession = Depends(get_db)) -> dict:
    _schema_or_404(module)
    row = await db.get(ModuleConfig, (access.guild_id, module))
    cfg = parse_config(module, row.config if row else {}, await _locale(db, access.guild_id))
    return {"data": _module_json(module, row, cfg), "can_edit": access.level >= 2, "can_manage": access.level >= 3}


class ModuleIn(BaseModel):
    config: dict[str, Any]
    version: int


@router.put("/{module}", dependencies=[write_limit])
async def put_module(module: str, body: ModuleIn, request: Request,
                     access: GuildAccess = Depends(guild_access(2)), db: AsyncSession = Depends(get_db)) -> dict:
    _, sch = _schema_or_404(module)
    try:
        cfg = sch.model.model_validate(body.config)
    except ValidationError as exc:
        raise ApiError(400, "validation_error", fields=validation_fields(exc, "config.")) from exc
    data = cfg.model_dump(mode="json")
    if module == "autoroles":
        await G.reject_dangerous_roles(request, access.guild_id, data["human_role_ids"], "config.human_role_ids")
        await G.reject_dangerous_roles(request, access.guild_id, data["bot_role_ids"], "config.bot_role_ids")
    now = utcnow()
    row = await db.get(ModuleConfig, (access.guild_id, module))
    locale = await _locale(db, access.guild_id)
    old = row.config if row and row.config else sch.default(locale).model_dump(mode="json")
    if row is None:
        if body.version != 0:
            raise ApiError(409, "version_conflict", current_version=0)
        stmt = insert(ModuleConfig).values(guild_id=access.guild_id, module=module, config=data, version=1,
                                           updated_at=now, updated_by=access.auth.user.id).on_conflict_do_nothing()
        res = await db.execute(stmt)
        if not res.rowcount:
            await db.rollback()
            raise ApiError(409, "version_conflict", current_version=1)
        new_version = 1
    else:
        res = await db.execute(
            update(ModuleConfig)
            .where(ModuleConfig.guild_id == access.guild_id, ModuleConfig.module == module,
                   ModuleConfig.version == body.version)
            .values(config=data, version=ModuleConfig.version + 1, updated_at=now, updated_by=access.auth.user.id)
            .returning(ModuleConfig.version))
        new_version = res.scalar_one_or_none()
        if new_version is None:
            await db.rollback()
            current = await db.scalar(select(ModuleConfig.version).where(
                ModuleConfig.guild_id == access.guild_id, ModuleConfig.module == module))
            raise ApiError(409, "version_conflict", current_version=current)
    changes = diff_changes(old, data)
    if changes:
        await add_audit(db, guild_id=access.guild_id, action="module.update", source="dashboard",
                        actor_id=access.auth.user.id, module=module, changes=_trim(changes))
    await db.commit()
    await _publish(request, "module.updated", access.guild_id, module, new_version)
    row = await db.get(ModuleConfig, (access.guild_id, module))
    await db.refresh(row)
    return {"data": _module_json(module, row, cfg), "warnings": await _channel_warnings(request, access, data)}


def _trim(changes: dict[str, Any], limit: int = 500) -> dict[str, Any]:
    """Los textos largos se recortan en el historial."""
    out = {}
    for k, v in changes.items():
        out[k] = {side: (val[:limit] + "…" if isinstance(val, str) and len(val) > limit else val)
                  for side, val in v.items()}
    return out


async def _publish(request: Request, kind: str, guild_id: int, module: str, version: int | None) -> None:
    try:
        await publish(request.app.state.redis, kind, guild_id, module=module, version=version)  # type: ignore[arg-type]
    except Exception:
        pass  # el bot lo recupera en su revisión periódica


class EnabledIn(BaseModel):
    enabled: bool


@router.patch("/{module}/enabled", dependencies=[write_limit])
async def toggle_module(module: str, body: EnabledIn, request: Request,
                        access: GuildAccess = Depends(guild_access(3)), db: AsyncSession = Depends(get_db)) -> dict:
    info, sch = _schema_or_404(module)
    if not info.toggleable:
        raise ApiError(404, "not_found")
    locale = await _locale(db, access.guild_id)
    now = utcnow()
    stmt = insert(ModuleConfig).values(
        guild_id=access.guild_id, module=module, enabled=body.enabled,
        config=sch.default(locale).model_dump(mode="json"), version=1, updated_at=now, updated_by=access.auth.user.id,
    ).on_conflict_do_update(
        index_elements=[ModuleConfig.guild_id, ModuleConfig.module],
        set_={"enabled": body.enabled, "version": ModuleConfig.version + 1, "updated_at": now,
              "updated_by": access.auth.user.id},
    ).returning(ModuleConfig.version)
    version = (await db.execute(stmt)).scalar_one()
    await add_audit(db, guild_id=access.guild_id, action="module.enable" if body.enabled else "module.disable",
                    source="dashboard", actor_id=access.auth.user.id, module=module)
    await db.commit()
    await _publish(request, "module.toggled", access.guild_id, module, version)
    return {"enabled": body.enabled, "version": version}


@router.post("/{module}/reset", dependencies=[write_limit])
async def reset_module(module: str, request: Request, access: GuildAccess = Depends(guild_access(3)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    _, sch = _schema_or_404(module)
    row = await db.get(ModuleConfig, (access.guild_id, module))
    cfg = sch.default(await _locale(db, access.guild_id))
    if row is not None:
        row.config = cfg.model_dump(mode="json")
        row.version += 1
        row.updated_at = utcnow()
        row.updated_by = access.auth.user.id
        await add_audit(db, guild_id=access.guild_id, action="module.reset", source="dashboard",
                        actor_id=access.auth.user.id, module=module)
        await db.commit()
        await _publish(request, "module.updated", access.guild_id, module, row.version)
    return {"data": _module_json(module, row, cfg)}


# --- Renderizado con el usuario actual como "miembro de ejemplo" -------------------

async def _context(request: Request, access: GuildAccess, db: AsyncSession, channel_id: int | None) -> RenderContext:
    user = access.auth.user
    guild = access.guild
    assert guild is not None
    cfg = await db.get(GuildConfig, guild.id)
    joined: datetime | None = None
    display = user.global_name or user.username
    try:
        member = await request.app.state.discord.request("GET", f"/guilds/{guild.id}/members/{user.id}")
        display = member.get("nick") or display
        if member.get("joined_at"):
            joined = datetime.fromisoformat(member["joined_at"])
    except DiscordError:
        pass
    created = datetime.fromtimestamp(((user.id >> 22) + 1420070400000) / 1000).astimezone()
    return RenderContext(
        user_id=user.id, user_name=user.username, user_display_name=display,
        user_avatar_url=avatar_url(user.id, user.avatar, 256), user_created_at=created, user_joined_at=joined,
        server_id=guild.id, server_name=guild.name, server_icon_url=guild_icon_url(guild.id, guild.icon),
        member_count=guild.member_count + 1, channel_id=channel_id,
        locale=cfg.locale if cfg else "es", timezone=cfg.timezone if cfg else "UTC",
    )


class PreviewIn(BaseModel):
    message: dict[str, Any]
    channel_id: str | None = None


@router.post("/welcome/preview")
async def preview(body: PreviewIn, request: Request, access: GuildAccess = Depends(guild_access(1)),
                  db: AsyncSession = Depends(get_db)) -> dict:
    try:
        tmpl = MessageTemplate.model_validate(body.message)
    except ValidationError as exc:
        raise ApiError(400, "validation_error", fields=validation_fields(exc, "message.")) from exc
    cfg = await db.get(GuildConfig, access.guild_id)
    ctx = await _context(request, access, db, int(body.channel_id) if body.channel_id else None)
    return {"payload": render_payload(tmpl, ctx, cfg.embed_color if cfg else 0x7465F7),
            "unknown_variables": sorted(unknown_variables(tmpl))}


class TestIn(BaseModel):
    part: str = "join"  # join | leave | dm


async def _rest_payload(db: AsyncSession, guild_id: int, payload: dict[str, Any],
                        extra: list[M.Loaded] | None = None) -> dict[str, Any]:
    return M.rest_kwargs(payload, await M.load(db, guild_id, M.referenced(payload)), extra)


async def _send(request: Request, channel_id: int, payload: dict[str, Any], *, db: AsyncSession,
                guild_id: int, extra: list[M.Loaded] | None = None) -> dict[str, Any]:
    kw = await _rest_payload(db, guild_id, payload, extra)
    try:
        return await request.app.state.discord.request("POST", f"/channels/{channel_id}/messages", **kw)
    except DiscordError as exc:
        if exc.status in (403, 404):
            raise ApiError(409, "bot_cannot_send", channel_id=str(channel_id)) from exc
        raise


@router.post("/welcome/test", dependencies=[test_limit])
async def welcome_test(body: TestIn, request: Request, access: GuildAccess = Depends(guild_access(2)),
                       db: AsyncSession = Depends(get_db)) -> dict:
    row = await db.get(ModuleConfig, (access.guild_id, "welcome"))
    cfg = parse_config("welcome", row.config if row else {}, await _locale(db, access.guild_id))
    gcfg = await db.get(GuildConfig, access.guild_id)
    color = gcfg.embed_color if gcfg else 0x7465F7
    if body.part == "dm":
        tmpl = cfg.join.dm.message  # type: ignore[attr-defined]
        if tmpl is None:
            raise ApiError(400, "validation_error", fields={"dm.message": "message_required"})
        ctx = await _context(request, access, db, None)
        try:
            dm = await request.app.state.discord.request("POST", "/users/@me/channels",
                                                         json={"recipient_id": str(access.auth.user.id)})
            await request.app.state.discord.request(
                "POST", f"/channels/{dm['id']}/messages",
                **await _rest_payload(db, access.guild_id, render_payload(tmpl, ctx, color)))
        except DiscordError as exc:
            raise ApiError(409, "dm_closed") from exc
    else:
        part = cfg.join if body.part == "join" else cfg.leave  # type: ignore[attr-defined]
        if not part.channel_id:
            raise ApiError(400, "validation_error", fields={f"{body.part}.channel_id": "channel_required"})
        ctx = await _context(request, access, db, part.channel_id)
        await _send(request, part.channel_id, render_payload(part.message, ctx, color), db=db,
                    guild_id=access.guild_id)
    await add_audit(db, guild_id=access.guild_id, action="welcome.test_sent", source="dashboard",
                    actor_id=access.auth.user.id, module="welcome")
    await db.commit()
    return {"sent": True}


# --- Editor de embeds (herramienta) -----------------------------------------------

class EmbedSendIn(BaseModel):
    channel_id: Snowflake
    message: dict[str, Any]


async def _one_off_files(request: Request) -> tuple[dict[str, Any], dict[str, str], list[M.Loaded]]:
    """Cuerpo multipart: «payload» (JSON) + imágenes «solo para este envío» en «file:<hueco>». No se guardan."""
    form = await request.form()
    try:
        raw = json.loads(str(form.get("payload") or ""))
    except ValueError as exc:
        raise ApiError(400, "validation_error", fields={"payload": "invalid_json"}) from exc
    slots: dict[str, str] = {}
    files: list[M.Loaded] = []
    total = 0
    for slot in M.SLOTS:
        up = form.get(f"file:{slot}")
        if up is None or isinstance(up, str):
            continue
        data = await up.read(M.MAX_SIZE + 1)
        total += len(data)
        if len(data) > M.MAX_SIZE or total > M.MAX_ONE_OFF_TOTAL:
            raise ApiError(413, "validation_error", fields={slot: "file_too_large"})
        ctype = M.sniff(data)
        if ctype is None:
            raise ApiError(400, "validation_error", fields={slot: "image_type"})
        mid = M.new_id()
        f = M.Loaded(mid, M.file_name(mid, ctype), ctype, data)
        files.append(f)
        slots[slot] = f.name
    return raw, slots, files


@tools.post("/embeds/send", dependencies=[write_limit])
async def send_embed(request: Request, access: GuildAccess = Depends(guild_access(2)),
                     db: AsyncSession = Depends(get_db)) -> dict:
    slots: dict[str, str] = {}
    one_off: list[M.Loaded] = []
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        raw, slots, one_off = await _one_off_files(request)
    else:
        try:
            raw = await request.json()
        except ValueError as exc:
            raise ApiError(400, "validation_error", fields={"_": "invalid_json"}) from exc
    try:
        body = EmbedSendIn.model_validate(raw)
        tmpl = MessageTemplate.model_validate(body.message)
    except ValidationError as exc:
        raise ApiError(400, "validation_error", fields=validation_fields(exc, "message.")) from exc
    gcfg = await db.get(GuildConfig, access.guild_id)
    ctx = await _context(request, access, db, body.channel_id)
    payload = render_payload(tmpl, ctx, gcfg.embed_color if gcfg else 0x7465F7)
    payload["allowed_mentions"] = {"parse": []}  # mensajes del staff: sin menciones masivas
    M.place_one_off(payload, slots)
    msg = await _send(request, body.channel_id, payload, db=db, guild_id=access.guild_id, extra=one_off)
    await add_audit(db, guild_id=access.guild_id, action="embed.sent", source="dashboard",
                    actor_id=access.auth.user.id, module="embeds",
                    changes={"channel_id": {"old": None, "new": str(body.channel_id)}})
    await db.commit()
    return {"message_id": msg["id"], "channel_id": str(body.channel_id),
            "url": f"https://discord.com/channels/{access.guild_id}/{body.channel_id}/{msg['id']}"}

