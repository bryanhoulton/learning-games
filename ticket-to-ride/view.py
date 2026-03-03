"""
Player-scoped view of game state for Ticket to Ride.

get_player_view() produces a PlayerView containing only the information
a real player at the table would have. Use this to feed bots and LLMs —
never hand them the raw GameState.

What is and isn't visible in Ticket to Ride:
  - Your own train cards (hand)         → fully visible
  - Other players' train cards          → size only (you can count their pile)
  - Your own destination tickets        → fully visible
  - Other players' destination tickets  → count only (you cannot see the routes)
  - Face-up train cards                 → fully visible
  - Train deck                          → size only (face-down)
  - Destination deck                    → size only (face-down)
  - Claimed routes (who owns what)      → fully visible
  - Trains remaining per player         → fully visible
  - Scores (route points, running)      → fully visible
  - Last-round flag                     → fully visible
  - Pending tickets (KEEPING_TICKETS)   → only visible to the player being offered them
"""

from __future__ import annotations

from dataclasses import dataclass

from models import Color, DestinationTicket, GameState, Phase, RouteId


@dataclass(frozen=True)
class OtherPlayerView:
    name: str
    color: str
    hand_size: int                  # you can count their cards; you cannot see them
    ticket_count: int               # you can count; you cannot see which routes
    trains_remaining: int           # fully public
    score: int                      # running route-point score, fully public
    claimed_routes: tuple           # tuple[RouteId, ...] — fully public


@dataclass(frozen=True)
class PlayerView:
    # ---- your own info ----
    your_name: str
    your_hand: tuple                # tuple[Color, ...] — only you see this
    your_tickets: tuple             # tuple[DestinationTicket, ...] — only you see this
    your_claimed_routes: tuple      # tuple[RouteId, ...]
    your_trains_remaining: int
    your_score: int

    # ---- public board ----
    face_up_cards: tuple            # tuple[Color, ...] — always visible
    train_deck_size: int            # count only
    destination_deck_size: int      # count only
    all_claimed_routes: dict        # dict[RouteId, str] — route -> owner name
    others: tuple                   # tuple[OtherPlayerView, ...]

    # ---- turn state ----
    current_player_name: str
    phase: Phase
    last_round: bool

    # ---- pending tickets (only populated when it's your KEEPING_TICKETS phase) ----
    pending_tickets: tuple          # tuple[DestinationTicket, ...] — empty when not your decision
    min_tickets_to_keep: int


def get_player_view(state: GameState, player_name: str) -> PlayerView:
    """
    Return the subset of GameState that *player_name* is allowed to see.
    Raises ValueError if the player name is not in the game.
    """
    me = next((p for p in state.players if p.name == player_name), None)
    if me is None:
        raise ValueError(f"No player named {player_name!r} in this game.")

    others = tuple(
        OtherPlayerView(
            name=p.name,
            color=p.color,
            hand_size=len(p.hand),
            ticket_count=len(p.destination_tickets),
            trains_remaining=p.trains_remaining,
            score=p.score,
            claimed_routes=tuple(p.claimed_routes),
        )
        for p in state.players
        if p.name != player_name
    )

    # Map RouteId -> owner name (not index) for public route ownership
    all_claimed = {
        route_id: state.players[idx].name
        for route_id, idx in state.claimed_routes.items()
    }

    # Pending tickets are only shown to the player who must make the decision
    is_my_ticket_decision = (
        state.phase == Phase.KEEPING_TICKETS
        and state.current_player.name == player_name
    )

    return PlayerView(
        your_name=player_name,
        your_hand=tuple(me.hand),
        your_tickets=tuple(me.destination_tickets),
        your_claimed_routes=tuple(me.claimed_routes),
        your_trains_remaining=me.trains_remaining,
        your_score=me.score,
        face_up_cards=tuple(state.face_up_cards),
        train_deck_size=len(state.train_deck),
        destination_deck_size=len(state.destination_deck),
        all_claimed_routes=all_claimed,
        others=others,
        current_player_name=state.current_player.name,
        phase=state.phase,
        last_round=state.last_round,
        pending_tickets=tuple(state.pending_tickets) if is_my_ticket_decision else (),
        min_tickets_to_keep=state.min_tickets_to_keep if is_my_ticket_decision else 0,
    )
