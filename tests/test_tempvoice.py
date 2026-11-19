import pytest
from pydantic import ValidationError

from nexus_core.discord.permissions import REQUIRED_PERMISSIONS
from nexus_core.modules import REGISTRY, parse_config
from nexus_core.modules.tempvoice import TempVoiceConfig, room_name


def test_room_name_template():
    assert room_name("Sala de {user}", "Ana") == "Sala de Ana"
    assert room_name("{user}", "x" * 150) == "x" * 100  # Discord: máx. 100 caracteres
    assert room_name("   ", "Ana") == "Ana"


def test_defaults_and_limits():
    assert REGISTRY["tempvoice"].available
    assert parse_config("tempvoice", {}, "en").name_template == "{user}'s room"
    with pytest.raises(ValidationError):
        TempVoiceConfig(default_limit=100)


def test_bot_permissions_listed_for_diagnostics():
    for perm in ("connect", "move_members", "manage_channels"):
        assert "tempvoice" in REQUIRED_PERMISSIONS[perm]


def test_owner_permissions_limited_to_what_bot_has():
    """Discord rechaza la sala entera si se concede un permiso que el bot no tiene."""
    import discord

    from nexus_bot.cogs.tempvoice import OWNER_PERMS, _only_granted

    mine = discord.Permissions(view_channel=True, connect=True, speak=True, manage_channels=True)
    allow, _ = _only_granted(OWNER_PERMS, mine).pair()
    assert allow.connect and allow.manage_channels
    assert not allow.move_members and not allow.mute_members
    full, _ = _only_granted(OWNER_PERMS, discord.Permissions(administrator=True)).pair()
    assert full.move_members
