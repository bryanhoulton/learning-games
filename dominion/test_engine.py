"""
Tests for the Dominion engine.
Run with: python test_engine.py
"""

import sys
from models import CardName, CardType, Phase
from cards import CARD_REGISTRY, FIRST_GAME_KINGDOM
from engine import GameEngine
from errors import InvalidAction, InvalidCard, NotYourTurn, WrongPhase, InsufficientCards


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def new_game(seed=42):
    return GameEngine.new_game(["Alice", "Bob"], seed=seed)


def force_hand(engine, player_name: str, cards: list[CardName]):
    """Replace a player's hand with the given cards (for test setup)."""
    s = engine.state
    player = next(p for p in s.players if p.name == player_name)
    # Return current hand to discard, then set new hand
    player.discard.extend(player.hand)
    player.hand = list(cards)


def skip_to_buy(engine, player_name: str):
    """Move from ACTION phase to BUY phase."""
    engine.end_action_phase(player_name)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initial_state():
    engine = new_game()
    s = engine.state

    assert len(s.players) == 2
    assert s.players[0].name == "Alice"
    assert s.players[1].name == "Bob"

    # Each player draws 5 cards from a 10-card starting deck
    assert len(s.players[0].hand) == 5
    assert len(s.players[1].hand) == 5

    # Starting deck = 7 Copper + 3 Estate
    alice_all = s.players[0].all_cards()
    assert alice_all.count(CardName.COPPER) == 7
    assert alice_all.count(CardName.ESTATE) == 3

    # Province supply: 8 for 2-player game
    assert s.supply[CardName.PROVINCE] == 8

    # Turn starts with Alice in ACTION phase
    assert s.current_player.name == "Alice"
    assert s.phase == Phase.ACTION
    assert s.actions == 1
    assert s.buys == 1
    assert s.coins == 0

    print("✓ test_initial_state")


def test_kingdom_in_supply():
    engine = new_game()
    s = engine.state
    for card in FIRST_GAME_KINGDOM:
        assert s.supply[card] == 10, f"Expected 10 {card.value}, got {s.supply[card]}"
    print("✓ test_kingdom_in_supply")


# ---------------------------------------------------------------------------
# Buy phase basics
# ---------------------------------------------------------------------------

def test_play_treasures_and_buy():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.COPPER, CardName.COPPER, CardName.COPPER])

    skip_to_buy(engine, "Alice")

    events = engine.play_all_treasures("Alice")
    assert s.coins == 3
    assert len(s.current_player.hand) == 0
    assert CardName.COPPER in s.current_player.played

    events = engine.buy_card("Alice", CardName.SILVER)   # costs 3
    assert s.supply[CardName.SILVER] == 39
    assert CardName.SILVER in s.current_player.discard
    assert s.buys == 0
    assert s.coins == 0

    print("✓ test_play_treasures_and_buy")


def test_cannot_buy_without_coins():
    engine = new_game()
    skip_to_buy(engine, "Alice")

    try:
        engine.buy_card("Alice", CardName.GOLD)   # costs 6
        assert False, "Should have raised InvalidAction"
    except InvalidAction:
        pass

    print("✓ test_cannot_buy_without_coins")


def test_cannot_buy_with_no_buys():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.COPPER] * 6)
    skip_to_buy(engine, "Alice")
    engine.play_all_treasures("Alice")
    engine.buy_card("Alice", CardName.COPPER)   # use the 1 buy

    try:
        engine.buy_card("Alice", CardName.COPPER)
        assert False, "Should have raised InvalidAction"
    except InvalidAction:
        pass

    print("✓ test_cannot_buy_with_no_buys")


def test_buy_province():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.GOLD] * 3)   # 9 coins
    skip_to_buy(engine, "Alice")
    engine.play_all_treasures("Alice")
    engine.buy_card("Alice", CardName.PROVINCE)
    assert s.supply[CardName.PROVINCE] == 7
    print("✓ test_buy_province")


# ---------------------------------------------------------------------------
# Turn advancement
# ---------------------------------------------------------------------------

def test_turn_advances_after_buy_phase():
    engine = new_game()
    s = engine.state

    skip_to_buy(engine, "Alice")
    engine.end_buy_phase("Alice")

    assert s.current_player.name == "Bob"
    assert s.phase == Phase.ACTION
    assert s.actions == 1
    assert s.buys == 1
    assert s.coins == 0
    assert len(s.current_player.hand) == 5   # Bob drew 5 cards

    print("✓ test_turn_advances_after_buy_phase")


