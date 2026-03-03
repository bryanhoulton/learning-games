"""
Game events emitted by the engine.

Consumers (UI, AI, logging) subscribe to these; the engine never calls back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class GemsTaken:
    player_name: str
    gems: dict          # dict[GemColor, int] — what was taken


@dataclass(frozen=True)
class GemsReturned:
    """Gems returned to supply (discard-to-10 resolution)."""
    player_name: str
    gems: dict          # dict[GemColor, int]


@dataclass(frozen=True)
class CardReserved:
    player_name: str
    card_id:     int
    tier:        int    # which tier (useful when deck-top was reserved)
    gold_taken:  bool   # whether a gold token was received


@dataclass(frozen=True)
class CardBought:
    player_name: str
    card_id:     int
    gems_paid:   dict   # dict[GemColor, int] — actual tokens returned to supply
    gold_used:   int    # number of gold wildcards spent


@dataclass(frozen=True)
class NobleVisited:
    player_name: str
    noble_id:    int


@dataclass(frozen=True)
class TurnStarted:
    player_name: str


@dataclass(frozen=True)
class TurnEnded:
    player_name: str
    vp:          int    # player's VP at end of turn


@dataclass(frozen=True)
class GameOver:
    scores: dict    # dict[str, int] — player_name -> final VP
    winner: str


Event = Union[
    GemsTaken,
    GemsReturned,
    CardReserved,
    CardBought,
    NobleVisited,
    TurnStarted,
    TurnEnded,
    GameOver,
]
