"""
Core data models for Ticket to Ride.

Pure data structures — no logic here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Color(Enum):
    RED = "red"
    BLUE = "blue"
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    PINK = "pink"
    WHITE = "white"
    BLACK = "black"
    WILD = "wild"          # locomotive / rainbow card


class Phase(Enum):
    """Turn phases for the active player."""
    CHOOSE_ACTION = auto()          # player has not yet committed to an action
    DRAWING_CARDS = auto()          # player drew one open card; must draw second
    KEEPING_TICKETS = auto()        # player must decide which tickets to keep
    GAME_OVER = auto()


class ActionType(Enum):
    DRAW_TRAIN_CARD_OPEN = auto()   # draw one of the 5 face-up cards
    DRAW_TRAIN_CARD_DECK = auto()   # draw blind from deck
    DRAW_DESTINATION_TICKETS = auto()
    CLAIM_ROUTE = auto()
    KEEP_DESTINATION_TICKETS = auto()


# ---------------------------------------------------------------------------
# Immutable value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RouteId:
    """Unique identifier for a route (city_a always < city_b lexicographically)."""
    city_a: str
    city_b: str
    index: int = 0          # for double routes between the same cities

    def __post_init__(self) -> None:
        if self.city_a > self.city_b:
            a, b = self.city_a, self.city_b
            object.__setattr__(self, "city_a", b)
            object.__setattr__(self, "city_b", a)


@dataclass(frozen=True)
class Route:
    id: RouteId
    city_a: str
    city_b: str
    length: int
    color: Color            # Color.WILD means grey / any colour
    index: int = 0          # 0 for single routes; 0 or 1 for double routes

    # Points awarded when claiming this route (standard scoring table)
    @property
    def points(self) -> int:
        return {1: 1, 2: 2, 3: 4, 4: 7, 5: 10, 6: 15}[self.length]


@dataclass(frozen=True)
class DestinationTicket:
    id: int
    city_a: str
    city_b: str
    points: int             # positive = bonus if complete, negative penalty if not


# ---------------------------------------------------------------------------
# Mutable game entities
# ---------------------------------------------------------------------------

@dataclass
class Player:
    name: str
    color: str                                      # player token colour (not card colour)
    hand: list[Color] = field(default_factory=list)
    destination_tickets: list[DestinationTicket] = field(default_factory=list)
    claimed_routes: list[RouteId] = field(default_factory=list)
    trains_remaining: int = 45
    score: int = 0                                  # running score (route points only)

    def card_count(self, color: Optional[Color] = None) -> int:
        if color is None:
            return len(self.hand)
        return self.hand.count(color)


@dataclass
class GameState:
    """
    Single source of truth for the entire game.

    The engine reads and writes only this object.
    """
    players: list[Player]
    routes: dict[RouteId, Route]                    # full board definition
    destination_tickets: list[DestinationTicket]    # full deck definition

    # Decks & face-up cards
    train_deck: list[Color] = field(default_factory=list)
    train_discard: list[Color] = field(default_factory=list)
    face_up_cards: list[Color] = field(default_factory=list)   # always 5 when possible

    destination_deck: list[DestinationTicket] = field(default_factory=list)

    # Ownership: RouteId -> player index
    claimed_routes: dict[RouteId, int] = field(default_factory=dict)

    # Turn tracking
    current_player_index: int = 0
    phase: Phase = Phase.CHOOSE_ACTION
    last_round: bool = False                        # triggered when a player has ≤2 trains
    last_round_trigger_player: Optional[int] = None

    # During DRAWING_CARDS phase: track first draw
    first_draw_was_wild: bool = False               # if True, second draw must be non-open-wild

    # During KEEPING_TICKETS phase: tickets currently offered to the player
    pending_tickets: list[DestinationTicket] = field(default_factory=list)
    min_tickets_to_keep: int = 1

    @property
    def current_player(self) -> Player:
        return self.players[self.current_player_index]

    @property
    def num_players(self) -> int:
        return len(self.players)

    @property
    def is_game_over(self) -> bool:
        return self.phase == Phase.GAME_OVER
