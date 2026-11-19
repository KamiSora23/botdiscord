"""Textos del bot y de los errores de la API en español e inglés."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

LOCALES = ("es", "en")
DEFAULT_LOCALE = "es"


@lru_cache
def _load(locale: str) -> dict[str, str]:
    text = resources.files("nexus_core").joinpath(f"locales/{locale}.json").read_text("utf-8")
    return json.loads(text)


def normalize(locale: str | None) -> str:
    if not locale:
        return DEFAULT_LOCALE
    base = locale.split("-")[0].lower()
    return base if base in LOCALES else "en"


def t(locale: str | None, key: str, **params: Any) -> str:
    loc = normalize(locale)
    text = _load(loc).get(key) or _load(DEFAULT_LOCALE).get(key) or key
    try:
        return text.format(**params)
    except (KeyError, IndexError):
        return text


def has(locale: str | None, key: str) -> bool:
    """¿Existe ese texto en el idioma pedido (sin caer en el idioma por defecto)?"""
    return key in _load(normalize(locale))
