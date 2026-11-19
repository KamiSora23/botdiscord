"""Bits de permisos de Discord y cálculo de permisos efectivos en un canal."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

CREATE_INSTANT_INVITE = 1 << 0
KICK_MEMBERS = 1 << 1
BAN_MEMBERS = 1 << 2
ADMINISTRATOR = 1 << 3
MANAGE_CHANNELS = 1 << 4
MANAGE_GUILD = 1 << 5
ADD_REACTIONS = 1 << 6
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
MANAGE_MESSAGES = 1 << 13
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
READ_MESSAGE_HISTORY = 1 << 16
USE_EXTERNAL_EMOJIS = 1 << 18
MANAGE_ROLES = 1 << 28
MODERATE_MEMBERS = 1 << 40
MENTION_EVERYONE = 1 << 17
MANAGE_WEBHOOKS = 1 << 29

# Un rol con alguno de estos permisos nunca se reparte solo (paneles de roles, autoroles):
# cualquiera podría hacerse administrador o moderador pulsando un botón.
DANGEROUS_PERMISSIONS = (
    ADMINISTRATOR | MANAGE_GUILD | MANAGE_ROLES | MANAGE_CHANNELS | KICK_MEMBERS | BAN_MEMBERS
    | MODERATE_MEMBERS | MANAGE_MESSAGES | MANAGE_WEBHOOKS | MENTION_EVERYONE
)


def is_dangerous(perms: int) -> bool:
    return bool(perms & DANGEROUS_PERMISSIONS)

ALL = (1 << 53) - 1

NAMES: dict[str, int] = {
    "view_channel": VIEW_CHANNEL,
    "send_messages": SEND_MESSAGES,
    "embed_links": EMBED_LINKS,
    "attach_files": ATTACH_FILES,
    "read_message_history": READ_MESSAGE_HISTORY,
    "use_external_emojis": USE_EXTERNAL_EMOJIS,
    "manage_roles": MANAGE_ROLES,
    "manage_messages": MANAGE_MESSAGES,
    "moderate_members": MODERATE_MEMBERS,
    "kick_members": KICK_MEMBERS,
    "ban_members": BAN_MEMBERS,
    "add_reactions": ADD_REACTIONS,
    "manage_channels": MANAGE_CHANNELS,
    "create_public_threads": 1 << 35,
    "connect": 1 << 20,
    "move_members": 1 << 24,
}

# Permisos que pide la invitación en la V1 (docs/NEXUS_API_SPEC.md §4.4).
V1_INVITE_PERMISSIONS = (
    VIEW_CHANNEL
    | SEND_MESSAGES
    | EMBED_LINKS
    | ATTACH_FILES
    | READ_MESSAGE_HISTORY
    | USE_EXTERNAL_EMOJIS
)

# Qué módulo necesita cada permiso a nivel de servidor. Crece con cada fase.
REQUIRED_PERMISSIONS: dict[str, list[str]] = {
    "view_channel": ["core"],
    "send_messages": ["core", "welcome"],
    "embed_links": ["core", "welcome"],
    "attach_files": ["welcome"],
    "read_message_history": ["core"],
    "use_external_emojis": ["welcome"],
    "manage_messages": ["automod", "moderation", "honeypot"],
    "moderate_members": ["moderation", "automod"],
    "kick_members": ["moderation"],
    "ban_members": ["moderation"],
    "manage_roles": ["autoroles", "reaction_roles", "moderation"],
    "add_reactions": ["reaction_roles", "suggestions"],
    "manage_channels": ["tickets", "moderation", "tempvoice"],
    "create_public_threads": ["suggestions"],
    "connect": ["tempvoice"],
    "move_members": ["tempvoice"],
}

# Invitación actual: todos los permisos que usan los módulos disponibles.
INVITE_PERMISSIONS = 0
for _name in REQUIRED_PERMISSIONS:
    INVITE_PERMISSIONS |= NAMES[_name]


def has(perms: int, flag: int) -> bool:
    return bool(perms & ADMINISTRATOR) or (perms & flag) == flag


def can_manage_guild(perms: int, *, is_owner: bool = False) -> bool:
    return is_owner or bool(perms & ADMINISTRATOR) or bool(perms & MANAGE_GUILD)


def base_permissions(
    *, guild_id: int, owner_id: int, member_id: int, member_role_ids: Iterable[int],
    roles: Mapping[int, int],
) -> int:
    """Permisos del miembro en el servidor. ``roles``: {role_id: permisos}."""
    if member_id == owner_id:
        return ALL
    perms = roles.get(guild_id, 0)  # @everyone tiene el mismo ID que el servidor
    for role_id in member_role_ids:
        perms |= roles.get(role_id, 0)
    if perms & ADMINISTRATOR:
        return ALL
    return perms


def channel_permissions(
    base: int, *, guild_id: int, member_id: int, member_role_ids: Iterable[int],
    overwrites: Iterable[Mapping[str, Any]],
) -> int:
    """Aplica los overwrites del canal: @everyone → roles → miembro."""
    if base & ADMINISTRATOR or base == ALL:
        return ALL
    role_ids = set(member_role_ids)
    ow = {int(o["id"]): o for o in overwrites}
    perms = base
    everyone = ow.get(guild_id)
    if everyone:
        perms &= ~int(everyone["deny"])
        perms |= int(everyone["allow"])
    allow = deny = 0
    for oid, o in ow.items():
        if int(o.get("type", 0)) == 0 and oid in role_ids:
            allow |= int(o["allow"])
            deny |= int(o["deny"])
    perms &= ~deny
    perms |= allow
    member = ow.get(member_id)
    if member and int(member.get("type", 0)) == 1:
        perms &= ~int(member["deny"])
        perms |= int(member["allow"])
    if not perms & VIEW_CHANNEL:
        return 0
    return perms


def invite_url(client_id: str, guild_id: int | str | None = None,
               permissions: int | None = None) -> str:
    permissions = INVITE_PERMISSIONS if permissions is None else permissions
    url = (
        "https://discord.com/oauth2/authorize"
        f"?client_id={client_id}&scope=bot%20applications.commands&permissions={permissions}"
    )
    if guild_id is not None:
        url += f"&guild_id={guild_id}&disable_guild_select=true"
    return url
