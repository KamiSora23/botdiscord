"""Traduce nombres y descripciones de los comandos slash con los textos de nexus_core."""

from __future__ import annotations

import discord
from discord import app_commands

from nexus_core.i18n import has, t

LOCALE_MAP = {
    discord.Locale.spain_spanish: "es",
    discord.Locale.latin_american_spanish: "es",
    discord.Locale.american_english: "en",
    discord.Locale.british_english: "en",
}


def key(k: str) -> app_commands.locale_str:
    """Texto traducible. El valor por defecto (inglés) es el que Discord usa si no hay traducción."""
    return app_commands.locale_str(t("en", k), key=k)


class NexusTranslator(app_commands.Translator):
    async def translate(self, string: app_commands.locale_str, locale: discord.Locale,
                        context: app_commands.TranslationContextTypes) -> str | None:
        lang = LOCALE_MAP.get(locale)
        if lang is None:
            return None
        k = string.extras.get("key")
        if k is None and context.location is app_commands.TranslationContextLocation.parameter_name:
            # Los nombres de las opciones (user, reason…) se traducen con «param.<nombre>».
            k = f"param.{string.message}"
            if not has(lang, k):
                return None
        if k is None:
            return None
        return t(lang, k)
