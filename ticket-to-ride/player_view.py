"""
PlayerView — what a single player is allowed to observe.

Built from GameState but enforcing information hiding:
- Own hand and tickets are fully visible
- Opponents' hands and tickets are reduced to counts only
- Public board state (face-up cards, claimed routes, deck sizes) is fully visible
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from models import Color, DestinationTicket, Phase, Route, RouteId

if TYPE_CHECKING:
    from models import GameState


@dataclass(frozen=True)
class OpponentView:
    name: str
    hand_size: int          # count only — NOT which cards
    ticket_count: int       # count only — NOT which tickets
    trains_remaining: int
    score: int
    claimed_routes: tuple[RouteId, ...]


@dataclass(frozen=True)
class PlayerView:
    # Identity
    my_name: str
    my_index: int
    # Private (own) info
    my_hand: tuple[Color, ...]
    my_tickets: tuple[DestinationTicket, ...]
    my_trains_remaining: int
    my_score: int
    my_claimed_routes: tuple[RouteId, ...]
    # Public board state
    face_up_cards: tuple[Color, ...]
    train_deck_size: int
    destination_deck_size: int
    routes: dict[RouteId, Route]            # full board definition (public)
    all_claimed_routes: dict[RouteId, str]  # route_id -> owner name (public)
    # Other players (public info only)
    opponents: tuple[OpponentView, ...]
    # Turn state
    phase: Phase
    current_player_name: str
    is_my_turn: bool
    last_round: bool
    num_players: int
    # KEEPING_TICKETS phase only (empty otherwise)
    pending_tickets: tuple[DestinationTicket, ...]
    min_tickets_to_keep: int


def build_player_view(state: GameState, player_index: int) -> PlayerView:
    """Build a PlayerView for the player at *player_index*."""
    me = state.players[player_index]

    opponents = tuple(
        OpponentView(
            name=p.name,
            hand_size=len(p.hand),
            ticket_count=len(p.destination_tickets),
            trains_remaining=p.trains_remaining,
            score=p.score,
            claimed_routes=tuple(p.claimed_routes),
        )
        for i, p in enumerate(state.players)
        if i != player_index
    )

    # all_claimed_routes maps route_id -> owner name
    all_claimed_routes = {
        rid: state.players[owner_idx].name
        for rid, owner_idx in state.claimed_routes.items()
    }

    # pending_tickets only visible when it's this player's KEEPING_TICKETS turn
    is_my_turn = state.current_player_index == player_index
    if state.phase == Phase.KEEPING_TICKETS and is_my_turn:
        pending_tickets = tuple(state.pending_tickets)
        min_tickets_to_keep = state.min_tickets_to_keep
    else:
        pending_tickets = ()
        min_tickets_to_keep = 0

    return PlayerView(
        my_name=me.name,
        my_index=player_index,
        my_hand=tuple(me.hand),
        my_tickets=tuple(me.destination_tickets),
        my_trains_remaining=me.trains_remaining,
        my_score=me.score,
        my_claimed_routes=tuple(me.claimed_routes),
        face_up_cards=tuple(state.face_up_cards),
        train_deck_size=len(state.train_deck) + len(state.train_discard),
        destination_deck_size=len(state.destination_deck),
        routes=dict(state.routes),
        all_claimed_routes=all_claimed_routes,
        opponents=opponents,
        phase=state.phase,
        current_player_name=state.current_player.name,
        is_my_turn=is_my_turn,
        last_round=state.last_round,
        num_players=state.num_players,
        pending_tickets=pending_tickets,
        min_tickets_to_keep=min_tickets_to_keep,
    )
