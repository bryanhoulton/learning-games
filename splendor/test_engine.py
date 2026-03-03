"""
Splendor engine tests.

Run with:
    python test_engine.py
"""

from __future__ import annotations

import traceback
from typing import Callable

from cards import CARD_REGISTRY, NOBLE_REGISTRY, TIER_CARD_IDS
from engine import GameEngine
from errors import GameError, InsufficientGems, InvalidAction, NotYourTurn, WrongPhase
from models import GEM_COLORS, GemColor, Phase
from view import get_player_view

# ---------------------------------------------------------------------------
# Tiny test harness
# ---------------------------------------------------------------------------

_passed = _failed = 0


def test(name: str, fn: Callable) -> None:
    global _passed, _failed
    try:
        fn()
        print(f"  PASS  {name}")
        _passed += 1
    except Exception as e:
        print(f"  FAIL  {name}")
        traceback.print_exc()
        _failed += 1


def assert_eq(a, b, msg=""):
    assert a == b, f"{msg}: expected {b!r}, got {a!r}"


def assert_raises(exc_type: type, fn: Callable, msg=""):
    try:
        fn()
        raise AssertionError(f"{msg}: expected {exc_type.__name__} but no exception raised")
    except exc_type:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_2p(seed: int = 1) -> GameEngine:
    return GameEngine.new_game(["Alice", "Bob"], seed=seed)


def _new_4p(seed: int = 1) -> GameEngine:
    return GameEngine.new_game(["Alice", "Bob", "Carol", "Dave"], seed=seed)


def _give_gems(engine: GameEngine, player_name: str, gems: dict) -> None:
    """Force gems onto a player (bypasses supply) for test setup."""
    p = next(p for p in engine.state.players if p.name == player_name)
    for color, amount in gems.items():
        p.gems[color] = p.gems.get(color, 0) + amount


def _drain_supply(engine: GameEngine, color: GemColor, leave: int = 0) -> None:
    """Remove gems from supply down to *leave* tokens."""
    s = engine.state
    s.gem_supply[color] = max(leave, 0)


def _give_purchased(engine: GameEngine, player_name: str, card_id: int) -> None:
    """Force a purchased card onto a player (skips payment) for test setup."""
    p = next(p for p in engine.state.players if p.name == player_name)
    p.purchased.append(card_id)


def _force_to_board(engine: GameEngine, card_id: int, tier: int, slot: int = 0) -> None:
    """Place a specific card face-up on the board (moves existing occupant to deck)."""
    s = engine.state
    displaced = s.board[tier][slot]
    if displaced is not None and displaced != card_id:
        s.decks[tier].insert(0, displaced)
    if card_id in s.decks[tier]:
        s.decks[tier].remove(card_id)
    s.board[tier][slot] = card_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_game_creation():
    engine = _new_2p()
    s = engine.state
    assert_eq(len(s.players), 2)
    assert_eq(s.phase, Phase.PLAYER_TURN)
    assert_eq(s.current_player_index, 0)

    # 2-player: 4 of each gem, 5 gold
    for color in GEM_COLORS:
        assert_eq(s.gem_supply[color], 4, f"{color.value} supply")
    assert_eq(s.gem_supply[GemColor.GOLD], 5)

    # 4 face-up cards per tier
    for tier in (1, 2, 3):
        face_up = [c for c in s.board[tier] if c is not None]
        assert_eq(len(face_up), 4, f"tier {tier} face-up count")

    # Nobles: num_players + 1 = 3
    assert_eq(len(s.nobles), 3)

    # All players start with 0 gems
    for p in s.players:
        assert all(v == 0 for v in p.gems.values()), f"{p.name} should start with no gems"


def test_take_different_gems_3():
    engine = _new_2p()
    colors = [GemColor.RUBY, GemColor.SAPPHIRE, GemColor.EMERALD]
    events = engine.take_different_gems("Alice", colors)

    p = engine.state.players[0]
    assert_eq(p.gems[GemColor.RUBY], 1)
    assert_eq(p.gems[GemColor.SAPPHIRE], 1)
    assert_eq(p.gems[GemColor.EMERALD], 1)
    assert_eq(engine.state.gem_supply[GemColor.RUBY], 3)
    # Turn should advance to Bob
    assert_eq(engine.state.current_player.name, "Bob")


