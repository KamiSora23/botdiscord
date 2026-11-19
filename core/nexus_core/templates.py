"""Plantillas de configuración (Quick Setup): activan módulos con valores pensados para cada tipo de comunidad.

Una plantilla nunca sobrescribe una configuración existente salvo que se confirme (``overwrite``).
Los canales los elige el usuario en el asistente; la plantilla solo decide módulos y opciones.
"""

from __future__ import annotations

from typing import Any

from nexus_core.modules import parse_config

# Para cada plantilla: módulo → cambios sobre los valores por defecto.
TEMPLATES: dict[str, dict[str, dict[str, Any]]] = {
    "gaming": {
        "welcome": {}, "moderation": {}, "automod": {}, "antiraid": {"min_account_age_days": 3}, "logging": {},
        "reaction_roles": {}, "levels": {}, "economy": {}, "giveaways": {}, "polls": {"allow_members": True},
    },
    "support": {
        "welcome": {}, "moderation": {"require_reason": True}, "logging": {}, "tickets": {}, "suggestions": {},
    },
    "creator": {
        "welcome": {}, "moderation": {}, "automod": {}, "antiraid": {"min_account_age_days": 3}, "integrations": {},
        "scheduled_messages": {}, "suggestions": {},
        "giveaways": {}, "levels": {},
    },
    "study": {
        "welcome": {}, "reaction_roles": {}, "levels": {"xp_min": 10, "xp_max": 20}, "polls": {"allow_members": True},
        "scheduled_messages": {},
    },
    "professional": {
        "welcome": {}, "moderation": {"require_reason": True}, "automod": {}, "antiraid": {"min_account_age_days": 7},
        "logging": {},
    },
    "minimal": {"welcome": {}, "moderation": {}},
}

# Qué canal del asistente usa cada módulo (y en qué campo de su configuración).
CHANNEL_SLOTS = {
    "welcome": ("welcome", ["join", "channel_id"]),
    "logs": ("logging", None),  # se usa para todas las categorías de logs
    "mod_log": ("moderation", ["log_channel_id"]),
    "suggestions": ("suggestions", ["channel_id"]),
    "levels": ("levels", ["announce_channel_id"]),
}


def _set_path(data: dict[str, Any], path: list[str], value: Any) -> None:
    for key in path[:-1]:
        data = data.setdefault(key, {})
    data[path[-1]] = value


def build_configs(template: str, locale: str, channels: dict[str, str | None]) -> dict[str, dict[str, Any]]:
    """Configuración validada de cada módulo de la plantilla, con los canales elegidos."""
    out: dict[str, dict[str, Any]] = {}
    for module, overrides in TEMPLATES[template].items():
        cfg = parse_config(module, {}, locale).model_dump(mode="json")
        cfg.update(overrides)
        out[module] = cfg
    for slot, channel_id in channels.items():
        if not channel_id or slot not in CHANNEL_SLOTS:
            continue
        module, path = CHANNEL_SLOTS[slot]
        if module not in out:
            continue
        if module == "logging":
            for cat in out[module]["categories"].values():
                cat["channel_id"] = channel_id
        elif path:
            _set_path(out[module], path, channel_id)
            if module == "welcome":
                out[module]["join"]["enabled"] = True
            if module == "levels":
                out[module]["announce"] = "channel"
    # Validar al final (p. ej. welcome exige canal si está activo).
    return {m: parse_config(m, c, locale).model_dump(mode="json") for m, c in out.items()}
