"""
All actions a player can submit to the engine.

One action = one engine method call. The runner dispatches each action
to the appropriate engine method after receiving it from an agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from models import CardName


@dataclass(frozen=True)
class PlayAction:
    card: CardName


@dataclass(frozen=True)
class EndActionPhase:
    pass


@dataclass(frozen=True)
class PlayTreasure:
    card: CardName


@dataclass(frozen=True)
class BuyCard:
    card: CardName


@dataclass(frozen=True)
class EndBuyPhase:
    pass


@dataclass(frozen=True)
class ResolveCellar:
    discard_cards: tuple    # tuple[CardName, ...]


@dataclass(frozen=True)
class ResolveMineTrash:
    card: CardName


@dataclass(frozen=True)
class ResolveMineGain:
    card: CardName


@dataclass(frozen=True)
class ResolveRemodelTrash:
    card: CardName


@dataclass(frozen=True)
class ResolveRemodelGain:
    card: CardName


@dataclass(frozen=True)
class ResolveWorkshop:
    card: CardName


@dataclass(frozen=True)
class ResolveMilitiaDiscard:
    discard_cards: tuple    # tuple[CardName, ...]


Action = Union[
    PlayAction,
    EndActionPhase,
    PlayTreasure,
    BuyCard,
    EndBuyPhase,
    ResolveCellar,
    ResolveMineTrash,
    ResolveMineGain,
    ResolveRemodelTrash,
    ResolveRemodelGain,
    ResolveWorkshop,
    ResolveMilitiaDiscard,
]
