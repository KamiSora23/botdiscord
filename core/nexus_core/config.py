"""Configuración leída de .env (raíz del proyecto) y variables de entorno."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Path | None:
    explicit = os.environ.get("NEXUS_ENV_FILE")
    if explicit:
        return Path(explicit)
    here = Path.cwd().resolve()
    for folder in (here, *here.parents):
        candidate = folder / ".env"
        if candidate.is_file() and (folder / "docs").is_dir():
            return candidate
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_find_env_file(), extra="ignore")

    env: str = "development"
    # Detrás de Cloudflare Tunnel: la IP real del visitante llega en CF-Connecting-IP.
    trust_cloudflare: bool = False
    database_url: str
    redis_url: str = "redis://127.0.0.1:6379/0"

    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_bot_token: str = ""
    discord_redirect_uri: str = "http://localhost:3000/api/v1/auth/callback"
    dev_guild_id: int | None = None

    dashboard_url: str = "http://localhost:3000"

    # Fase 7 (opcionales): avisos de Twitch e IA de moderación.
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    anthropic_api_key: str = ""
    nexus_ai_model: str = "claude-opus-5-5"
    encryption_key: str = Field(default="")

    @field_validator("dev_guild_id", mode="before")
    @classmethod
    def _guild_id(cls, value: object) -> object:
        """Acepta el ID o un enlace como https://discord.com/channels/<id>[/<canal>]."""
        if value in ("", None):
            return None
        if isinstance(value, str) and "discord.com/channels/" in value:
            parts = value.split("discord.com/channels/", 1)[1].strip("/").split("/")
            return parts[0] if parts and parts[0].isdigit() else value
        return value

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def production_problems(self) -> list[str]:
        """Errores de configuración que impiden arrancar en producción (vacío = todo bien).

        Se comprueba al arrancar la API y el bot para fallar con un mensaje claro en vez de funcionar a medias.
        """
        if not self.is_production:
            return []
        out: list[str] = []
        for name in ("discord_client_id", "discord_client_secret", "discord_bot_token", "encryption_key"):
            if not getattr(self, name).strip():
                out.append(f"{name.upper()} está vacío")
        if self.encryption_key.strip():
            try:
                from cryptography.fernet import Fernet

                Fernet(self.encryption_key.encode())
            except (ValueError, TypeError):
                out.append("ENCRYPTION_KEY no es una clave Fernet válida (genera una nueva, ver .env.example)")
        if self.dev_guild_id is not None:
            out.append("DEV_GUILD_ID debe quedar vacío en producción (si no, los comandos solo salen en ese servidor)")
        if not self.dashboard_url.startswith("https://"):
            out.append("DASHBOARD_URL debe empezar por https:// (tu dominio público)")
        if not self.discord_redirect_uri.startswith(self.dashboard_url.rstrip("/") + "/api/v1/auth/callback"):
            out.append("DISCORD_REDIRECT_URI debe ser DASHBOARD_URL + /api/v1/auth/callback")
        if "CAMBIAR" in self.database_url:
            out.append("DATABASE_URL todavía tiene la contraseña de ejemplo")
        return out

    def check_production(self) -> None:
        """Sale del programa con la lista de problemas si la configuración de producción no es válida."""
        if problems := self.production_problems():
            raise SystemExit("Configuración de producción incompleta:\n  - " + "\n  - ".join(problems))

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
        return url

    @property
    def discord_configured(self) -> bool:
        return bool(self.discord_client_id and self.discord_client_secret and self.discord_bot_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
