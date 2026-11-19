"""Imágenes subidas desde el panel o con /embed archivo:… para usarlas en embeds.

Los enlaces de los adjuntos de Discord caducan (~24 h), así que guardamos la imagen en la base de datos y la
plantilla apunta a ``media://<id>``. Quien envía el mensaje (bot o API) la adjunta y la cambia por
``attachment://<nombre>``, que Discord muestra dentro del embed.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from typing import Any

MAX_SIZE = 8 * 1024 * 1024  # por imagen (límite de subida sin boost de Discord)
MAX_COUNT = 50  # por servidor
MAX_TOTAL = 100 * 1024 * 1024  # por servidor
MAX_PER_MESSAGE = 10  # Discord: 10 adjuntos por mensaje
MAX_ONE_OFF_TOTAL = 10 * 1024 * 1024  # imágenes de un solo envío: lo que acepta Discord por mensaje sin boost
SLOTS = ("image_url", "thumbnail_url", "author.icon_url", "footer.icon_url")
# El panel pone esta URL en los huecos con imagen de un solo envío (para que el embed no cuente como vacío).
ONE_OFF_PLACEHOLDER = "https://one-off.nexus.invalid/"

MEDIA_RE = re.compile(r"^media://([0-9a-f]{32})$")
_ANY_MEDIA = re.compile(r"media://([0-9a-f]{32})")
UNUSED_TTL_DAYS = 7  # las imágenes que nada usa se borran solas pasado este tiempo
# Secciones del panel con editor de mensajes: quien tenga permiso en cualquiera puede usar la galería.
IMAGE_MODULES = ("embeds", "welcome", "scheduled_messages", "events", "tickets", "reaction_roles",
                 "custom_commands", "responses", "honeypot", "antiraid", "integrations", "levels")

# Dónde se guardan plantillas de mensajes: (tabla, columnas JSON, columna con el nombre para mostrar).
_PLACES = (
    ("module_configs", ("config",), "module"),
    ("custom_commands", ("response",), "name"),
    ("scheduled_messages", ("message",), "name"),
    ("role_panels", ("message",), "name"),
    ("integrations", ("message",), "display_name"),
    ("automod_rules", ("config", "actions"), "name"),
    ("events", ("image_url",), "title"),
)


class MediaError(Exception):
    """Imagen rechazada: ``code`` es file_too_large, image_type o media_quota."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}


def new_id() -> str:
    return secrets.token_hex(16)


def sniff(data: bytes) -> str | None:
    """Tipo real según los primeros bytes (no nos fiamos de la extensión ni del Content-Type)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def file_name(media_id: str, content_type: str) -> str:
    return f"{media_id}.{_EXT.get(content_type, 'png')}"


def media_id(url: str | None) -> str | None:
    m = MEDIA_RE.match(url or "")
    return m.group(1) if m else None


def _slots(e: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    out = []
    for part, key in (("image", "url"), ("thumbnail", "url"), ("author", "icon_url"), ("footer", "icon_url")):
        if isinstance(e.get(part), dict) and key in e[part]:
            out.append((e[part], key))
    return out


def referenced(payload: dict[str, Any]) -> list[str]:
    """IDs media:// que usa un payload ya renderizado (en orden, sin repetir)."""
    seen: list[str] = []
    for e in payload.get("embeds") or []:
        for obj, key in _slots(e):
            mid = media_id(obj[key])
            if mid and mid not in seen:
                seen.append(mid)
    return seen[:MAX_PER_MESSAGE]


