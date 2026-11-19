"""Sustitución de variables y conversión a payload de Discord (docs/NEXUS_DATABASE_SPEC.md §3.2).

El bot, la vista previa de la API y el botón "Enviar prueba" usan esta misma función.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from nexus_core.messages.template import Embed, MessageTemplate

VAR_RE = re.compile(r"\{([a-z_]+(?:\.[a-z_]+)?)\}")

KNOWN_VARIABLES = (
    "user", "user.name", "user.display_name", "user.id", "user.avatar", "user.created_at", "user.joined_at",
    "server", "server.id", "server.icon", "member_count", "member_count.ordinal", "channel",
)

INTEGRATION_VARIABLES = ("title", "url", "author", "name", "thumbnail")

_MONTHS = {
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}


@dataclass
class RenderContext:
    user_id: int
    user_name: str
    user_display_name: str
    user_avatar_url: str
    user_created_at: datetime | None
    user_joined_at: datetime | None
    server_id: int
    server_name: str
    server_icon_url: str | None
    member_count: int
    channel_id: int | None = None
    locale: str = "es"
    timezone: str = "UTC"


def ordinal(n: int, locale: str) -> str:
    if locale == "es":
        return f"{n}.º"
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def format_date(dt: datetime | None, locale: str, tz: str) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        dt = dt.astimezone(ZoneInfo(tz))
    except Exception:
        pass
    months = _MONTHS.get(locale, _MONTHS["en"])
    if locale == "es":
        return f"{dt.day} {months[dt.month - 1]} {dt.year}"
    return f"{months[dt.month - 1]} {dt.day}, {dt.year}"


def variables(ctx: RenderContext) -> dict[str, str]:
    return {
        "user": f"<@{ctx.user_id}>",
        "user.name": ctx.user_name,
        "user.display_name": ctx.user_display_name,
        "user.id": str(ctx.user_id),
        "user.avatar": ctx.user_avatar_url,
        "user.created_at": format_date(ctx.user_created_at, ctx.locale, ctx.timezone),
        "user.joined_at": format_date(ctx.user_joined_at, ctx.locale, ctx.timezone),
        "server": ctx.server_name,
        "server.id": str(ctx.server_id),
        "server.icon": ctx.server_icon_url or "",
        "member_count": str(ctx.member_count),
        "member_count.ordinal": ordinal(ctx.member_count, ctx.locale),
        "channel": f"<#{ctx.channel_id}>" if ctx.channel_id else "",
    }


def substitute(text: str | None, values: dict[str, str]) -> str | None:
    if text is None:
        return None
    return VAR_RE.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def unknown_variables(template: MessageTemplate) -> set[str]:
    found: set[str] = set()
    for text in _all_texts(template):
        found.update(m.group(1) for m in VAR_RE.finditer(text or ""))
    return found - set(KNOWN_VARIABLES)


def _all_texts(t: MessageTemplate) -> list[str | None]:
    out: list[str | None] = [t.content]
    for e in t.embeds:
        out += [e.title, e.description, e.url, e.thumbnail_url, e.image_url, e.author.name, e.author.icon_url,
                e.author.url, e.footer.text, e.footer.icon_url]
        for f in e.fields:
            out += [f.name, f.value]
    return out


def _url(v: str | None, values: dict[str, str], *, media: bool = True) -> str | None:
    """URL final: https://… o, para imágenes, una subida al panel (media://<id>, la adjunta quien envía)."""
    out = substitute(v, values)
    if not out:
        return None
    if out.startswith("https://") or (media and out.startswith("media://")):
        return out
    return None


def _embed_payload(e: Embed, values: dict[str, str], default_color: int) -> dict[str, Any]:
    p: dict[str, Any] = {"color": e.color if e.color is not None else default_color}
    if e.title:
        p["title"] = substitute(e.title, values)[:256]
    if e.description:
        p["description"] = substitute(e.description, values)[:4096]
    if (u := _url(e.url, values, media=False)) and e.title:
        p["url"] = u
    if e.author.name:
        a: dict[str, Any] = {"name": substitute(e.author.name, values)[:256]}
        if u := _url(e.author.icon_url, values):
            a["icon_url"] = u
        if u := _url(e.author.url, values, media=False):
            a["url"] = u
        p["author"] = a
    if u := _url(e.thumbnail_url, values):
        p["thumbnail"] = {"url": u}
    if u := _url(e.image_url, values):
        p["image"] = {"url": u}
    if e.footer.text:
        f: dict[str, Any] = {"text": substitute(e.footer.text, values)[:2048]}
        if u := _url(e.footer.icon_url, values):
            f["icon_url"] = u
        p["footer"] = f
    if e.timestamp:
        p["timestamp"] = datetime.now(timezone.utc).isoformat()
    if e.fields:
        p["fields"] = [
            {"name": substitute(x.name, values)[:256], "value": substitute(x.value, values)[:1024], "inline": x.inline}
            for x in e.fields
        ]
    return p


def render_payload(template: MessageTemplate, ctx: RenderContext, default_color: int,
                   extra: dict[str, str] | None = None) -> dict[str, Any]:
    """Payload JSON listo para POST /channels/{id}/messages (o discord.py vía from_dict).

    ``extra`` añade variables propias de un módulo, p. ej. {title} y {url} en integraciones.
    """
    values = {**variables(ctx), **(extra or {})}
    payload: dict[str, Any] = {
        "allowed_mentions": {"parse": [], "users": [str(ctx.user_id)]},
    }
    if template.content:
        payload["content"] = substitute(template.content, values)[:2000]
    embeds = [_embed_payload(e, values, default_color) for e in template.embeds if e.has_content()]
    if embeds:
        payload["embeds"] = embeds
    return payload
