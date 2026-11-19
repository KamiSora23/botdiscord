"""Acceso al panel por roles: nivel por sección, varias secciones a la vez (imágenes) y mapa para el menú."""

from __future__ import annotations

import pytest
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from nexus_core.db.models import DashboardRolePermission, Guild

GID, MOD_ROLE, OTHER_ROLE = 990000000000000901, 555, 666


@pytest.fixture
async def perms(db, monkeypatch):
    import nexus_api.services.guild_data as gd

    async def fake_roles(request, guild_id, user_id):  # el moderador tiene MOD_ROLE
        return [MOD_ROLE] if user_id == 1 else []

    monkeypatch.setattr(gd, "member_role_ids", fake_roles)
    await db.execute(delete(Guild).where(Guild.id == GID))
    await db.execute(insert(Guild).values(id=GID, name="perm-test", owner_id=9))
    db.add_all([
        DashboardRolePermission(guild_id=GID, role_id=MOD_ROLE, module="scheduled_messages", level=2),
        DashboardRolePermission(guild_id=GID, role_id=MOD_ROLE, module="moderation", level=1),
        DashboardRolePermission(guild_id=GID, role_id=OTHER_ROLE, module="*", level=3),
    ])
    await db.commit()
    yield
    await db.execute(delete(Guild).where(Guild.id == GID))
    await db.commit()


async def test_levels_per_section(db, perms) -> None:
    from nexus_api.deps import module_levels, role_level

    assert await module_levels(None, db, GID, 1) == {"scheduled_messages": 2, "moderation": 1}
    assert await module_levels(None, db, GID, 2) == {}  # sin roles con permiso
    assert await role_level(None, db, GID, 1, "scheduled_messages") == 2
    assert await role_level(None, db, GID, 1, "economy") == 0
    # Imágenes: vale el permiso de cualquier sección con editor de mensajes.
    from nexus_core.media import IMAGE_MODULES

    assert await role_level(None, db, GID, 1, IMAGE_MODULES) == 2
    assert await role_level(None, db, GID, 1, ("economy", "levels")) == 0
    # Páginas generales (Overview…): cualquier permiso da lectura.
    assert await role_level(None, db, GID, 1, None) == 1