def test_take_different_gems_2():
    engine = _new_2p()
    # Drain all but 2 colors to have only 2 available
    _drain_supply(engine, GemColor.EMERALD, 0)
    _drain_supply(engine, GemColor.RUBY, 0)
    _drain_supply(engine, GemColor.ONYX, 0)
    events = engine.take_different_gems("Alice", [GemColor.DIAMOND, GemColor.SAPPHIRE])
    p = engine.state.players[0]
    assert_eq(p.gems[GemColor.DIAMOND], 1)
    assert_eq(p.gems[GemColor.SAPPHIRE], 1)


def test_take_different_gems_wrong_player():
    engine = _new_2p()
    assert_raises(
        NotYourTurn,
        lambda: engine.take_different_gems("Bob", [GemColor.RUBY, GemColor.SAPPHIRE, GemColor.EMERALD]),
    )


def test_take_different_gems_duplicate_color():
    engine = _new_2p()
    assert_raises(
        InvalidAction,
        lambda: engine.take_different_gems("Alice", [GemColor.RUBY, GemColor.RUBY, GemColor.EMERALD]),
    )


def test_take_different_gems_gold_forbidden():
    engine = _new_2p()
    assert_raises(
        InvalidAction,
        lambda: engine.take_different_gems("Alice", [GemColor.GOLD, GemColor.RUBY, GemColor.EMERALD]),
    )


def test_take_double_gem():
    engine = _new_2p(seed=2)
    # 2-player has 4 of each — NOT enough for double (need ≥4)
    # Supply is exactly 4, which IS 4 so it should work
    events = engine.take_double_gem("Alice", GemColor.RUBY)
    p = engine.state.players[0]
    assert_eq(p.gems[GemColor.RUBY], 2)
    assert_eq(engine.state.gem_supply[GemColor.RUBY], 2)


def test_take_double_gem_insufficient():
    engine = _new_2p()
    _drain_supply(engine, GemColor.RUBY, 3)  # leave only 3
    assert_raises(
        InsufficientGems,
        lambda: engine.take_double_gem("Alice", GemColor.RUBY),
    )


def test_reserve_board_card():
    engine = _new_2p()
    s = engine.state
    # Find a face-up tier-1 card
    card_id = next(c for c in s.board[1] if c is not None)
    gold_before = s.gem_supply[GemColor.GOLD]

    engine.reserve_board_card("Alice", card_id)

    p = engine.state.players[0]
    assert card_id in p.reserved
    # Gold given if available
    assert_eq(p.gems[GemColor.GOLD], 1)
    assert_eq(s.gem_supply[GemColor.GOLD], gold_before - 1)
    # Board slot refilled (deck is non-empty)
    face_up = [c for c in s.board[1] if c is not None]
    assert_eq(len(face_up), 4)


def test_reserve_board_card_not_on_board():
    engine = _new_2p()
    assert_raises(
        Exception,
        lambda: engine.reserve_board_card("Alice", 9999),
    )


def test_reserve_max_3():
    engine = _new_2p()
    s = engine.state
    # Reserve 3 cards alternating between players (so Alice gets 3)
    for _ in range(3):
        card_id = next(c for c in s.board[1] if c is not None)
        engine.reserve_board_card("Alice", card_id)
        engine.take_different_gems("Bob", [GemColor.RUBY, GemColor.SAPPHIRE, GemColor.EMERALD])
    # 4th reserve should fail
    card_id = next(c for c in s.board[1] if c is not None)
    assert_raises(
        InvalidAction,
        lambda: engine.reserve_board_card("Alice", card_id),
    )


def test_reserve_deck_top():
    engine = _new_2p()
    s = engine.state
    deck_size_before = len(s.decks[2])
    engine.reserve_deck_top("Alice", 2)
    p = engine.state.players[0]
    assert_eq(len(p.reserved), 1)
    assert_eq(len(s.decks[2]), deck_size_before - 1)
    assert_eq(p.gems[GemColor.GOLD], 1)


