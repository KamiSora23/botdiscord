"""La API y el bot no arrancan en producción con una configuración incompleta o insegura."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from nexus_core.config import Settings

GOOD = dict(env="production", database_url="postgresql://nexus:s3cret@postgres:5432/nexus",
            discord_client_id="1", discord_client_secret="x", discord_bot_token="t",
            encryption_key=Fernet.generate_key().decode(), dashboard_url="https://nexus.example.com",
            discord_redirect_uri="https://nexus.example.com/api/v1/auth/callback", dev_guild_id=None)


def make(**kw) -> Settings:
    return Settings(_env_file=None, **{**GOOD, **kw})


def test_valid_production_config_passes() -> None:
    assert make().production_problems() == []
    make().check_production()


def test_development_is_never_blocked() -> None:
    assert make(env="development", discord_bot_token="", dashboard_url="http://localhost:3000").production_problems() == []


@pytest.mark.parametrize(("kw", "needle"), [
    ({"discord_bot_token": ""}, "DISCORD_BOT_TOKEN"),
    ({"encryption_key": ""}, "ENCRYPTION_KEY"),
    ({"encryption_key": "no-es-fernet"}, "Fernet"),
    ({"dev_guild_id": 123}, "DEV_GUILD_ID"),
    ({"dashboard_url": "http://nexus.example.com"}, "DASHBOARD_URL"),
    ({"discord_redirect_uri": "http://localhost:3000/api/v1/auth/callback"}, "DISCORD_REDIRECT_URI"),
    ({"database_url": "postgresql://nexus:CAMBIAR@postgres:5432/nexus"}, "DATABASE_URL"),
])
def test_bad_production_config_is_reported(kw, needle) -> None:
    s = make(**kw)
    assert any(needle in p for p in s.production_problems())
    with pytest.raises(SystemExit, match=needle):
        s.check_production()
