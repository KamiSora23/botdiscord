from nexus_core.db.repo import diff_changes
from nexus_core.discord import permissions as P
from nexus_core.i18n import normalize, t

GUILD = 1000
BOT = 2000
ROLE = 3000


def test_invite_permissions_match_spec():
    assert P.V1_INVITE_PERMISSIONS == 379904
    assert P.INVITE_PERMISSIONS & P.V1_INVITE_PERMISSIONS == P.V1_INVITE_PERMISSIONS


def test_base_permissions_everyone_plus_roles():
    roles = {GUILD: P.VIEW_CHANNEL, ROLE: P.SEND_MESSAGES}
    perms = P.base_permissions(guild_id=GUILD, owner_id=1, member_id=BOT, member_role_ids=[ROLE], roles=roles)
    assert P.has(perms, P.VIEW_CHANNEL | P.SEND_MESSAGES)
    assert not P.has(perms, P.EMBED_LINKS)


def test_administrator_grants_everything():
    perms = P.base_permissions(guild_id=GUILD, owner_id=1, member_id=BOT, member_role_ids=[ROLE],
                               roles={GUILD: 0, ROLE: P.ADMINISTRATOR})
    assert P.has(perms, P.MANAGE_ROLES)


def test_channel_overwrites_order():
    base = P.VIEW_CHANNEL | P.SEND_MESSAGES
    # @everyone niega enviar; el rol del bot lo vuelve a permitir.
    overwrites = [
        {"id": str(GUILD), "type": 0, "allow": "0", "deny": str(P.SEND_MESSAGES)},
        {"id": str(ROLE), "type": 0, "allow": str(P.SEND_MESSAGES), "deny": "0"},
    ]
    perms = P.channel_permissions(base, guild_id=GUILD, member_id=BOT, member_role_ids=[ROLE], overwrites=overwrites)
    assert P.has(perms, P.SEND_MESSAGES)
    # Un overwrite del propio miembro gana a todo.
    overwrites.append({"id": str(BOT), "type": 1, "allow": "0", "deny": str(P.SEND_MESSAGES)})
    perms = P.channel_permissions(base, guild_id=GUILD, member_id=BOT, member_role_ids=[ROLE], overwrites=overwrites)
    assert not P.has(perms, P.SEND_MESSAGES)


def test_no_view_channel_means_nothing():
    overwrites = [{"id": str(GUILD), "type": 0, "allow": "0", "deny": str(P.VIEW_CHANNEL)}]
    perms = P.channel_permissions(P.VIEW_CHANNEL | P.SEND_MESSAGES, guild_id=GUILD, member_id=BOT,
                                  member_role_ids=[], overwrites=overwrites)
    assert perms == 0


def test_can_manage_guild():
    assert P.can_manage_guild(P.MANAGE_GUILD)
    assert P.can_manage_guild(P.ADMINISTRATOR)
    assert P.can_manage_guild(0, is_owner=True)
    assert not P.can_manage_guild(P.SEND_MESSAGES)


def test_diff_changes_flattens_nested_keys():
    old = {"join": {"channel_id": "1", "enabled": True}, "color": 1}
    new = {"join": {"channel_id": "2", "enabled": True}, "color": 1}
    assert diff_changes(old, new) == {"join.channel_id": {"old": "1", "new": "2"}}


def test_i18n_fallbacks():
    assert normalize("es-419") == "es"
    assert normalize("fr") == "en"
    assert t("en", "ping.reply", latency=5).endswith("5 ms")
    assert t("es", "no.such.key") == "no.such.key"


def test_dev_guild_id_accepts_discord_link():
    from nexus_core.config import Settings

    s = Settings(database_url="postgresql://x", dev_guild_id="https://discord.com/channels/1571819134491033610")
    assert s.dev_guild_id == 1571819134491033610
    assert Settings(database_url="postgresql://x", dev_guild_id="").dev_guild_id is None
