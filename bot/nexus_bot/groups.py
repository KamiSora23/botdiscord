"""Grupos de comandos compartidos entre varios cogs (/info …, /juego …).

Discord permite como máximo 100 comandos «/» por aplicación: agrupar los comandos ligeros deja sitio
para los módulos nuevos. Cada cog añade sus subcomandos con ``@groups.info.command(...)`` y los enlaza
a sí mismo con :func:`bind` (los subcomandos de un grupo externo no se enlazan solos).
"""

from __future__ import annotations

from typing import Any

from discord import app_commands
from discord.ext import commands

from nexus_bot.translator import key

info = app_commands.Group(name=key("cmd.info.name"), description=key("cmd.info.description"), guild_only=True)
fun = app_commands.Group(name=key("cmd.fun.name"), description=key("cmd.fun.description"), guild_only=True)

ALL = (info, fun)


def bind(cog: commands.Cog, *cmds: Any) -> None:
    """Enlaza al cog los subcomandos que declaró en un grupo compartido."""
    for cmd in cmds:
        cmd.binding = cog
