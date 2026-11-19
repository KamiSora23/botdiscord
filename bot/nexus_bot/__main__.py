"""Arranque del bot: python -m nexus_bot"""

from __future__ import annotations

import asyncio
import logging
import sys

import discord

from nexus_core.config import get_settings
from nexus_core.logsetup import setup_logging

from nexus_bot.client import NexusBot

log = logging.getLogger("nexus.bot")


def main() -> None:
    setup_logging()
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    get_settings().check_production()
    token = get_settings().discord_bot_token
    if not token:
        sys.exit("Falta DISCORD_BOT_TOKEN en .env")

    async def runner(message_content: bool) -> None:
        async with NexusBot(message_content=message_content) as bot:
            await bot.start(token)

    try:
        try:
            asyncio.run(runner(True))
        except discord.PrivilegedIntentsRequired:
            log.warning(
                "Message Content Intent no está activado en el Developer Portal: arranco sin él. "
                "AutoMod y los logs de mensajes no podrán leer el texto hasta que lo actives "
                "(Developer Portal → Bot → Privileged Gateway Intents → Message Content Intent)."
            )
            asyncio.run(runner(False))
    except discord.PrivilegedIntentsRequired:
        sys.exit(
            "Discord rechazó la conexión: activa 'Server Members Intent' en el Developer Portal "
            "→ tu aplicación → Bot → Privileged Gateway Intents."
        )
    except discord.LoginFailure:
        sys.exit("El DISCORD_BOT_TOKEN de .env no es válido. Genera uno nuevo en Bot → Reset Token.")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
