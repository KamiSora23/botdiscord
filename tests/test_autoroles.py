"""Autoroles: simula la entrada de un miembro sin necesitar Discord."""

from __future__ import annotations

from types import SimpleNamespace

from nexus_core.discord.permissions import ADMINISTRATOR
from nexus_core.modules.roles import AutorolesConfig

from nexus_bot.cogs.autoroles import Autoroles


class FakeRole:
    def __init__(self, rid: int, position: int, perms: int = 0, managed: bool = False) -> None:
        self.id, self.position, self.managed, self.name = rid, position, managed, f"r{rid}"
        self.permissions = SimpleNamespace(value=perms)

    def __lt__(self, other: "FakeRole") -> bool:
        return self.position < other.position


class FakeMember:
    def __init__(self, guild, *, bot: bool = False, pending: bool = False) -> None:
        self.id, self.guild, self.bot, self.pending = 42, guild, bot, pending
        self.given: list[FakeRole] = []

    async def add_roles(self, *roles, reason=None) -> None:
        self.given.extend(roles)


def make_guild(roles: list[FakeRole]):
    by_id = {r.id: r for r in roles}
    me = SimpleNamespace(top_role=FakeRole(999, 10))
    guild = SimpleNamespace(id=1, me=me, get_role=by_id.get)
    guild.get_member = lambda uid: None
    return guild


def make_cog(cfg: AutorolesConfig | None) -> Autoroles:
    cog = Autoroles.__new__(Autoroles)
    cog._cfg = lambda guild_id: cfg  # type: ignore[method-assign]
    return cog


MORTAL, BOTS, STAFF, HIGH = FakeRole(1, 2), FakeRole(2, 3), FakeRole(3, 4, ADMINISTRATOR), FakeRole(4, 20)


async def test_new_member_gets_human_role():
    guild = make_guild([MORTAL, BOTS])
    member = FakeMember(guild)
    await make_cog(AutorolesConfig(human_role_ids=[1], bot_role_ids=[2])).on_member_join(member)
    assert member.given == [MORTAL]


async def test_bot_gets_bot_role():
    guild = make_guild([MORTAL, BOTS])
    member = FakeMember(guild, bot=True)
    await make_cog(AutorolesConfig(human_role_ids=[1], bot_role_ids=[2])).on_member_join(member)
    assert member.given == [BOTS]


async def test_module_off_gives_nothing():
    member = FakeMember(make_guild([MORTAL]))
    await make_cog(None).on_member_join(member)
    assert member.given == []


async def test_skips_staff_and_too_high_roles():
    guild = make_guild([MORTAL, STAFF, HIGH])
    member = FakeMember(guild)
    await make_cog(AutorolesConfig(human_role_ids=[1, 3, 4])).on_member_join(member)
    assert member.given == [MORTAL]


async def test_waits_for_rules_screening():
    guild = make_guild([MORTAL])
    cfg = AutorolesConfig(human_role_ids=[1], wait_for_screening=True)
    cog = make_cog(cfg)
    before = FakeMember(guild, pending=True)
    await cog.on_member_join(before)
    assert before.given == []  # aún no aceptó las reglas
    after = FakeMember(guild, pending=False)
    await cog.on_member_update(before, after)
    assert after.given == [MORTAL]