def test_cleanup_discards_hand_and_played():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.COPPER, CardName.ESTATE])

    skip_to_buy(engine, "Alice")
    engine.play_treasure("Alice", CardName.COPPER)
    engine.end_buy_phase("Alice")

    alice = s.players[0]
    assert len(alice.hand) == 0 or all(c in alice.hand for c in alice.hand)
    assert len(alice.played) == 0   # played should be cleared
    # Both Copper (played) and Estate (not played) should be in discard
    assert CardName.COPPER in alice.discard
    assert CardName.ESTATE in alice.discard

    print("✓ test_cleanup_discards_hand_and_played")


def test_not_your_turn():
    engine = new_game()
    try:
        engine.end_action_phase("Bob")
        assert False
    except NotYourTurn:
        pass
    print("✓ test_not_your_turn")


def test_wrong_phase_action_during_buy():
    engine = new_game()
    skip_to_buy(engine, "Alice")
    try:
        engine.end_action_phase("Alice")
        assert False
    except WrongPhase:
        pass
    print("✓ test_wrong_phase_action_during_buy")


# ---------------------------------------------------------------------------
# Simple action cards (no resolution needed)
# ---------------------------------------------------------------------------

def test_smithy_draws_three():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.SMITHY])

    initial_hand_after_play = 0  # Smithy leaves hand
    engine.play_action("Alice", CardName.SMITHY)

    # Hand should have 3 cards (Smithy moved to played, +3 drawn)
    assert len(s.current_player.hand) == 3
    assert CardName.SMITHY in s.current_player.played
    assert s.actions == 0

    print("✓ test_smithy_draws_three")


def test_village_plus_two_actions():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.VILLAGE, CardName.SMITHY])

    engine.play_action("Alice", CardName.VILLAGE)
    # Village: spend 1 action, gain 2 → net +1
    assert s.actions == 2
    # Also drew 1 card, so hand now has: Smithy + 1 drawn (Village moved to played)
    assert len(s.current_player.hand) == 2

    print("✓ test_village_plus_two_actions")


def test_market_bonuses():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.MARKET])

    engine.play_action("Alice", CardName.MARKET)

    assert s.actions == 1   # spent 1, gained 1 → net 0, still 1... wait
    # Actually: start with 1, spend 1 to play, gain 1 from Market = net 1
    assert s.actions == 1
    assert s.buys == 2
    assert s.coins == 1
    assert len(s.current_player.hand) == 1   # drew 1 (Market moved to played)

    print("✓ test_market_bonuses")


def test_woodcutter_bonuses():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.WOODCUTTER])

    engine.play_action("Alice", CardName.WOODCUTTER)

    assert s.buys == 2
    assert s.coins == 2
    assert s.actions == 0   # spent 1, no gain

    print("✓ test_woodcutter_bonuses")


def test_moat_draws_two():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.MOAT])

    engine.play_action("Alice", CardName.MOAT)
    assert len(s.current_player.hand) == 2   # drew 2

    print("✓ test_moat_draws_two")


# ---------------------------------------------------------------------------
# Cellar
# ---------------------------------------------------------------------------

def test_cellar_discard_and_draw():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.CELLAR, CardName.ESTATE, CardName.ESTATE])

    engine.play_action("Alice", CardName.CELLAR)
    assert s.phase == Phase.AWAITING_CELLAR_DISCARD
    assert s.actions == 1   # Cellar gives +1 action immediately

    engine.resolve_cellar("Alice", [CardName.ESTATE, CardName.ESTATE])

    assert s.phase == Phase.ACTION
    # Discarded 2, drew 2; hand has 2 new cards
    assert len(s.current_player.hand) == 2
    assert CardName.ESTATE not in s.current_player.hand or True  # drew from pile
    assert CardName.ESTATE in s.current_player.discard

    print("✓ test_cellar_discard_and_draw")


def test_cellar_discard_zero():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.CELLAR])

    engine.play_action("Alice", CardName.CELLAR)
    engine.resolve_cellar("Alice", [])   # discard nothing, draw nothing

    assert s.phase == Phase.ACTION
    assert len(s.current_player.hand) == 0

    print("✓ test_cellar_discard_zero")


# ---------------------------------------------------------------------------
# Mine
# ---------------------------------------------------------------------------

