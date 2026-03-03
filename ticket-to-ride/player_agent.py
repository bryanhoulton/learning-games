"""
PlayerAgent abstraction — the interface all player types must implement.

Action types cover every legal move a player can make.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Union

from events import Event
from models import Color, RouteId
from player_view import PlayerView


# ---------------------------------------------------------------------------
# Action types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DrawCardAction:
    slot: Optional[int]     # None = blind deck draw; 0-4 = face-up slot


@dataclass(frozen=True)
class ClaimRouteAction:
    route_id: RouteId
    cards: tuple[Color, ...]


@dataclass(frozen=True)
class DrawTicketsAction:
    pass


@dataclass(frozen=True)
class KeepTicketsAction:
    ticket_ids: tuple[int, ...]


PlayerAction = Union[DrawCardAction, ClaimRouteAction, DrawTicketsAction, KeepTicketsAction]


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class PlayerAgent(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """The player's name — must match the name registered with the engine."""

    @abstractmethod
    def choose_action(self, view: PlayerView, error: Optional[str] = None) -> PlayerAction:
        """
        Return the next action given the current observable game state.

        `error` is set when the previous action was rejected by the engine.
        The phase in view determines valid action types:
          CHOOSE_ACTION   → DrawCardAction | ClaimRouteAction | DrawTicketsAction
          DRAWING_CARDS   → DrawCardAction (no face-up wild)
          KEEPING_TICKETS → KeepTicketsAction
        """

    def on_event(self, event: Event) -> None:
        """Called for every game event. Default: no-op."""
