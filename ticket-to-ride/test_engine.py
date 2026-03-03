"""
Basic smoke tests for the Ticket to Ride engine.
Run with: python test_engine.py
"""

import sys
from models import Color, Phase, RouteId
from engine import GameEngine, _validate_payment
from errors import InvalidAction, WrongPhase, NotYourTurn, RouteAlreadyClaimed
from board import build_routes


def test_new_game_state():
    engine = GameEngine.new_game(["Alice", "Bob"], seed=42)
    s = engine.state

    assert len(s.players) == 2
    assert s.players[0].name == "Alice"
    assert s.players[1].name == "Bob"

    # Each player should have 4 cards dealt at start
    assert len(s.players[0].hand) == 4
    assert len(s.players[1].hand) == 4

    # Face-up should have 5 cards (or fewer if deck ran out, very unlikely)
    assert len(s.face_up_cards) == 5

    # Game starts in KEEPING_TICKETS (first player choosing starting tickets)
    assert s.phase == Phase.KEEPING_TICKETS
    assert len(s.pending_tickets) == 3

    print("✓ test_new_game_state")


def test_keep_destination_tickets():
    engine = GameEngine.new_game(["Alice", "Bob"], seed=42)
    s = engine.state

    # Alice keeps 2 of the 3 offered tickets
    offered_ids = [t.id for t in s.pending_tickets]
    keep_ids = offered_ids[:2]

    events = engine.keep_destination_tickets("Alice", keep_ids)
    assert len(s.players[0].destination_tickets) == 2

    print("✓ test_keep_destination_tickets")


def _setup_game_past_tickets(seed=42):
    """Return engine where both players have chosen their starting tickets."""
    engine = GameEngine.new_game(["Alice", "Bob"], seed=seed)
    s = engine.state

    # Alice keeps all 3
    ids = [t.id for t in s.pending_tickets]
    engine.keep_destination_tickets("Alice", ids)

    # Bob is now offered tickets (we simulate the setup round manually)
    # The engine doesn't auto-offer for player 2 during setup in _end_turn;
    # we replicate what a host would do: offer tickets to Bob.
    from engine import MIN_KEEP_INITIAL
    engine._offer_destination_tickets(s.players[1], MIN_KEEP_INITIAL)
    ids = [t.id for t in s.pending_tickets]
    engine.keep_destination_tickets("Bob", ids)

    return engine


def test_draw_cards_from_deck():
    engine = _setup_game_past_tickets()
    s = engine.state

    assert s.current_player.name == "Alice"
    initial_hand = len(s.current_player.hand)

    engine.draw_train_card_from_deck("Alice")
    assert s.phase == Phase.DRAWING_CARDS

    engine.draw_train_card_from_deck("Alice")
    assert s.phase == Phase.CHOOSE_ACTION
    assert s.current_player.name == "Bob"

    assert len(s.players[0].hand) == initial_hand + 2
    print("✓ test_draw_cards_from_deck")


def test_draw_face_up_wild_counts_as_both():
    engine = _setup_game_past_tickets(seed=1)
    s = engine.state

    # Force a wild into slot 0
    s.face_up_cards[0] = Color.WILD

    initial_hand = len(s.current_player.hand)
    engine.draw_train_card_face_up("Alice", 0)

    # Should have immediately ended Alice's turn
    assert s.phase == Phase.CHOOSE_ACTION
    assert s.current_player.name == "Bob"
    assert len(s.players[0].hand) == initial_hand + 1
    print("✓ test_draw_face_up_wild_counts_as_both")


def test_cannot_draw_wild_as_second_card():
    engine = _setup_game_past_tickets(seed=2)
    s = engine.state

    # Draw a non-wild first
    s.face_up_cards[0] = Color.RED
    engine.draw_train_card_face_up("Alice", 0)
    assert s.phase == Phase.DRAWING_CARDS

    # Now try to take a face-up wild as second draw
    s.face_up_cards[0] = Color.WILD
    try:
        engine.draw_train_card_face_up("Alice", 0)
        assert False, "Should have raised InvalidAction"
    except InvalidAction:
        pass
    print("✓ test_cannot_draw_wild_as_second_card")


def test_claim_route():
    engine = _setup_game_past_tickets()
    s = engine.state
    player = s.players[0]

    # Force Alice's hand so she can claim Dallas-Houston (length 1, grey)
    player.hand = [Color.RED]
    route_id = RouteId("Dallas", "Houston", 0)
    assert route_id in s.routes

    events = engine.claim_route("Alice", route_id, [Color.RED])
    assert route_id in s.claimed_routes
    assert s.claimed_routes[route_id] == 0  # Alice is player 0
    assert player.score == 1                 # length-1 route = 1 point
    assert player.trains_remaining == 44
    assert s.current_player.name == "Bob"
    print("✓ test_claim_route")


def test_cannot_claim_taken_route():
    engine = _setup_game_past_tickets()
    s = engine.state

    route_id = RouteId("Dallas", "Houston", 0)
    s.players[0].hand = [Color.RED]
    engine.claim_route("Alice", route_id, [Color.RED])

    # Bob tries to claim same route
    s.players[1].hand = [Color.RED]
    try:
        engine.claim_route("Bob", route_id, [Color.RED])
        assert False, "Should have raised RouteAlreadyClaimed"
    except RouteAlreadyClaimed:
        pass
    print("✓ test_cannot_claim_taken_route")


def test_not_your_turn():
    engine = _setup_game_past_tickets()
    try:
        engine.draw_train_card_from_deck("Bob")
        assert False
    except NotYourTurn:
        pass
    print("✓ test_not_your_turn")


def test_validate_payment_wrong_color():
    routes = build_routes()
    # Find a coloured route, e.g. Portland-San Francisco (GREEN, length 5)
    route = routes[RouteId("Portland", "San Francisco", 0)]
    assert route.color == Color.GREEN

    try:
        _validate_payment(route, [Color.RED] * 5)
        assert False
    except InvalidAction:
        pass
    print("✓ test_validate_payment_wrong_color")


def test_validate_payment_wilds_allowed():
    routes = build_routes()
    route = routes[RouteId("Portland", "San Francisco", 0)]  # GREEN, length 5
    # 3 green + 2 wild is valid
    _validate_payment(route, [Color.GREEN, Color.GREEN, Color.GREEN, Color.WILD, Color.WILD])
    print("✓ test_validate_payment_wilds_allowed")


def test_validate_payment_all_wilds():
    routes = build_routes()
    route = routes[RouteId("Dallas", "Houston", 0)]  # WILD (grey), length 1
    _validate_payment(route, [Color.WILD])
    print("✓ test_validate_payment_all_wilds")


if __name__ == "__main__":
    tests = [
        test_new_game_state,
        test_keep_destination_tickets,
        test_draw_cards_from_deck,
        test_draw_face_up_wild_counts_as_both,
        test_cannot_draw_wild_as_second_card,
        test_claim_route,
        test_cannot_claim_taken_route,
        test_not_your_turn,
        test_validate_payment_wrong_color,
        test_validate_payment_wilds_allowed,
        test_validate_payment_all_wilds,
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