def test_buy_board_card_with_gems():
    engine = _new_2p()
    s = engine.state
    # Card 22: emerald bonus, cost {diamond:3} — force onto board for test
    card_id = 22
    _force_to_board(engine, card_id, tier=1, slot=0)
    _give_gems(engine, "Alice", {GemColor.DIAMOND: 3})

    engine.buy_card("Alice", card_id)
    p = engine.state.players[0]
    assert card_id in p.purchased
    assert card_id not in [c for row in s.board.values() for c in row]
    assert_eq(p.gems[GemColor.DIAMOND], 0)
    assert_eq(s.gem_supply[GemColor.DIAMOND], 4 + 3)  # returned to supply


def test_buy_card_with_bonuses():
    engine = _new_2p()
    # Card 22: costs {diamond:3} — force onto board, give 3 diamond bonuses
    card_id = 22
    _force_to_board(engine, card_id, tier=1, slot=0)
    _give_purchased(engine, "Alice", 9)   # diamond bonus
    _give_purchased(engine, "Alice", 10)  # diamond bonus
    _give_purchased(engine, "Alice", 14)  # diamond bonus
    # 3 diamond bonuses cover the full cost — buy for free
    engine.buy_card("Alice", card_id)
    p = engine.state.players[0]
    assert card_id in p.purchased
    assert_eq(p.gems[GemColor.DIAMOND], 0)


def test_buy_card_with_gold():
    engine = _new_2p()
    # Card 22: costs {diamond:3}. Alice has 1 diamond + 2 gold.
    card_id = 22
    _force_to_board(engine, card_id, tier=1, slot=0)
    _give_gems(engine, "Alice", {GemColor.DIAMOND: 1, GemColor.GOLD: 2})
    engine.buy_card("Alice", card_id)
    p = engine.state.players[0]
    assert card_id in p.purchased
    assert_eq(p.gems[GemColor.GOLD], 0)
    assert_eq(p.gems[GemColor.DIAMOND], 0)


def test_buy_card_insufficient_gems():
    engine = _new_2p()
    # Card 22 costs 3 diamond; Alice has 0
    card_id = 22
    _force_to_board(engine, card_id, tier=1, slot=0)
    assert_raises(
        InsufficientGems,
        lambda: engine.buy_card("Alice", card_id),
    )


def test_buy_reserved_card():
    engine = _new_2p()
    s = engine.state
    card_id = next(c for c in s.board[1] if c is not None)
    engine.reserve_board_card("Alice", card_id)
    engine.take_different_gems("Bob", [GemColor.RUBY, GemColor.SAPPHIRE, GemColor.EMERALD])

    card = CARD_REGISTRY[card_id]
    # Give Alice exactly the gems needed
    _give_gems(engine, "Alice", card.cost)
    engine.buy_card("Alice", card_id)

    p = engine.state.players[0]
    assert card_id in p.purchased
    assert card_id not in p.reserved


def test_gem_overflow_discard():
    engine = _new_2p()
    # Give Alice 9 gems, then let her take 3 more (total 12 → must discard 2)
    _give_gems(engine, "Alice", {GemColor.DIAMOND: 3, GemColor.SAPPHIRE: 3, GemColor.EMERALD: 3})
    engine.take_different_gems("Alice", [GemColor.RUBY, GemColor.ONYX, GemColor.DIAMOND])

    s = engine.state
    assert_eq(s.phase, Phase.AWAITING_DISCARD)
    assert_eq(s.current_player.name, "Alice")

    # Resolve: discard 2 gems
    engine.discard_gems("Alice", {GemColor.DIAMOND: 2})
    assert_eq(s.phase, Phase.PLAYER_TURN)
    assert_eq(s.current_player.name, "Bob")

    p = s.players[0]
    total = sum(v for v in p.gems.values())
    assert total <= 10


def test_gem_overflow_discard_wrong_phase():
    engine = _new_2p()
    assert_raises(
        WrongPhase,
        lambda: engine.discard_gems("Alice", {GemColor.RUBY: 1}),
    )


