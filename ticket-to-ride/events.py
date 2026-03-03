"""
Game events emitted by the engine.

Consumers (UI, AI, logging) subscribe to these; the engine never calls back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from models import Color, DestinationTicket, Player, RouteId


@dataclass(frozen=True)
class CardDrawnFromDeck:
    player_name: str


@dataclass(frozen=True)
class CardDrawnFromFaceUp:
    player_name: str
    card: Color
    slot: int               # 0-4


@dataclass(frozen=True)
class FaceUpCardReplaced:
    slot: int
    new_card: Color


@dataclass(frozen=True)
class FaceUpCardsReset:
    """All 5 face-up cards discarded and replaced (too many locomotives rule)."""
    new_cards: list[Color]


@dataclass(frozen=True)
class DestinationTicketsOffered:
    player_name: str
    tickets: list[DestinationTicket]
    min_keep: int


@dataclass(frozen=True)
class DestinationTicketsKept:
    player_name: str
    kept: list[DestinationTicket]
    returned: list[DestinationTicket]


@dataclass(frozen=True)
class RouteClaimed:
    player_name: str
    route_id: RouteId
    cards_spent: list[Color]
    points_scored: int


@dataclass(frozen=True)
class LastRoundTriggered:
    player_name: str
    trains_remaining: int


@dataclass(frozen=True)
class GameOver:
    scores: dict[str, int]      # player_name -> final score
    winner: str


Event = Union[
    CardDrawnFromDeck,
    CardDrawnFromFaceUp,
    FaceUpCardReplaced,
    FaceUpCardsReset,
    DestinationTicketsOffered,
    DestinationTicketsKept,
    RouteClaimed,
    LastRoundTriggered,
    GameOver,
]
