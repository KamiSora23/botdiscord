"""Cifrado de secretos guardados en la base de datos (tokens OAuth, integraciones)."""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from nexus_core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY no está definida en .env")
    return Fernet(key.encode())


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt(value: bytes) -> str:
    return _fernet().decrypt(value).decode()