def test_noble_auto_awarded():
    engine = _new_2p()
    s = engine.state
    # Pick a noble and satisfy its requirements
    noble_id = s.nobles[0]
    noble = NOBLE_REGISTRY[noble_id]

    # Give Alice purchased cards to meet the requirements
    # Each requirement is count of cards with that bonus color
    from cards import CARD_REGISTRY
    for color, count in noble.requirements.items():
        # Find cards with this bonus color
        eligible = [cid for cid, c in CARD_REGISTRY.items() if c.bonus_color == color]
        for i in range(count):
            _give_purchased(engine, "Alice", eligible[i])

    # Take a dummy action to trigger noble check
    # First drain gems from supply so Alice can take some
    engine.take_different_gems("Alice", [GemColor.RUBY, GemColor.SAPPHIRE, GemColor.EMERALD])

    # After the action the noble should have been awarded
    alice = s.players[0]
    assert noble_id in alice.nobles, f"Noble {noble_id} should have been awarded"
    assert noble_id not in s.nobles


def test_noble_choice_multiple():
    engine = _new_2p()
    s = engine.state

    # Ensure at least 2 nobles on the board
    # Manually satisfy requirements for multiple nobles
    noble1 = NOBLE_REGISTRY[s.nobles[0]]
    noble2 = NOBLE_REGISTRY[s.nobles[1]]

    from cards import CARD_REGISTRY
    # Satisfy noble1
    for color, count in noble1.requirements.items():
        eligible = [cid for cid, c in CARD_REGISTRY.items() if c.bonus_color == color]
        for i in range(count):
            _give_purchased(engine, "Alice", eligible[i])
    # Satisfy noble2 (may overlap)
    for color, count in noble2.requirements.items():
        eligible = [cid for cid, c in CARD_REGISTRY.items() if c.bonus_color == color]
        alice = s.players[0]
        have = sum(1 for cid in alice.purchased if CARD_REGISTRY[cid].bonus_color == color)
        for i in range(have, count):
            _give_purchased(engine, "Alice", eligible[i])

    # Trigger by taking gems
    engine.take_different_gems("Alice", [GemColor.RUBY, GemColor.SAPPHIRE, GemColor.EMERALD])

    # If multiple nobles qualify, we should be in AWAITING_NOBLE_CHOICE
    # OR one was auto-awarded (depends on how many qualify)
    # Either way the state is consistent
    alice = s.players[0]
    if s.phase == Phase.AWAITING_NOBLE_CHOICE:
        noble_id = s.pending_noble_choices[0]
        engine.choose_noble("Alice", noble_id)
        assert len(alice.nobles) >= 1
    else:
        # Auto-awarded
        assert len(alice.nobles) >= 1


def test_wrong_phase_buy():
    engine = _new_2p()
    s = engine.state
    # Put engine in AWAITING_DISCARD
    _give_gems(engine, "Alice", {
        GemColor.DIAMOND: 3, GemColor.SAPPHIRE: 3, GemColor.EMERALD: 3
    })
    engine.take_different_gems("Alice", [GemColor.RUBY, GemColor.ONYX, GemColor.DIAMOND])
    assert_eq(s.phase, Phase.AWAITING_DISCARD)
    assert_raises(
        WrongPhase,
        lambda: engine.buy_card("Alice", 22),
    )


def test_view_hides_deck_contents():
    engine = _new_2p()
    view = get_player_view(engine.state, "Alice")

    # Deck sizes are visible
    for tier in (1, 2, 3):
        assert tier in view.deck_sizes
        assert view.deck_sizes[tier] >= 0

    # But deck contents are not in the view
    assert not hasattr(view, "decks")


def test_view_shows_opponent_info():
    engine = _new_2p()
    engine.take_different_gems("Alice", [GemColor.RUBY, GemColor.SAPPHIRE, GemColor.EMERALD])
    view = get_player_view(engine.state, "Bob")

    assert_eq(len(view.others), 1)
    alice_view = view.others[0]
    assert_eq(alice_view.name, "Alice")
    assert_eq(alice_view.gems[GemColor.RUBY], 1)


