"""Configuración de logs compartida por la API y el bot.

- Oculta secretos (token del bot, client secret, claves) aunque acaben en un mensaje o traza.
- En producción escribe una línea JSON por evento (fácil de filtrar con `docker compose logs`).
- Incluye el ``request_id`` de la petición HTTP en curso, si lo hay.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re

from nexus_core.config import get_settings

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

# Formas típicas de credenciales aunque no coincidan con las de .env (tokens de Discord, Bearer, claves sk-).
_PATTERNS = [
    re.compile(r"[MNO][A-Za-z\d_-]{23,27}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,40}"),
    re.compile(r"(?i)(bearer|bot)\s+[A-Za-z0-9._~+/=-]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
]
REDACTED = "[OCULTO]"


class RedactFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        s = get_settings()
        self.secrets = [v for v in (s.discord_bot_token, s.discord_client_secret, s.twitch_client_secret,
                                    s.anthropic_api_key, s.encryption_key) if v and len(v) >= 8]

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, REDACTED)
        for pat in _PATTERNS:
            text = pat.sub(REDACTED, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        clean = self.redact(msg)
        if clean != msg:
            record.msg, record.args = clean, None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if getattr(record, "request_id", None):
            data["request_id"] = record.request_id
        if record.exc_text:
            data["exception"] = record.exc_text
        return json.dumps(data, ensure_ascii=False)


def setup_logging() -> None:
    """Llamar una vez al arrancar. Texto legible en desarrollo, JSON en producción."""
    handler = logging.StreamHandler()
    handler.addFilter(RedactFilter())
    if get_settings().env == "production":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    # Los loggers de uvicorn tienen sus propios handlers: que usen también el nuestro.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
