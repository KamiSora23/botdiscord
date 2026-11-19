"""Nombres y descripciones de los comandos válidos para Discord en ES y EN."""

from __future__ import annotations

import json
import re
from pathlib import Path

from nexus_bot.cogs.utility import HEX_COLOR, MESSAGE_LINK

LOCALES = Path(__file__).resolve().parents[1] / "core" / "nexus_core" / "locales"
NAME = re.compile(r"^[-_\w]{1,32}$")


def _load(lang: str) -> dict[str, str]:
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


def test_command_names_and_descriptions_are_valid():
    es, en = _load("es"), _load("en")
    for data in (es, en):
        for k, v in data.items():
            if (k.startswith("cmd.") and k.endswith(".name")) or k.startswith("sub."):
                assert NAME.match(v) and v == v.lower(), (k, v)
            if k.startswith("cmd.") and k.endswith(".description"):
                assert 1 <= len(v) <= 100, (k, len(v))
            if k.startswith("arg."):
                assert 1 <= len(v) <= 100, (k, len(v))
    cmd_keys = {k for k in es if k.startswith(("cmd.", "arg."))}
    assert cmd_keys == {k for k in en if k.startswith(("cmd.", "arg."))}


def test_top_level_names_are_unique():
    """Dos comandos con el mismo nombre chocarían al registrarse."""
    import nexus_bot.cogs  # noqa: F401  (asegura que el paquete existe)

    base = Path(__file__).resolve().parents[1] / "bot" / "nexus_bot"
    src = "\n".join(p.read_text(encoding="utf-8") for p in [*(base / "cogs").glob("*.py"), base / "groups.py"])
    top = re.findall(r'@app_commands\.command\(name=key\("(cmd\.[a-z_0-9]+)\.name"\)', src)
    top += re.findall(r'Group\(name=key\("(cmd\.[a-z_0-9]+)\.name"\)', src)
    top += re.findall(r'group_name=key\("(cmd\.[a-z_0-9]+)\.name"\)', src)
    for lang in ("es", "en"):
        data = _load(lang)
        names = [data[f"{k}.name"] for k in top]
        dupes = {n for n in names if names.count(n) > 1}
        assert not dupes, (lang, dupes)


def test_message_link_and_color_parsing():
    m = MESSAGE_LINK.search("https://discord.com/channels/1/22/333")
    assert m and m.groups() == ("1", "22", "333")
    assert MESSAGE_LINK.search("https://ptb.discord.com/channels/1/2/3")
    assert not MESSAGE_LINK.search("https://example.com/channels/1/2/3")
    assert HEX_COLOR.match("#7465F7") and HEX_COLOR.match("ff0000")
    assert not HEX_COLOR.match("rojo")


def _all_commands():
    import importlib
    import inspect

    from discord import app_commands
    from discord.ext import commands

    from nexus_bot.client import EXTENSIONS

    out = []

    def walk(c):
        if isinstance(c, app_commands.Group):
            for sub in c.commands:
                walk(sub)
        elif isinstance(c, app_commands.Command):
            out.append(c)

    from nexus_bot import groups

    for ext in EXTENSIONS:
        mod = importlib.import_module(ext)
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if issubclass(cls, commands.Cog) and cls.__module__ == mod.__name__:
                for c in cls.__cog_app_commands__:
                    walk(c)
    for g in groups.ALL:
        walk(g)
    return out


def test_every_option_has_spanish_and_english_name():
    """Ninguna opción de comando puede quedarse en inglés en Discord en español."""
    es, en = _load("es"), _load("en")
    for cmd in _all_commands():
        names_es = []
        for p in cmd.parameters:
            k = f"param.{p.name}"
            assert k in es and k in en, f"/{cmd.qualified_name}: falta {k}"
            assert NAME.match(es[k]) and es[k] == es[k].lower(), es[k]
            names_es.append(es[k])
        assert len(names_es) == len(set(names_es)), f"/{cmd.qualified_name}: nombres repetidos {names_es}"
