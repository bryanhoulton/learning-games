"""
RandomPlayerAgent — makes uniformly random valid moves using only PlayerView.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Optional

from models import Color, Phase, RouteId
from player_agent import (
    ClaimRouteAction,
    DrawCardAction,
    DrawTicketsAction,
    KeepTicketsAction,
    PlayerAction,
    PlayerAgent,
)
from player_view import PlayerView


def _cheapest_payment(route, hand_counts: Counter, wild_count: int) -> Optional[list[Color]]:
    n = route.length
    candidates = [route.color] if route.color != Color.WILD else [
        c for c in Color if c != Color.WILD
    ]
    best = None
    for color in candidates:
        have = hand_counts[color]
        needed = n - have
        if needed <= 0:
            return [color] * n
        elif needed <= wild_count:
            if best is None:
                best = [color] * have + [Color.WILD] * needed
    return best


def _claimable_routes(view: PlayerView) -> list[tuple[RouteId, list[Color]]]:
    hand_counts = Counter(view.my_hand)
    wild_count = hand_counts[Color.WILD]
    claimable = []
    for rid, route in view.routes.items():
        if rid in view.all_claimed_routes:
            continue
        if view.my_trains_remaining < route.length:
            continue
        if view.num_players <= 3:
            sibling_blocked = any(
                RouteId(route.city_a, route.city_b, idx) != rid
                and RouteId(route.city_a, route.city_b, idx) in view.all_claimed_routes
                and view.all_claimed_routes[RouteId(route.city_a, route.city_b, idx)] == view.my_name
                for idx in range(2)
            )
            if sibling_blocked:
                continue
        payment = _cheapest_payment(route, hand_counts, wild_count)
        if payment is not None:
            claimable.append((rid, payment))
    return claimable


class RandomPlayerAgent(PlayerAgent):

    def __init__(self, player_name: str) -> None:
        self._name = player_name

    @property
    def name(self) -> str:
        return self._name

    def choose_action(self, view: PlayerView, error: Optional[str] = None) -> PlayerAction:
        if view.phase == Phase.KEEPING_TICKETS:
            return self._keep_tickets(view)
        elif view.phase == Phase.DRAWING_CARDS:
            return self._draw_second_card(view)
        else:
            return self._choose_action(view)

    def _choose_action(self, view: PlayerView) -> PlayerAction:
        actions: list[PlayerAction] = []

        # Always can draw a card if deck has cards or face-up cards exist
        if view.train_deck_size > 0 or view.face_up_cards:
            for i, card in enumerate(view.face_up_cards):
                actions.append(DrawCardAction(slot=i))
            if view.train_deck_size > 0:
                actions.append(DrawCardAction(slot=None))

        # Claim routes if affordable
        for rid, payment in _claimable_routes(view):
            actions.append(ClaimRouteAction(route_id=rid, cards=tuple(payment)))

        # Draw tickets if deck not empty
        if view.destination_deck_size > 0:
            actions.append(DrawTicketsAction())

        return random.choice(actions)

    def _draw_second_card(self, view: PlayerView) -> DrawCardAction:
        options: list[DrawCardAction] = []
        for i, card in enumerate(view.face_up_cards):
            if card != Color.WILD:
                options.append(DrawCardAction(slot=i))
        if view.train_deck_size > 0:
            options.append(DrawCardAction(slot=None))
        # Fall back to deck draw if no non-wild face-up cards and deck is empty
        if not options:
            options.append(DrawCardAction(slot=None))
        return random.choice(options)

    def _keep_tickets(self, view: PlayerView) -> KeepTicketsAction:
        tickets = list(view.pending_tickets)
        keep_count = random.randint(view.min_tickets_to_keep, len(tickets))
        kept = random.sample(tickets, keep_count)
        return KeepTicketsAction(ticket_ids=tuple(t.id for t in kept))
