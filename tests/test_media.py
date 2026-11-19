"""Imágenes subidas para embeds: media:// en plantillas, detección de tipo y adjuntos al enviar."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from nexus_core import media as M
from nexus_core.messages.template import Embed

MID = "a" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def test_template_accepts_media_urls() -> None:
    e = Embed(title="x", image_url=f"media://{MID}", thumbnail_url=f"media://{MID}")
    assert e.image_url == f"media://{MID}"
    with pytest.raises(ValidationError):
        Embed(title="x", image_url="media://nope")
    with pytest.raises(ValidationError):
        Embed(title="x", image_url="http://inseguro.com/a.png")


def test_sniff_by_magic_bytes() -> None:
    assert M.sniff(PNG) == "image/png"
    assert M.sniff(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert M.sniff(b"GIF89a....") == "image/gif"
    assert M.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert M.sniff(b"<svg xmlns=...>") is None  # SVG y demás: rechazados
    assert M.sniff(b"MZ\x90\x00") is None


def test_referenced_and_attach() -> None:
    other = "b" * 32
    payload = {"embeds": [{"title": "t", "image": {"url": f"media://{MID}"}, "thumbnail": {"url": f"media://{other}"},
                           "footer": {"text": "f", "icon_url": f"media://{MID}"}, "author": {"icon_url": "https://x/a.png"}}]}
    assert M.referenced(payload) == [MID, other]
    M.attach(payload, {MID: f"{MID}.png"})  # la otra imagen ya no existe
    e = payload["embeds"][0]
    assert e["image"]["url"] == f"attachment://{MID}.png"
    assert e["footer"]["icon_url"] == f"attachment://{MID}.png"
    assert "thumbnail" not in e  # borrada: se quita en vez de enviar un enlace roto
    assert "author" not in e  # autor sin nombre no se envía


def test_rest_kwargs_multipart() -> None:
    payload = {"embeds": [{"title": "t", "image": {"url": f"media://{MID}"}}]}
    kw = M.rest_kwargs(payload, [M.Loaded(MID, f"{MID}.png", "image/png", PNG)])
    body = json.loads(kw["data"]["payload_json"])
    assert body["attachments"] == [{"id": 0, "filename": f"{MID}.png"}]
    assert body["embeds"][0]["image"]["url"] == f"attachment://{MID}.png"
    assert kw["files"][0][0] == "files[0]"
    plain = M.rest_kwargs({"content": "hola"}, [])
    assert plain == {"json": {"content": "hola"}}


def test_render_keeps_media_only_for_images() -> None:
    from nexus_core.messages import MessageTemplate, render_payload
    from tests.test_messages import ctx

    tmpl = MessageTemplate(embeds=[Embed(title="t", url=f"media://{MID}", image_url=f"media://{MID}")])
    p = render_payload(tmpl, ctx(), 0)
    assert p["embeds"][0]["image"]["url"] == f"media://{MID}"
    assert "url" not in p["embeds"][0]  # el enlace del título no puede ser una imagen subida


async def test_usage_and_cleanup(db) -> None:
    from datetime import timedelta

    from sqlalchemy import delete, select
    from sqlalchemy.dialects.postgresql import insert

    from nexus_core.db.models import CustomCommand, Guild, Media, ModuleConfig
    from nexus_core.db.repo import utcnow

    gid = 990000000000000777
    await db.execute(delete(Guild).where(Guild.id == gid))
    await db.execute(insert(Guild).values(id=gid, name="media-test", owner_id=1))
    used_w, used_c, old_unused, new_unused = (c * 32 for c in "1234")
    old = utcnow() - timedelta(days=10)
    for mid, when in ((used_w, old), (used_c, old), (old_unused, old), (new_unused, utcnow())):
        db.add(Media(id=mid, guild_id=gid, filename=f"{mid[:4]}.png", content_type="image/png", size=10,
                     data=PNG, created_at=when))
    db.add(ModuleConfig(guild_id=gid, module="welcome", enabled=True,
                        config={"join": {"message": {"embeds": [{"image_url": f"media://{used_w}"}]}}}))
    db.add(CustomCommand(guild_id=gid, name="info", description="Info", response={"embeds": [{"thumbnail_url": f"media://{used_c}"}]}))
    await db.commit()

    used = await M.usage(db, gid)
    assert used == {used_w: [{"type": "module_configs", "name": "welcome"}],
                    used_c: [{"type": "custom_commands", "name": "info"}]}
    # Automática: solo las sin usar con más de 7 días.
    assert await M.cleanup_unused(db, gid) == 1
    left = set((await db.scalars(select(Media.id).where(Media.guild_id == gid))).all())
    assert left == {used_w, used_c, new_unused}
    # Desde el panel («Borrar las no usadas»): todas las sin usar.
    assert await M.cleanup_unused(db, gid, older_than_days=None) == 1
    await db.execute(delete(Guild).where(Guild.id == gid))
    await db.commit()


def test_place_one_off() -> None:
    ph = M.ONE_OFF_PLACEHOLDER + "x.png"
    payload = {"embeds": [{"image": {"url": ph}, "thumbnail": {"url": ph}, "footer": {"text": "f", "icon_url": ph}}]}
    M.place_one_off(payload, {"image_url": "a.png"})
    e = payload["embeds"][0]
    assert e["image"] == {"url": "attachment://a.png"}
    assert "thumbnail" not in e and "icon_url" not in e["footer"]  # marcador sin archivo: fuera
    kw = M.rest_kwargs(payload, [], [M.Loaded("a", "a.png", "image/png", PNG)])
    assert json.loads(kw["data"]["payload_json"])["attachments"] == [{"id": 0, "filename": "a.png"}]


async def test_store_validates_and_events_count_as_use(db) -> None:
    from sqlalchemy import delete
    from sqlalchemy.dialects.postgresql import insert

    from nexus_core.db.models import Event, Guild
    from nexus_core.db.repo import utcnow
    from nexus_core.modules.events import EventIn

    gid = 990000000000000778
    await db.execute(delete(Guild).where(Guild.id == gid))
    await db.execute(insert(Guild).values(id=gid, name="media-test-2", owner_id=1))
    with pytest.raises(M.MediaError, match="image_type"):
        await M.store(db, gid, "x.svg", b"<svg/>", None)
    row = await M.store(db, gid, "C:\\fotos\\cartel.png", PNG, 5)
    assert row.filename == "cartel.png" and row.content_type == "image/png"
    url = f"media://{row.id}"
    assert EventIn(title="t", starts_at=utcnow().replace(year=2099), channel_id=1, image_url=url).image_url == url
    db.add(Event(guild_id=gid, title="Torneo", description="", starts_at=utcnow(), channel_id=1, image_url=url,
                 created_by=5))
    await db.commit()
    assert (await M.usage(db, gid))[row.id] == [{"type": "events", "name": "Torneo"}]
    assert await M.attachment_name(db, gid, url) == f"{row.id}.png"
    await db.execute(delete(Guild).where(Guild.id == gid))
    await db.commit()