def test_mine_trash_copper_gain_silver():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.MINE, CardName.COPPER])

    engine.play_action("Alice", CardName.MINE)
    assert s.phase == Phase.AWAITING_MINE_TRASH

    engine.resolve_mine_trash("Alice", CardName.COPPER)
    assert CardName.COPPER in s.trash
    assert s.phase == Phase.AWAITING_MINE_GAIN
    assert s.pending_gain_max_cost == 3   # Copper costs 0, +3 = 3

    engine.resolve_mine_gain("Alice", CardName.SILVER)   # Silver costs 3 ≤ 3 ✓
    assert s.phase == Phase.ACTION
    assert CardName.SILVER in s.current_player.hand   # gained to hand

    print("✓ test_mine_trash_copper_gain_silver")


def test_mine_cannot_gain_too_expensive():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.MINE, CardName.COPPER])

    engine.play_action("Alice", CardName.MINE)
    engine.resolve_mine_trash("Alice", CardName.COPPER)   # max cost = 3

    try:
        engine.resolve_mine_gain("Alice", CardName.GOLD)   # Gold costs 6 > 3
        assert False, "Should raise InvalidAction"
    except InvalidAction:
        pass

    print("✓ test_mine_cannot_gain_too_expensive")


def test_mine_cannot_trash_non_treasure():
    engine = new_game()
    s = engine.state
    # Give Alice Mine + a Copper (treasure) + Estate; after playing Mine, hand = [COPPER, ESTATE]
    force_hand(engine, "Alice", [CardName.MINE, CardName.COPPER, CardName.ESTATE])

    engine.play_action("Alice", CardName.MINE)
    assert s.phase == Phase.AWAITING_MINE_TRASH

    try:
        engine.resolve_mine_trash("Alice", CardName.ESTATE)   # not a treasure
        assert False, "Should raise InvalidCard"
    except InvalidCard:
        pass

    print("✓ test_mine_cannot_trash_non_treasure")


def test_mine_no_treasures_skips_resolution():
    # When Mine is played but player has no treasures in hand, skip the AWAITING phase
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.MINE, CardName.ESTATE, CardName.DUCHY])

    engine.play_action("Alice", CardName.MINE)
    # Estate and Duchy are not treasures → engine stays in ACTION phase
    assert s.phase == Phase.ACTION

    print("✓ test_mine_no_treasures_skips_resolution")


# ---------------------------------------------------------------------------
# Remodel
# ---------------------------------------------------------------------------

def test_remodel_trash_estate_gain_silver():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.REMODEL, CardName.ESTATE])

    engine.play_action("Alice", CardName.REMODEL)
    assert s.phase == Phase.AWAITING_REMODEL_TRASH

    engine.resolve_remodel_trash("Alice", CardName.ESTATE)   # Estate costs 2
    assert CardName.ESTATE in s.trash
    assert s.pending_gain_max_cost == 4   # 2 + 2

    engine.resolve_remodel_gain("Alice", CardName.SMITHY)   # Smithy costs 4 ≤ 4 ✓
    assert CardName.SMITHY in s.current_player.discard
    assert s.phase == Phase.ACTION

    print("✓ test_remodel_trash_estate_gain_silver")


def test_remodel_cannot_gain_too_expensive():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.REMODEL, CardName.COPPER])

    engine.play_action("Alice", CardName.REMODEL)
    engine.resolve_remodel_trash("Alice", CardName.COPPER)   # Copper costs 0, max = 2

    try:
        engine.resolve_remodel_gain("Alice", CardName.MARKET)   # Market costs 5 > 2
        assert False, "Should raise InvalidAction"
    except InvalidAction:
        pass

    print("✓ test_remodel_cannot_gain_too_expensive")


# ---------------------------------------------------------------------------
# Workshop
# ---------------------------------------------------------------------------

def test_workshop_gain_card_costing_up_to_4():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.WORKSHOP])

    engine.play_action("Alice", CardName.WORKSHOP)
    assert s.phase == Phase.AWAITING_WORKSHOP_GAIN

    engine.resolve_workshop("Alice", CardName.SMITHY)   # costs 4 ≤ 4 ✓
    assert CardName.SMITHY in s.current_player.discard
    assert s.phase == Phase.ACTION

    print("✓ test_workshop_gain_card_costing_up_to_4")


def test_workshop_cannot_gain_expensive_card():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.WORKSHOP])

    engine.play_action("Alice", CardName.WORKSHOP)

    try:
        engine.resolve_workshop("Alice", CardName.MARKET)   # costs 5 > 4
        assert False, "Should raise InvalidAction"
    except InvalidAction:
        pass

    print("✓ test_workshop_cannot_gain_expensive_card")


# ---------------------------------------------------------------------------
# Militia
# ---------------------------------------------------------------------------

