"""Cliente REST mínimo para la API de Discord, con respeto de rate limits."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

API_BASE = "https://discord.com/api/v10"
CDN = "https://cdn.discordapp.com"


class DiscordError(Exception):
    def __init__(self, status: int, body: Any):
        super().__init__(f"Discord respondió {status}: {body}")
        self.status = status
        self.body = body


class DiscordREST:
    def __init__(self, bot_token: str | None = None, *, timeout: float = 10.0):
        self._bot_token = bot_token
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            timeout=timeout,
            headers={"User-Agent": "DiscordBot (https://github.com, 0.1) NexusBot"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self, method: str, path: str, *, bearer: str | None = None, retries: int = 2, **kw: Any
    ) -> Any:
        headers = kw.pop("headers", {})
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        elif self._bot_token:
            headers["Authorization"] = f"Bot {self._bot_token}"
        for attempt in range(retries + 1):
            resp = await self._client.request(method, path, headers=headers, **kw)
            if resp.status_code == 429 and attempt < retries:
                retry_after = float(resp.json().get("retry_after", 1.0))
                await asyncio.sleep(min(retry_after, 10.0))
                continue
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                except ValueError:
                    body = resp.text
                raise DiscordError(resp.status_code, body)
            if resp.status_code == 204:
                return None
            return resp.json()
        raise DiscordError(429, "rate limited")

    # --- OAuth2 -----------------------------------------------------------
    async def exchange_code(self, *, client_id: str, client_secret: str, code: str,
                            redirect_uri: str) -> dict[str, Any]:
        return await self._token(client_id, client_secret, {
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        })

    async def refresh_token(self, *, client_id: str, client_secret: str,
                            refresh_token: str) -> dict[str, Any]:
        return await self._token(client_id, client_secret, {
            "grant_type": "refresh_token", "refresh_token": refresh_token,
        })

    async def _token(self, client_id: str, client_secret: str, data: dict[str, str]) -> dict[str, Any]:
        resp = await self._client.post(
            "/oauth2/token", data=data, auth=(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code >= 400:
            raise DiscordError(resp.status_code, resp.text)
        return resp.json()


def avatar_url(user_id: int | str, avatar: str | None, size: int = 128) -> str:
    if avatar:
        ext = "gif" if avatar.startswith("a_") else "png"
        return f"{CDN}/avatars/{user_id}/{avatar}.{ext}?size={size}"
    index = (int(user_id) >> 22) % 6
    return f"{CDN}/embed/avatars/{index}.png"


def guild_icon_url(guild_id: int | str, icon: str | None, size: int = 128) -> str | None:
    if not icon:
        return None
    ext = "gif" if icon.startswith("a_") else "png"
    return f"{CDN}/icons/{guild_id}/{icon}.{ext}?size={size}"
