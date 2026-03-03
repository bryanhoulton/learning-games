"""
Core data models for Dominion.

Pure data structures — no logic here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class CardName(str, Enum):
    # Base treasure cards
    COPPER   = "Copper"
    SILVER   = "Silver"
    GOLD     = "Gold"
    # Base victory cards
    ESTATE   = "Estate"
    DUCHY    = "Duchy"
    PROVINCE = "Province"
    # Base curse
    CURSE    = "Curse"
    # First Game kingdom cards
    CELLAR    = "Cellar"
    MARKET    = "Market"
    MILITIA   = "Militia"
    MINE      = "Mine"
    MOAT      = "Moat"
    REMODEL   = "Remodel"
    SMITHY    = "Smithy"
    VILLAGE   = "Village"
    WOODCUTTER = "Woodcutter"
    WORKSHOP  = "Workshop"


class CardType(Enum):
    TREASURE = auto()
    VICTORY  = auto()
    CURSE    = auto()
    ACTION   = auto()
    REACTION = auto()   # Moat: can block attacks


class Phase(Enum):
    ACTION  = auto()    # active player's action phase
    BUY     = auto()    # active player's buy phase

    # Multi-step card resolution (player must call a resolve_* method)
    AWAITING_CELLAR_DISCARD   = auto()   # current player discarding for Cellar
    AWAITING_MINE_TRASH       = auto()   # current player trashing treasure for Mine
    AWAITING_MINE_GAIN        = auto()   # current player gaining treasure for Mine
    AWAITING_REMODEL_TRASH    = auto()   # current player trashing card for Remodel
    AWAITING_REMODEL_GAIN     = auto()   # current player gaining card for Remodel
    AWAITING_WORKSHOP_GAIN    = auto()   # current player gaining card for Workshop

    # Attack resolution (a *different* player must act)
    AWAITING_MILITIA_DISCARD  = auto()   # militia_targets[0] must discard to ≤3

    GAME_OVER = auto()


# ---------------------------------------------------------------------------
# Immutable card definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CardDef:
    name: CardName
    cost: int
    types: frozenset                # frozenset[CardType]

    # Static values
    vp: int = 0        # victory points (for scoring)
    coins: int = 0     # treasure value when played

    # Immediate effects when played as an action
    plus_actions: int = 0
    plus_cards:   int = 0
    plus_buys:    int = 0
    plus_coins:   int = 0

    # Flags
    is_attack:   bool = False
    is_reaction: bool = False


# ---------------------------------------------------------------------------
# Mutable game entities
# ---------------------------------------------------------------------------

@dataclass
class Player:
    name: str
    draw_pile: list = field(default_factory=list)   # list[CardName]
    hand:      list = field(default_factory=list)   # list[CardName]
    discard:   list = field(default_factory=list)   # list[CardName]
    played:    list = field(default_factory=list)   # cards played this turn

    def all_cards(self) -> list:
        """Every card owned by this player, regardless of location."""
        return self.draw_pile + self.hand + self.discard + self.played


@dataclass
class GameState:
    """Single source of truth for the entire game."""
    players: list           # list[Player]
    supply:  dict           # dict[CardName, int]  — pile name -> count remaining
    trash:   list           # list[CardName]

    current_player_index: int   = 0
    phase:                Phase = Phase.ACTION

    # Per-turn resources
    actions: int = 1
    buys:    int = 1
    coins:   int = 0

    # Pending decision metadata
    pending_gain_max_cost:  int  = 0      # max cost for Mine / Remodel / Workshop gain
    pending_gain_to_hand:   bool = False  # True for Mine (gains to hand, not discard)

    # Militia: ordered list of player indices still needing to discard
    militia_targets: list = field(default_factory=list)   # list[int]

    @property
    def current_player(self) -> Player:
        return self.players[self.current_player_index]

    @property
    def num_players(self) -> int:
        return len(self.players)

    @property
    def is_game_over(self) -> bool:
        return self.phase == Phase.GAME_OVER
