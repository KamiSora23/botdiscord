"""Formato único de errores (docs/NEXUS_API_SPEC.md §5)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from nexus_core.discord.rest import DiscordError
from nexus_core.i18n import normalize, t


class ApiError(Exception):
    def __init__(self, status: int, code: str, *, fields: dict[str, str] | None = None,
                 **extra: Any):
        super().__init__(code)
        self.status = status
        self.code = code
        self.fields = fields
        self.extra = extra


def request_locale(request: Request) -> str:
    loc = getattr(request.state, "locale", None)
    if loc:
        return loc
    header = request.headers.get("accept-language", "")
    return normalize(header.split(",")[0] if header else None)


def error_body(request: Request, code: str, fields: dict[str, str] | None = None,
               **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": t(request_locale(request), f"error.{code}")}
    if fields:
        body["fields"] = fields
    body.update(extra)
    return {"error": body}


def _field_path(loc: tuple[Any, ...]) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) or "_"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        headers = {}
        if "retry_after" in exc.extra:
            headers["Retry-After"] = str(exc.extra["retry_after"])
        return JSONResponse(error_body(request, exc.code, exc.fields, **exc.extra),
                            status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for err in exc.errors():
            msg = err.get("msg", "invalid")
            if msg.startswith("Value error, "):
                msg = msg.removeprefix("Value error, ")
            fields[_field_path(tuple(err.get("loc", ())))] = msg
        return JSONResponse(error_body(request, "validation_error", fields), status_code=400)

    @app.exception_handler(DiscordError)
    async def _discord(request: Request, exc: DiscordError) -> JSONResponse:
        return JSONResponse(error_body(request, "discord_unavailable"), status_code=502)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found",
                405: "not_found"}.get(exc.status_code, "internal")
        return JSONResponse(error_body(request, code), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        import logging

        logging.getLogger("nexus.api").exception("Error no controlado en %s", request.url.path)
        return JSONResponse(error_body(request, "internal"), status_code=500)
