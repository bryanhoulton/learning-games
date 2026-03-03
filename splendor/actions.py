"""
All actions a player can submit to the engine.

One action = one engine method call. The runner dispatches each action
to the appropriate engine method after receiving it from an agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from models import GemColor


@dataclass(frozen=True)
class TakeDifferentGems:
    """Take 2 or 3 tokens of different colors."""
    colors: tuple   # tuple[GemColor, ...] — 2 or 3 distinct colors


@dataclass(frozen=True)
class TakeDoubleGem:
    """Take 2 tokens of the same color (requires ≥ 4 of that color in supply)."""
    color: GemColor


@dataclass(frozen=True)
class ReserveBoardCard:
    """Reserve a face-up card from the board."""
    card_id: int


@dataclass(frozen=True)
class ReserveDeckTop:
    """Reserve the top card from a tier deck."""
    tier: int


@dataclass(frozen=True)
class BuyCard:
    """Buy a card from the board or from your reserved cards."""
    card_id: int


@dataclass(frozen=True)
class DiscardGems:
    """Return gems to bring hand total to ≤ 10 (resolves AWAITING_DISCARD)."""
    gems: dict  # dict[GemColor, int]


@dataclass(frozen=True)
class ChooseNoble:
    """Pick one noble when multiple qualify (resolves AWAITING_NOBLE_CHOICE)."""
    noble_id: int


Action = Union[
    TakeDifferentGems,
    TakeDoubleGem,
    ReserveBoardCard,
    ReserveDeckTop,
    BuyCard,
    DiscardGems,
    ChooseNoble,
]