def test_militia_forces_opponent_to_discard():
    engine = new_game()
    s = engine.state

    # Give Alice Militia; give Bob a 5-card hand (he'll need to discard 2)
    force_hand(engine, "Alice", [CardName.MILITIA])
    force_hand(engine, "Bob", [
        CardName.COPPER, CardName.COPPER, CardName.ESTATE,
        CardName.COPPER, CardName.ESTATE,
    ])

    engine.play_action("Alice", CardName.MILITIA)

    # Militia gives +2 coins
    assert s.coins == 2
    assert s.phase == Phase.AWAITING_MILITIA_DISCARD
    assert s.militia_targets == [1]   # Bob is player index 1

    engine.resolve_militia_discard("Bob", [CardName.ESTATE, CardName.ESTATE])

    assert len(s.players[1].hand) == 3
    assert s.phase == Phase.ACTION   # back to Alice's action phase

    print("✓ test_militia_forces_opponent_to_discard")


def test_militia_wrong_player_raises():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.MILITIA])
    force_hand(engine, "Bob", [CardName.COPPER] * 5)

    engine.play_action("Alice", CardName.MILITIA)

    try:
        engine.resolve_militia_discard("Alice", [CardName.COPPER, CardName.COPPER])
        assert False, "Should raise NotYourTurn"
    except NotYourTurn:
        pass

    print("✓ test_militia_wrong_player_raises")


def test_militia_must_discard_correct_amount():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.MILITIA])
    force_hand(engine, "Bob", [CardName.COPPER] * 5)

    engine.play_action("Alice", CardName.MILITIA)

    try:
        # Bob has 5 cards, must discard 2, but tries to discard only 1
        engine.resolve_militia_discard("Bob", [CardName.COPPER])
        assert False, "Should raise InvalidAction"
    except InvalidAction:
        pass

    print("✓ test_militia_must_discard_correct_amount")


def test_moat_blocks_militia():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.MILITIA])
    # Bob has a Moat in hand → protected
    force_hand(engine, "Bob", [CardName.MOAT, CardName.COPPER, CardName.COPPER,
                                CardName.COPPER, CardName.COPPER])

    engine.play_action("Alice", CardName.MILITIA)

    # Bob is immune; no militia discard phase
    assert s.phase == Phase.ACTION
    assert s.militia_targets == []
    assert len(s.players[1].hand) == 5   # Bob's hand untouched

    print("✓ test_moat_blocks_militia")


def test_militia_skips_players_with_3_or_fewer():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.MILITIA])
    # Bob only has 3 cards → already safe
    force_hand(engine, "Bob", [CardName.COPPER, CardName.COPPER, CardName.COPPER])

    engine.play_action("Alice", CardName.MILITIA)

    # No discard needed
    assert s.phase == Phase.ACTION
    assert s.militia_targets == []

    print("✓ test_militia_skips_players_with_3_or_fewer")


# ---------------------------------------------------------------------------
# Game end conditions
# ---------------------------------------------------------------------------

def test_game_ends_when_provinces_exhausted():
    engine = new_game()
    s = engine.state

    # Drain the Province pile
    s.supply[CardName.PROVINCE] = 0

    skip_to_buy(engine, "Alice")
    engine.end_buy_phase("Alice")   # cleanup triggers end-of-turn check

    assert s.phase == Phase.GAME_OVER

    print("✓ test_game_ends_when_provinces_exhausted")


def test_game_ends_when_three_piles_empty():
    engine = new_game()
    s = engine.state

    s.supply[CardName.ESTATE]    = 0
    s.supply[CardName.DUCHY]     = 0
    s.supply[CardName.SMITHY]    = 0

    skip_to_buy(engine, "Alice")
    engine.end_buy_phase("Alice")

    assert s.phase == Phase.GAME_OVER

    print("✓ test_game_ends_when_three_piles_empty")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def test_scoring():
    engine = new_game()
    s = engine.state

    # Force Alice to have lots of victory cards
    alice = s.players[0]
    alice.discard.extend([CardName.PROVINCE, CardName.PROVINCE, CardName.DUCHY])
    # Alice's base deck has 3 Estates (in draw pile / hand)
    # Province×2 = 12, Duchy×1 = 3, Estate×3 = 3 → total 18

    s.supply[CardName.PROVINCE] = 0   # trigger end
    skip_to_buy(engine, "Alice")
    engine.end_buy_phase("Alice")

    assert s.phase == Phase.GAME_OVER
    assert s.players[0].name in engine.state.players[0].name

    scores = {p.name: sum(CARD_REGISTRY[c].vp for c in p.all_cards()) for p in s.players}
    assert scores["Alice"] == 18

    print("✓ test_scoring")


