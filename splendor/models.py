"""
Core data models for Splendor.

Pure data structures — no logic here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class GemColor(str, Enum):
    DIAMOND  = "diamond"
    SAPPHIRE = "sapphire"
    EMERALD  = "emerald"
    RUBY     = "ruby"
    ONYX     = "onyx"
    GOLD     = "gold"   # wildcard — cannot be taken via take actions


# The 5 purchasable gem colors (gold is not in here)
GEM_COLORS: list[GemColor] = [
    GemColor.DIAMOND,
    GemColor.SAPPHIRE,
    GemColor.EMERALD,
    GemColor.RUBY,
    GemColor.ONYX,
]


class Phase(Enum):
    PLAYER_TURN           = auto()  # normal turn — player picks one action
    AWAITING_DISCARD      = auto()  # player took gems and now has > 10; must return some
    AWAITING_NOBLE_CHOICE = auto()  # multiple nobles qualify; player picks one
    GAME_OVER             = auto()


# ---------------------------------------------------------------------------
# Immutable card and noble definitions (static game content)
# ---------------------------------------------------------------------------

@dataclass
class CardDef:
    id:           int
    tier:         int
    bonus_color:  GemColor          # permanent gem bonus this card provides
    vp:           int
    cost:         dict              # dict[GemColor, int] — only non-zero entries needed


@dataclass
class NobleDef:
    id:           int
    vp:           int               # always 3 in standard Splendor
    requirements: dict              # dict[GemColor, int] — card-bonus counts needed


# ---------------------------------------------------------------------------
# Mutable game entities
# ---------------------------------------------------------------------------

@dataclass
class Player:
    name:      str
    gems:      dict = field(default_factory=dict)   # dict[GemColor, int]
    reserved:  list = field(default_factory=list)   # list[int] — card IDs
    purchased: list = field(default_factory=list)   # list[int] — card IDs
    nobles:    list = field(default_factory=list)   # list[int] — noble IDs


@dataclass
class GameState:
    """Single source of truth for the entire game."""
    players:    list   # list[Player]

    # Board: 4 face-up card slots per tier (None = empty slot)
    board:      dict   # dict[int, list[int | None]]  tier -> 4 slots

    # Remaining shuffled decks per tier
    decks:      dict   # dict[int, list[int]]  tier -> card IDs

    # Noble tiles available on the board
    nobles:     list   # list[int] — noble IDs

    # Gem token supply
    gem_supply: dict   # dict[GemColor, int]

    current_player_index: int   = 0
    phase:                Phase = Phase.PLAYER_TURN

    # True once any player ends a turn with ≥ 15 VP
    final_round: bool = False

    # Noble IDs the current player may choose from (AWAITING_NOBLE_CHOICE)
    pending_noble_choices: list = field(default_factory=list)

    @property
    def current_player(self) -> Player:
        return self.players[self.current_player_index]

    @property
    def num_players(self) -> int:
        return len(self.players)

    @property
    def is_game_over(self) -> bool:
        return self.phase == Phase.GAME_OVER
