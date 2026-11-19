"""Operaciones de saldo atómicas (SELECT … FOR UPDATE): sin saldos negativos ni dobles cobros."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_core.db.models import EconomyTransaction, MemberWallet


class EconomyError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def wallet_for_update(db: AsyncSession, guild_id: int, user_id: int, *, start_balance: int = 0,
                            user_name: str | None = None) -> MemberWallet:
    await db.execute(insert(MemberWallet).values(guild_id=guild_id, user_id=user_id, balance=start_balance,
                                                 user_name=user_name or "").on_conflict_do_nothing())
    w = await db.scalar(select(MemberWallet).where(MemberWallet.guild_id == guild_id, MemberWallet.user_id == user_id)
                        .with_for_update())
    assert w is not None
    if user_name:
        w.user_name = user_name[:100]
    return w


async def change_balance(db: AsyncSession, guild_id: int, user_id: int, amount: int, kind: str, *,
                         reference: str | None = None, max_balance: int = 1_000_000_000_000, start_balance: int = 0,
                         user_name: str | None = None, clamp: bool = False) -> int:
    """Suma (o resta) ``amount``. Si el saldo quedaría negativo: error, o se ajusta a 0 si ``clamp``."""
    w = await wallet_for_update(db, guild_id, user_id, start_balance=start_balance, user_name=user_name)
    new = w.balance + amount
    if new < 0:
        if not clamp:
            raise EconomyError("insufficient_funds")
        amount, new = -w.balance, 0
    if new > max_balance:
        amount, new = max_balance - w.balance, max_balance
    w.balance = new
    if amount:
        db.add(EconomyTransaction(guild_id=guild_id, user_id=user_id, amount=amount, kind=kind, reference=reference))
    return new


async def transfer(db: AsyncSession, guild_id: int, sender: int, receiver: int, amount: int, *,
                   max_balance: int, sender_name: str | None = None, receiver_name: str | None = None) -> int:
    if amount <= 0:
        raise EconomyError("invalid_amount")
    if sender == receiver:
        raise EconomyError("self_transfer")
    # Bloquear siempre en el mismo orden evita interbloqueos entre dos transferencias cruzadas.
    first, second = sorted((sender, receiver))
    await wallet_for_update(db, guild_id, first)
    await wallet_for_update(db, guild_id, second)
    remaining = await change_balance(db, guild_id, sender, -amount, "transfer_out", reference=str(receiver),
                                     user_name=sender_name)
    rw = await wallet_for_update(db, guild_id, receiver, user_name=receiver_name)
    if rw.balance + amount > max_balance:
        raise EconomyError("receiver_full")
    await change_balance(db, guild_id, receiver, amount, "transfer_in", reference=str(sender), max_balance=max_balance)
    return remaining
