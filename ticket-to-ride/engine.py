"""
Ticket to Ride — Game Engine

Owns GameState and enforces all rules. Every mutation goes through here.
Emits Event objects that external code can observe.

Usage:
    engine = GameEngine.new_game(["Alice", "Bob"])
    events = engine.draw_train_card_from_deck("Alice")
    events = engine.draw_train_card_from_deck("Alice")
    # ... etc.
"""

from __future__ import annotations

import random
from collections import defaultdict, deque
from typing import Callable, Optional

from board import build_destination_tickets, build_routes
from errors import (
    InsufficientCards,
    InsufficientTrains,
    InvalidAction,
    NotYourTurn,
    RouteAlreadyClaimed,
    WrongPhase,
)
from events import (
    CardDrawnFromDeck,
    CardDrawnFromFaceUp,
    DestinationTicketsKept,
    DestinationTicketsOffered,
    Event,
    FaceUpCardReplaced,
    FaceUpCardsReset,
    GameOver,
    LastRoundTriggered,
    RouteClaimed,
)
from models import Color, DestinationTicket, GameState, Phase, Player, RouteId
from scoring import (
    calculate_destination_ticket_bonuses,
    find_all_longest_route_players,
)

# Number of destination tickets dealt at game start / when drawing mid-game
INITIAL_TICKETS = 3
DRAW_TICKETS = 3
MIN_KEEP_INITIAL = 2
MIN_KEEP_DRAW = 1

# Train card distribution (110 cards: 12 per colour × 8 + 14 wilds)
_CARD_DISTRIBUTION: dict[Color, int] = {
    Color.RED: 12,
    Color.BLUE: 12,
    Color.GREEN: 12,
    Color.YELLOW: 12,
    Color.ORANGE: 12,
    Color.PINK: 12,
    Color.WHITE: 12,
    Color.BLACK: 12,
    Color.WILD: 14,
}

PLAYER_COLORS = ["red", "blue", "green", "yellow", "black"]
LONGEST_ROUTE_BONUS = 10
LAST_ROUND_TRIGGER_TRAINS = 2


def _build_train_deck() -> list[Color]:
    deck: list[Color] = []
    for color, count in _CARD_DISTRIBUTION.items():
        deck.extend([color] * count)
    random.shuffle(deck)
    return deck


