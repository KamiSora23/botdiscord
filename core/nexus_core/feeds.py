"""Lectura de fuentes para integraciones: YouTube (feed público), RSS/Atom, GitHub (releases) y Twitch (Helix).

Todo es por sondeo: no hace falta una URL pública ni webhooks, así que funciona igual en local.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from defusedxml import ElementTree as ET

from nexus_core.config import get_settings

MAX_BYTES = 2_000_000
TIMEOUT = 15.0
USER_AGENT = "NexusBot/0.1 (+feed reader)"

YOUTUBE_ID = re.compile(r"(UC[A-Za-z0-9_-]{22})")
GITHUB_REPO = re.compile(r"^(?:(?:https?://)?(?:www\.)?github\.com/)?([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")
TWITCH_LOGIN = re.compile(r"^(?:(?:https?://)?(?:www\.)?twitch\.tv/)?([A-Za-z0-9_]{3,25})/?$")


class FeedError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class FeedItem:
    id: str
    title: str
    url: str
    author: str = ""
    thumbnail: str = ""


def normalize_source(provider: str, raw: str) -> str:
    """Convierte lo que escribe el usuario en un identificador estable, o lanza FeedError."""
    raw = raw.strip()
    if provider == "youtube":
        m = YOUTUBE_ID.search(raw)
        if not m:
            raise FeedError("youtube_channel_id_required")
        return m.group(1)
    if provider == "github":
        m = GITHUB_REPO.match(raw)
        if not m:
            raise FeedError("invalid_repo")
        return f"{m.group(1)}/{m.group(2)}"
    if provider == "twitch":
        m = TWITCH_LOGIN.match(raw)
        if not m:
            raise FeedError("invalid_twitch_login")
        return m.group(1).lower()
    if provider == "rss":
        u = urlparse(raw)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise FeedError("invalid_url")
        return raw
    raise FeedError("invalid_provider")


async def _check_public_host(host: str) -> None:
    """Evita que una URL escrita en el panel haga que el bot acceda a la red interna (SSRF)."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FeedError("host_not_found") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise FeedError("private_address")


async def fetch_text(client: httpx.AsyncClient, url: str) -> str:
    host = urlparse(url).hostname or ""
    await _check_public_host(host)
    async with client.stream("GET", url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
                             follow_redirects=False) as resp:
        if resp.status_code in (301, 302, 303, 307, 308):
            raise FeedError("redirect_not_allowed")
        if resp.status_code == 404:
            raise FeedError("not_found")
        if resp.status_code >= 400:
            raise FeedError(f"http_{resp.status_code}")
        chunks, size = [], 0
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise FeedError("too_large")
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml: str) -> tuple[str, list[FeedItem]]:
    """Lee RSS 2.0 o Atom (incluye el feed de YouTube). Devuelve (título del feed, elementos)."""
    try:
        root = ET.fromstring(xml)
    except Exception as exc:  # noqa: BLE001 - defusedxml lanza varios tipos
        raise FeedError("invalid_feed") from exc
    items: list[FeedItem] = []
    feed_title = ""
    if _local(root.tag) == "rss":
        channel = next((c for c in root if _local(c.tag) == "channel"), None)
        if channel is None:
            raise FeedError("invalid_feed")
        for el in channel:
            if _local(el.tag) == "title":
                feed_title = (el.text or "").strip()
            if _local(el.tag) != "item":
                continue
            d = {_local(c.tag): c for c in el}
            link = (d["link"].text or "").strip() if "link" in d else ""
            guid = (d["guid"].text or "").strip() if "guid" in d else link
            thumb = ""
            for c in el:
                if _local(c.tag) in ("thumbnail", "content") and c.get("url"):
                    thumb = c.get("url", "")
                    break
            items.append(FeedItem(id=guid or link, title=(d["title"].text or "").strip() if "title" in d else "",
                                  url=link, author=(d["author"].text or "").strip() if "author" in d else "",
                                  thumbnail=thumb))
    elif _local(root.tag) == "feed":
        for el in root:
            if _local(el.tag) == "title":
                feed_title = (el.text or "").strip()
            if _local(el.tag) != "entry":
                continue
            entry_id, title, url, author, thumb = "", "", "", "", ""
            for c in el.iter():
                name = _local(c.tag)
                if name == "id" and not entry_id:
                    entry_id = (c.text or "").strip()
                elif name == "title" and not title:
                    title = (c.text or "").strip()
                elif name == "link" and not url and c.get("rel", "alternate") == "alternate":
                    url = c.get("href", "")
                elif name == "name" and not author:
                    author = (c.text or "").strip()
                elif name == "thumbnail" and not thumb:
                    thumb = c.get("url", "")
            items.append(FeedItem(id=entry_id or url, title=title, url=url, author=author, thumbnail=thumb))
    else:
        raise FeedError("invalid_feed")
    return feed_title, [i for i in items if i.id][:50]


def feed_url(provider: str, external_id: str) -> str:
    if provider == "youtube":
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={external_id}"
    if provider == "github":
        return f"https://github.com/{external_id}/releases.atom"
    return external_id


# --- Twitch ----------------------------------------------------------------------

_twitch_token: dict[str, object] = {}


def twitch_configured() -> bool:
    s = get_settings()
    return bool(s.twitch_client_id and s.twitch_client_secret)


async def _twitch_app_token(client: httpx.AsyncClient) -> str:
    import time

    if _twitch_token.get("value") and float(_twitch_token.get("exp", 0)) > time.time() + 60:  # type: ignore[arg-type]
        return str(_twitch_token["value"])
    s = get_settings()
    resp = await client.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": s.twitch_client_id, "client_secret": s.twitch_client_secret,
        "grant_type": "client_credentials"}, timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise FeedError("twitch_auth_failed")
    data = resp.json()
    _twitch_token.update(value=data["access_token"], exp=time.time() + int(data.get("expires_in", 3600)))
    return data["access_token"]


async def twitch_live(client: httpx.AsyncClient, login: str) -> tuple[str, list[FeedItem]]:
    """Si el canal está en directo, devuelve un elemento con el ID de la emisión (uno por directo)."""
    if not twitch_configured():
        raise FeedError("twitch_not_configured")
    token = await _twitch_app_token(client)
    resp = await client.get("https://api.twitch.tv/helix/streams", params={"user_login": login}, timeout=TIMEOUT,
                            headers={"Client-Id": get_settings().twitch_client_id, "Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        raise FeedError(f"http_{resp.status_code}")
    streams = resp.json().get("data", [])
    if not streams:
        return login, []
    s = streams[0]
    thumb = s.get("thumbnail_url", "").replace("{width}", "640").replace("{height}", "360")
    return s.get("user_name", login), [FeedItem(id=s["id"], title=s.get("title", ""), url=f"https://twitch.tv/{login}",
                                                author=s.get("game_name", ""), thumbnail=thumb)]


async def fetch_items(client: httpx.AsyncClient, provider: str, external_id: str) -> tuple[str, list[FeedItem]]:
    if provider == "twitch":
        return await twitch_live(client, external_id)
    return parse_feed(await fetch_text(client, feed_url(provider, external_id)))
