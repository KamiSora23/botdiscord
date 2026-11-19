from nexus_bot.cogs.games import ship_percent, slot_result, ttt_winner


def test_slots_payouts():
    assert slot_result(["💎", "💎", "💎"]) == 10
    assert slot_result(["⭐", "⭐", "⭐"]) == 5
    assert slot_result(["🍒", "🍒", "🍒"]) == 3
    assert slot_result(["🍒", "🍒", "🍋"]) == 1  # recupera la apuesta
    assert slot_result(["🍒", "🍋", "🍇"]) == 0


def test_tictactoe_winner():
    assert ttt_winner([1, 1, 1, 0, 2, 2, 0, 0, 0]) == 1
    assert ttt_winner([2, 1, 0, 2, 1, 0, 2, 0, 1]) == 2
    assert ttt_winner([1, 0, 2, 0, 1, 0, 0, 0, 2]) == 0
    assert ttt_winner([1, 2, 1, 1, 2, 2, 2, 1, 1]) == 3  # tablero lleno sin línea


def test_ship_is_stable_and_symmetric():
    a, b = 111111111111111111, 222222222222222222
    assert ship_percent(a, b) == ship_percent(b, a)
    assert 0 <= ship_percent(a, b) <= 100