class GameEngine:
    """
    Encapsulates all game logic.

    All public methods return a list[Event] describing what happened.
    Raises subclasses of GameError if the move is illegal.
    """

    def __init__(self, state: GameState) -> None:
        self._state = state
        self._event_handlers: list[Callable[[Event], None]] = []

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def new_game(cls, player_names: list[str], seed: Optional[int] = None) -> "GameEngine":
        if seed is not None:
            random.seed(seed)

        if not 2 <= len(player_names) <= 5:
            raise ValueError("Ticket to Ride requires 2-5 players.")

        players = [
            Player(name=name, color=PLAYER_COLORS[i])
            for i, name in enumerate(player_names)
        ]

        routes = build_routes()
        all_tickets = build_destination_tickets()
        random.shuffle(all_tickets)

        deck = _build_train_deck()
        face_up: list[Color] = []

        state = GameState(
            players=players,
            routes=routes,
            destination_tickets=all_tickets[:],
            train_deck=deck,
            train_discard=[],
            face_up_cards=[],
            destination_deck=all_tickets[:],
            claimed_routes={},
            current_player_index=0,
            phase=Phase.CHOOSE_ACTION,
        )

        engine = cls(state)

        # Deal 4 train cards to each player
        for player in state.players:
            for _ in range(4):
                engine._deal_card_to_player(player)

        # Reveal 5 face-up cards
        engine._refill_face_up()

        # Deal initial destination tickets (players will choose during setup)
        random.shuffle(state.destination_deck)
        engine._offer_destination_tickets(state.players[0], MIN_KEEP_INITIAL)

        return engine

    # ------------------------------------------------------------------
    # Event subscription
    # ------------------------------------------------------------------

    def subscribe(self, handler: Callable[[Event], None]) -> None:
        """Register a callback invoked for every emitted event."""
        self._event_handlers.append(handler)

    def _emit(self, event: Event) -> None:
        for h in self._event_handlers:
            h(event)

    # ------------------------------------------------------------------
    # Public read access
    # ------------------------------------------------------------------

    @property
    def state(self) -> GameState:
        return self._state

    # ------------------------------------------------------------------
    # Player actions
    # ------------------------------------------------------------------

    def draw_train_card_from_deck(self, player_name: str) -> list[Event]:
        """Draw a blind card from the top of the train deck."""
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.CHOOSE_ACTION, Phase.DRAWING_CARDS)

        if not s.train_deck and not s.train_discard:
            raise InvalidAction("No cards left in the train deck.")

        card = self._deal_card_to_player(s.current_player)
        events: list[Event] = [CardDrawnFromDeck(player_name=player_name)]
        self._emit(events[-1])

        events += self._advance_draw_phase(drew_wild_face_up=False)
        return events

    def draw_train_card_face_up(self, player_name: str, slot: int) -> list[Event]:
        """Draw the face-up card at *slot* (0-4)."""
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.CHOOSE_ACTION, Phase.DRAWING_CARDS)

        if not 0 <= slot < len(s.face_up_cards):
            raise InvalidAction(f"Slot {slot} is out of range.")

        card = s.face_up_cards[slot]

        # Locomotives taken face-up count as BOTH draws; cannot be the second draw.
        if s.phase == Phase.DRAWING_CARDS and card == Color.WILD:
            raise InvalidAction(
                "You cannot take a face-up locomotive as your second card draw."
            )

        # Remove card from face-up and give to player
        s.face_up_cards.pop(slot)
        s.current_player.hand.append(card)

        events: list[Event] = [
            CardDrawnFromFaceUp(player_name=player_name, card=card, slot=slot)
        ]
        self._emit(events[-1])

        # Replace the slot
        replace_events = self._refill_face_up_slot()
        events += replace_events

        events += self._advance_draw_phase(drew_wild_face_up=(card == Color.WILD))
        return events

    def draw_destination_tickets(self, player_name: str) -> list[Event]:
        """Draw 3 destination tickets; player must keep at least 1."""
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.CHOOSE_ACTION)

        if len(s.destination_deck) == 0:
            raise InvalidAction("No destination tickets remaining.")

        events = self._offer_destination_tickets(s.current_player, MIN_KEEP_DRAW)
        return events

    def keep_destination_tickets(
        self, player_name: str, ticket_ids: list[int]
    ) -> list[Event]:
        """
        Keep the tickets with the given ids from the pending_tickets offer.
        All others are returned to the bottom of the destination deck.
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.KEEPING_TICKETS)

        offered_ids = {t.id for t in s.pending_tickets}
        if not set(ticket_ids).issubset(offered_ids):
            raise InvalidAction("ticket_ids contains tickets not in the current offer.")

        if len(ticket_ids) < s.min_tickets_to_keep:
            raise InvalidAction(
                f"You must keep at least {s.min_tickets_to_keep} destination ticket(s)."
            )

        kept = [t for t in s.pending_tickets if t.id in ticket_ids]
        returned = [t for t in s.pending_tickets if t.id not in ticket_ids]

        s.current_player.destination_tickets.extend(kept)
        s.destination_deck.extend(returned)   # returned to bottom
        s.pending_tickets = []

        events: list[Event] = [
            DestinationTicketsKept(
                player_name=player_name, kept=kept, returned=returned
            )
        ]
        self._emit(events[-1])

        events += self._end_turn()
        return events

    def claim_route(
        self,
        player_name: str,
        route_id: RouteId,
        cards: list[Color],
    ) -> list[Event]:
        """
        Claim a route by spending *cards* from the player's hand.

        *cards* must be a valid payment for the route (correct colour/count,
        wilds filling any gaps).
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.CHOOSE_ACTION)

        if route_id not in s.routes:
            raise InvalidAction(f"Route {route_id} does not exist.")

        route = s.routes[route_id]
        player = s.current_player

        # Check route not already claimed
        if route_id in s.claimed_routes:
            raise RouteAlreadyClaimed(f"Route {route_id} is already claimed.")

        # For double routes: in 2-3 player games the same player may not claim
        # both parallel routes between the same cities.
        if s.num_players <= 3:
            for idx in range(2):
                sibling = RouteId(route.city_a, route.city_b, idx)
                if sibling != route_id and sibling in s.claimed_routes:
                    if s.claimed_routes[sibling] == s.current_player_index:
                        raise InvalidAction(
                            "In a 2-3 player game you cannot claim both parallel routes."
                        )

        # Validate card payment
        _validate_payment(route, cards)

        # Check player actually has those cards
        hand = player.hand[:]
        for card in cards:
            if card not in hand:
                raise InsufficientCards(
                    f"Player does not have {card.value} in hand."
                )
            hand.remove(card)

        # Check train count
        if player.trains_remaining < route.length:
            raise InsufficientTrains(
                f"Need {route.length} trains but only {player.trains_remaining} remain."
            )

        # Apply the move
        for card in cards:
            player.hand.remove(card)
            s.train_discard.append(card)

        player.trains_remaining -= route.length
        player.claimed_routes.append(route_id)
        player.score += route.points
        s.claimed_routes[route_id] = s.current_player_index

        events: list[Event] = [
            RouteClaimed(
                player_name=player_name,
                route_id=route_id,
                cards_spent=cards,
                points_scored=route.points,
            )
        ]
        self._emit(events[-1])

        # Last round trigger
        if player.trains_remaining <= LAST_ROUND_TRIGGER_TRAINS and not s.last_round:
            s.last_round = True
            s.last_round_trigger_player = s.current_player_index
            evt = LastRoundTriggered(
                player_name=player_name,
                trains_remaining=player.trains_remaining,
            )
            events.append(evt)
            self._emit(evt)

        events += self._end_turn()
        return events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assert_active(self, player_name: str) -> None:
        if self._state.current_player.name != player_name:
            raise NotYourTurn(
                f"It is {self._state.current_player.name}'s turn, not {player_name}'s."
            )

    def _assert_phase(self, *allowed: Phase) -> None:
        if self._state.phase not in allowed:
            raise WrongPhase(
                f"Expected phase {allowed}, got {self._state.phase}."
            )

    def _deal_card_to_player(self, player: Player) -> Color:
        """Pop one card from the deck (reshuffling discard if needed) into player hand."""
        s = self._state
        if not s.train_deck:
            if not s.train_discard:
                raise InvalidAction("Both deck and discard are empty.")
            s.train_deck = s.train_discard[:]
            s.train_discard = []
            random.shuffle(s.train_deck)

        card = s.train_deck.pop()
        player.hand.append(card)
        return card

    def _refill_face_up(self) -> list[Event]:
        """Fill face_up_cards to 5, enforcing the '3 locomotives → reset' rule."""
        s = self._state
        events: list[Event] = []

        while len(s.face_up_cards) < 5 and (s.train_deck or s.train_discard):
            if not s.train_deck:
                s.train_deck = s.train_discard[:]
                s.train_discard = []
                random.shuffle(s.train_deck)
            card = s.train_deck.pop()
            s.face_up_cards.append(card)

        # If 3+ wilds are showing, discard all and redraw
        while s.face_up_cards.count(Color.WILD) >= 3:
            s.train_discard.extend(s.face_up_cards)
            s.face_up_cards = []
            while len(s.face_up_cards) < 5 and (s.train_deck or s.train_discard):
                if not s.train_deck:
                    s.train_deck = s.train_discard[:]
                    s.train_discard = []
                    random.shuffle(s.train_deck)
                card = s.train_deck.pop()
                s.face_up_cards.append(card)
            evt = FaceUpCardsReset(new_cards=s.face_up_cards[:])
            events.append(evt)
            self._emit(evt)

        return events

    def _refill_face_up_slot(self) -> list[Event]:
        """After a card is taken from face_up, fill back to 5."""
        s = self._state
        events: list[Event] = []

        if len(s.face_up_cards) < 5 and (s.train_deck or s.train_discard):
            if not s.train_deck:
                s.train_deck = s.train_discard[:]
                s.train_discard = []
                random.shuffle(s.train_deck)
            if s.train_deck:
                new_card = s.train_deck.pop()
                s.face_up_cards.append(new_card)
                evt = FaceUpCardReplaced(slot=len(s.face_up_cards) - 1, new_card=new_card)
                events.append(evt)
                self._emit(evt)

        # Check for 3-locomotive reset
        events += self._refill_face_up()
        return events

    def _advance_draw_phase(self, drew_wild_face_up: bool) -> list[Event]:
        """
        Move the turn phase forward after one card draw.
        A locomotive drawn face-up uses BOTH draws.
        """
        s = self._state

        if s.phase == Phase.CHOOSE_ACTION:
            if drew_wild_face_up:
                # Taking a visible locomotive counts as both draws
                return self._end_turn()
            else:
                s.phase = Phase.DRAWING_CARDS
                s.first_draw_was_wild = False
                return []

        else:  # DRAWING_CARDS — this was the second draw
            return self._end_turn()

    def _offer_destination_tickets(
        self, player: Player, min_keep: int
    ) -> list[Event]:
        s = self._state
        count = min(DRAW_TICKETS, len(s.destination_deck))
        offered = s.destination_deck[:count]
        s.destination_deck = s.destination_deck[count:]

        s.pending_tickets = offered
        s.min_tickets_to_keep = min_keep
        s.phase = Phase.KEEPING_TICKETS

        evt = DestinationTicketsOffered(
            player_name=player.name, tickets=offered, min_keep=min_keep
        )
        self._emit(evt)
        return [evt]

    def _end_turn(self) -> list[Event]:
        """Advance to the next player, or end the game."""
        s = self._state
        s.phase = Phase.CHOOSE_ACTION
        s.first_draw_was_wild = False
        s.pending_tickets = []

        next_index = (s.current_player_index + 1) % s.num_players

        # Last round: game ends after the triggering player's final turn comes back around
        if s.last_round and next_index == s.last_round_trigger_player:
            return self._end_game()

        s.current_player_index = next_index

        # Initial setup: each player must choose their starting tickets first
        # We check if the new current player still needs to choose their tickets
        new_player = s.players[next_index]
        if not new_player.destination_tickets and s.phase == Phase.CHOOSE_ACTION:
            # During the initial setup round, deal tickets to next player
            if next_index != 0 or (
                next_index == 0 and not s.last_round
            ):
                pass  # setup is handled externally for simplicity

        return []

    def _end_game(self) -> list[Event]:
        s = self._state
        s.phase = Phase.GAME_OVER

        # Destination ticket bonuses / penalties
        bonus_map = calculate_destination_ticket_bonuses(s)
        for i, player in enumerate(s.players):
            player.score += bonus_map[i]

        # Longest continuous route bonus (all tied players get it)
        for winner_idx in find_all_longest_route_players(s):
            s.players[winner_idx].score += LONGEST_ROUTE_BONUS

        scores = {p.name: p.score for p in s.players}
        winner_name = max(scores, key=lambda n: scores[n])

        evt = GameOver(scores=scores, winner=winner_name)
        self._emit(evt)
        return [evt]


# ------------------------------------------------------------------
# Payment validation (pure function, no state)
# ------------------------------------------------------------------

def _validate_payment(route, cards: list[Color]) -> None:
    """
    Raise InvalidAction if *cards* are not a legal payment for *route*.

    Rules:
    - Must provide exactly route.length cards.
    - All non-wild cards must be the same colour.
    - If the route has a specific colour (not WILD), non-wild cards must match it.
    - Wild (locomotive) cards can substitute for any colour.
    """
    from errors import InvalidAction  # local import to avoid circular

    if len(cards) != route.length:
        raise InvalidAction(
            f"Route requires exactly {route.length} card(s); got {len(cards)}."
        )

    non_wild = [c for c in cards if c != Color.WILD]

    if len(non_wild) == 0:
        # All wilds — always valid
        return

    # All non-wild cards must be the same colour
    if len(set(non_wild)) > 1:
        raise InvalidAction("All non-locomotive cards must be the same colour.")

    payment_color = non_wild[0]

    # Route colour constraint
    if route.color != Color.WILD and payment_color != route.color:
        raise InvalidAction(
            f"Route requires {route.color.value} cards; got {payment_color.value}."
        )
