"""
Game events emitted by the engine.

Consumers (UI, AI, logging) subscribe to these; the engine never calls back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from models import CardName


@dataclass(frozen=True)
class ActionPlayed:
    player_name: str
    card: CardName


@dataclass(frozen=True)
class TreasurePlayed:
    player_name: str
    card: CardName
    coins_added: int
    total_coins: int


@dataclass(frozen=True)
class CardsDrawn:
    player_name: str
    count: int


@dataclass(frozen=True)
class CardBought:
    player_name: str
    card: CardName
    cost: int


@dataclass(frozen=True)
class CardGained:
    """A card was gained (from supply to player's discard or hand)."""
    player_name: str
    card: CardName
    destination: str    # "discard" or "hand"


@dataclass(frozen=True)
class CardTrashed:
    player_name: str
    card: CardName


@dataclass(frozen=True)
class CardsDiscarded:
    """One or more cards discarded from hand (Cellar / Militia)."""
    player_name: str
    cards: list     # list[CardName]


@dataclass(frozen=True)
class MilitiaAttack:
    attacker: str
    targets: list   # list[str] — player names who must discard


@dataclass(frozen=True)
class MilitiaBlocked:
    """A player revealed Moat to block the Militia attack."""
    attacker: str
    defender: str


@dataclass(frozen=True)
class TurnStarted:
    player_name: str


@dataclass(frozen=True)
class TurnEnded:
    player_name: str


@dataclass(frozen=True)
class GameOver:
    scores: dict    # dict[str, int] — player_name -> final VP
    winner: str     # name of highest scorer (ties go to the last tied player)


Event = Union[
    ActionPlayed,
    TreasurePlayed,
    CardsDrawn,
    CardBought,
    CardGained,
    CardTrashed,
    CardsDiscarded,
    MilitiaAttack,
    MilitiaBlocked,
    TurnStarted,
    TurnEnded,
    GameOver,
]