def attach(payload: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    """Cambia media://<id> por attachment://<nombre>; si la imagen ya no existe, quita ese campo."""
    for e in payload.get("embeds") or []:
        for obj, key in _slots(e):
            mid = media_id(obj[key])
            if mid is None:
                continue
            if mid in names:
                obj[key] = f"attachment://{names[mid]}"
            else:
                del obj[key]
        for part in ("image", "thumbnail"):
            if isinstance(e.get(part), dict) and not e[part].get("url"):
                del e[part]
        if isinstance(e.get("author"), dict) and not e["author"].get("name"):
            del e["author"]
    return payload


@dataclass
class Loaded:
    id: str
    name: str  # nombre del adjunto en Discord
    content_type: str
    data: bytes


async def load(db: Any, guild_id: int, ids: list[str]) -> list[Loaded]:
    """Imágenes de este servidor con esos IDs (las de otros servidores se ignoran)."""
    if not ids:
        return []
    from sqlalchemy import select

    from nexus_core.db.models import Media

    rows = (await db.execute(select(Media.id, Media.content_type, Media.data)
                             .where(Media.guild_id == guild_id, Media.id.in_(ids)))).all()
    return [Loaded(r.id, file_name(r.id, r.content_type), r.content_type, r.data) for r in rows]


def rest_kwargs(payload: dict[str, Any], files: list[Loaded], extra: list[Loaded] | None = None) -> dict[str, Any]:
    """Argumentos para DiscordREST.request: JSON normal o multipart con las imágenes adjuntas.

    ``extra``: imágenes de un solo envío, ya colocadas como attachment:// (no se guardan).
    """
    attach(payload, {f.id: f.name for f in files})
    files = files + (extra or [])
    if not files:
        return {"json": payload}
    payload["attachments"] = [{"id": i, "filename": f.name} for i, f in enumerate(files)]
    return {"data": {"payload_json": json.dumps(payload)},
            "files": [(f"files[{i}]", (f.name, f.data, f.content_type)) for i, f in enumerate(files)]}


async def usage(db: Any, guild_id: int) -> dict[str, list[dict[str, str]]]:
    """Para cada imagen usada: dónde (módulo, comando, mensaje programado, panel…)."""
    from sqlalchemy import String, cast, or_, select

    from nexus_core.db.models import Base

    out: dict[str, list[dict[str, str]]] = {}
    for table_name, cols, label in _PLACES:
        table = Base.metadata.tables[table_name]
        texts = [cast(table.c[c], String) for c in cols]
        rows = (await db.execute(select(table.c[label], *texts).where(
            table.c.guild_id == guild_id, or_(*[t.like("%media://%") for t in texts])))).all()
        for row in rows:
            place = {"type": table_name, "name": str(row[0])}
            for text in row[1:]:
                for mid in _ANY_MEDIA.findall(text or ""):
                    if place not in out.setdefault(mid, []):
                        out[mid].append(place)
    return out


async def cleanup_unused(db: Any, guild_id: int, *, older_than_days: int | None = UNUSED_TTL_DAYS) -> int:
    """Borra las imágenes que nada usa (si se da, solo las subidas hace más de N días). Devuelve cuántas."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete, select

    from nexus_core.db.models import Media

    used = await usage(db, guild_id)
    q = select(Media.id).where(Media.guild_id == guild_id)
    if older_than_days is not None:
        q = q.where(Media.created_at < datetime.now(timezone.utc) - timedelta(days=older_than_days))
    gone = [mid for mid in (await db.scalars(q)).all() if mid not in used]
    if gone:
        await db.execute(delete(Media).where(Media.guild_id == guild_id, Media.id.in_(gone)))
    return len(gone)


def place_one_off(payload: dict[str, Any], slots: dict[str, str]) -> None:
    """Pone attachment://<nombre> en los huecos de imagen del primer embed (``slots``: hueco → nombre)."""
    embeds = payload.get("embeds") or []
    if not embeds:
        return
    e = embeds[0]
    # Huecos con el marcador pero sin archivo: se quitan (nunca se manda esa URL a Discord).
    for obj, key in _slots(e):
        if str(obj.get(key, "")).startswith(ONE_OFF_PLACEHOLDER):
            del obj[key]
    for part in ("image", "thumbnail"):
        if isinstance(e.get(part), dict) and not e[part].get("url"):
            del e[part]
    for slot, name in slots.items():
        url = f"attachment://{name}"
        if slot == "image_url":
            e["image"] = {"url": url}
        elif slot == "thumbnail_url":
            e["thumbnail"] = {"url": url}
        elif slot == "author.icon_url" and isinstance(e.get("author"), dict):
            e["author"]["icon_url"] = url
        elif slot == "footer.icon_url" and isinstance(e.get("footer"), dict):
            e["footer"]["icon_url"] = url


async def store(db: Any, guild_id: int, filename: str, data: bytes, created_by: int | None) -> Any:
    """Valida y guarda una imagen (sin commit). Lanza MediaError si no es válida o no cabe."""
    from sqlalchemy import func, select

    from nexus_core.db.models import Media

    if len(data) > MAX_SIZE:
        raise MediaError("file_too_large")
    ctype = sniff(data)
    if ctype is None:
        raise MediaError("image_type")
    count, total = (await db.execute(select(func.count(), func.coalesce(func.sum(Media.size), 0))
                                     .where(Media.guild_id == guild_id))).one()
    if count >= MAX_COUNT or total + len(data) > MAX_TOTAL:
        raise MediaError("media_quota")
    name = (filename or "imagen").replace("\\", "/").rsplit("/", 1)[-1][:100] or "imagen"
    row = Media(id=new_id(), guild_id=guild_id, filename=name, content_type=ctype, size=len(data), data=data,
                created_by=created_by)
    db.add(row)
    return row


async def attachment_name(db: Any, guild_id: int, url: str | None) -> str | None:
    """attachment://<nombre> para una imagen media:// ya adjunta a un mensaje (sin cargar los bytes)."""
    mid = media_id(url)
    if mid is None:
        return None
    from sqlalchemy import select

    from nexus_core.db.models import Media

    ctype = await db.scalar(select(Media.content_type).where(Media.guild_id == guild_id, Media.id == mid))
    return file_name(mid, ctype) if ctype else None