def test_final_round_and_game_over():
    engine = _new_2p(seed=5)
    s = engine.state

    # Force Alice to 15 VP by giving her high-VP cards
    # Tier-3 cards have 3-5 VP; give enough to hit 15
    from cards import CARD_REGISTRY
    high_vp = sorted(
        [c for c in CARD_REGISTRY.values() if c.vp >= 3],
        key=lambda c: -c.vp
    )
    total = 0
    for card in high_vp:
        if total >= 15:
            break
        _give_purchased(engine, "Alice", card.id)
        total += card.vp

    # Alice takes a normal action to trigger turn-end VP check
    engine.take_different_gems("Alice", [GemColor.RUBY, GemColor.SAPPHIRE, GemColor.EMERALD])
    # If Alice qualifies for a noble, handle that
    if s.phase == Phase.AWAITING_NOBLE_CHOICE:
        engine.choose_noble("Alice", s.pending_noble_choices[0])

    # Final round should be set
    assert s.final_round, "final_round should be True after Alice hits 15 VP"

    # Bob now plays — after Bob's turn with 2 players game should end
    if not s.is_game_over:
        engine.take_different_gems("Bob", [GemColor.RUBY, GemColor.SAPPHIRE, GemColor.EMERALD])
        if s.phase == Phase.AWAITING_NOBLE_CHOICE:
            engine.choose_noble("Bob", s.pending_noble_choices[0])

    assert s.is_game_over, "Game should be over after final round completes"
    assert_eq(s.phase, Phase.GAME_OVER)


def test_4_player_gem_supply():
    engine = _new_4p()
    s = engine.state
    for color in GEM_COLORS:
        assert_eq(s.gem_supply[color], 7, f"4-player {color.value} supply should be 7")
    # 5 nobles for 4 players
    assert_eq(len(s.nobles), 5)


def test_random_game_completes():
    """A full random game should complete without errors."""
    from agent import RandomAgent
    from runner import run_game
    run_game(
        {"Alice": RandomAgent(), "Bob": RandomAgent()},
        seed=42,
        verbose=False,
    )


def test_random_4p_game_completes():
    from agent import RandomAgent
    from runner import run_game
    run_game(
        {
            "Alice": RandomAgent(),
            "Bob": RandomAgent(),
            "Carol": RandomAgent(),
            "Dave": RandomAgent(),
        },
        seed=99,
        verbose=False,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Running Splendor engine tests...\n")

    test("game creation (2p)",                  test_game_creation)
    test("take 3 different gems",               test_take_different_gems_3)
    test("take 2 different gems",               test_take_different_gems_2)
    test("take gems — wrong player",            test_take_different_gems_wrong_player)
    test("take gems — duplicate color",         test_take_different_gems_duplicate_color)
    test("take gems — gold forbidden",          test_take_different_gems_gold_forbidden)
    test("take double gem",                     test_take_double_gem)
    test("take double gem — insufficient",      test_take_double_gem_insufficient)
    test("reserve board card",                  test_reserve_board_card)
    test("reserve board card — not on board",   test_reserve_board_card_not_on_board)
    test("reserve max 3",                       test_reserve_max_3)
    test("reserve deck top",                    test_reserve_deck_top)
    test("buy board card with gems",            test_buy_board_card_with_gems)
    test("buy card — bonuses reduce cost",      test_buy_card_with_bonuses)
    test("buy card — gold as wildcard",         test_buy_card_with_gold)
    test("buy card — insufficient gems",        test_buy_card_insufficient_gems)
    test("buy reserved card",                   test_buy_reserved_card)
    test("gem overflow → discard",              test_gem_overflow_discard)
    test("discard — wrong phase",               test_gem_overflow_discard_wrong_phase)
    test("noble auto-awarded",                  test_noble_auto_awarded)
    test("noble choice (multiple)",             test_noble_choice_multiple)
    test("wrong phase — buy during discard",    test_wrong_phase_buy)
    test("view hides deck contents",            test_view_hides_deck_contents)
    test("view shows opponent gems",            test_view_shows_opponent_info)
    test("final round + game over",             test_final_round_and_game_over)
    test("4-player gem supply",                 test_4_player_gem_supply)
    test("random 2p game completes",            test_random_game_completes)
    test("random 4p game completes",            test_random_4p_game_completes)

    print(f"\n{'='*40}")
    print(f"Results: {_passed} passed, {_failed} failed")
    if _failed:
        raise SystemExit(1)