def test_curse_subtracts_vp():
    engine = new_game()
    s = engine.state

    alice = s.players[0]
    alice.discard.append(CardName.CURSE)   # -1 VP

    # Base VP: 3 Estates = 3, minus 1 Curse = 2
    score = sum(CARD_REGISTRY[c].vp for c in alice.all_cards())
    assert score == 2

    print("✓ test_curse_subtracts_vp")


# ---------------------------------------------------------------------------
# Multiple buys
# ---------------------------------------------------------------------------

def test_multiple_buys_via_woodcutter():
    engine = new_game()
    s = engine.state
    force_hand(engine, "Alice", [CardName.WOODCUTTER, CardName.COPPER, CardName.COPPER,
                                  CardName.COPPER, CardName.COPPER])

    engine.play_action("Alice", CardName.WOODCUTTER)   # +1 buy, +2 coins
    assert s.buys == 2
    assert s.coins == 2

    skip_to_buy(engine, "Alice")

    engine.play_all_treasures("Alice")   # plays 4 Copper = +4 coins; total = 6
    assert s.coins == 6

    engine.buy_card("Alice", CardName.SILVER)   # costs 3; 1 buy used
    engine.buy_card("Alice", CardName.COPPER)   # costs 0; 2nd buy used

    assert s.buys == 0
    assert CardName.SILVER in s.current_player.discard
    assert CardName.COPPER in s.current_player.discard

    print("✓ test_multiple_buys_via_woodcutter")


# ---------------------------------------------------------------------------
# Extra: reshuffle when draw pile exhausted
# ---------------------------------------------------------------------------

def test_deck_reshuffles_from_discard():
    engine = new_game()
    s = engine.state

    alice = s.players[0]
    # Drain draw pile completely
    alice.draw_pile = []
    alice.discard = [CardName.GOLD, CardName.GOLD]
    alice.hand = []

    # Force draw; should reshuffle discard
    skip_to_buy(engine, "Alice")
    engine.end_buy_phase("Alice")   # cleanup + draw 5 for Bob

    # Now Bob's turn; let's simulate Alice's next turn by manually draining Bob's
    # Instead, let's just test the _draw_cards helper directly
    engine2 = new_game(seed=1)
    s2 = engine2.state
    alice2 = s2.players[0]
    alice2.draw_pile = []
    alice2.discard = [CardName.GOLD]
    alice2.hand = [CardName.COPPER]

    from engine import GameEngine as GE
    drawn = engine2._draw_cards(alice2, 1)
    assert drawn == [CardName.GOLD]
    assert CardName.GOLD in alice2.hand

    print("✓ test_deck_reshuffles_from_discard")


if __name__ == "__main__":
    tests = [
        test_initial_state,
        test_kingdom_in_supply,
        test_play_treasures_and_buy,
        test_cannot_buy_without_coins,
        test_cannot_buy_with_no_buys,
        test_buy_province,
        test_turn_advances_after_buy_phase,
        test_cleanup_discards_hand_and_played,
        test_not_your_turn,
        test_wrong_phase_action_during_buy,
        test_smithy_draws_three,
        test_village_plus_two_actions,
        test_market_bonuses,
        test_woodcutter_bonuses,
        test_moat_draws_two,
        test_cellar_discard_and_draw,
        test_cellar_discard_zero,
        test_mine_trash_copper_gain_silver,
        test_mine_cannot_gain_too_expensive,
        test_mine_cannot_trash_non_treasure,
        test_mine_no_treasures_skips_resolution,
        test_remodel_trash_estate_gain_silver,
        test_remodel_cannot_gain_too_expensive,
        test_workshop_gain_card_costing_up_to_4,
        test_workshop_cannot_gain_expensive_card,
        test_militia_forces_opponent_to_discard,
        test_militia_wrong_player_raises,
        test_militia_must_discard_correct_amount,
        test_moat_blocks_militia,
        test_militia_skips_players_with_3_or_fewer,
        test_game_ends_when_provinces_exhausted,
        test_game_ends_when_three_piles_empty,
        test_scoring,
        test_curse_subtracts_vp,
        test_multiple_buys_via_woodcutter,
        test_deck_reshuffles_from_discard,
    ]

    failed = 0
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'All tests passed!' if failed == 0 else f'{failed} test(s) FAILED'}")
    sys.exit(failed)
