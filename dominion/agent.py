"""
Agent interface and built-in agents for Dominion.

Agents receive a PlayerView (never raw GameState) and return an Action.
They must not receive or retain any reference to the engine or game state.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod

from actions import (
    Action,
    BuyCard,
    EndActionPhase,
    EndBuyPhase,
    PlayAction,
    PlayTreasure,
    ResolveCellar,
    ResolveMilitiaDiscard,
    ResolveMineGain,
    ResolveMineTrash,
    ResolveRemodelGain,
    ResolveRemodelTrash,
    ResolveWorkshop,
)
from cards import CARD_REGISTRY
from models import CardType, Phase
from view import PlayerView


class Agent(ABC):
    """
    Base class for all Dominion agents (human, heuristic, LLM, etc.).

    choose_action is called once per decision point. The agent returns
    exactly one Action; the runner executes it and calls again if more
    decisions are needed in the same turn.
    """

    @abstractmethod
    def choose_action(self, view: PlayerView) -> Action:
        ...


# ---------------------------------------------------------------------------
# Random agent
# ---------------------------------------------------------------------------

class RandomAgent(Agent):
    """Picks uniformly at random from legal options at each decision point."""

    def choose_action(self, view: PlayerView) -> Action:
        phase = view.phase
        dispatch = {
            Phase.ACTION:                   self._action_phase,
            Phase.BUY:                      self._buy_phase,
            Phase.AWAITING_CELLAR_DISCARD:  self._cellar,
            Phase.AWAITING_MINE_TRASH:      self._mine_trash,
            Phase.AWAITING_MINE_GAIN:       self._mine_gain,
            Phase.AWAITING_REMODEL_TRASH:   self._remodel_trash,
            Phase.AWAITING_REMODEL_GAIN:    self._remodel_gain,
            Phase.AWAITING_WORKSHOP_GAIN:   self._workshop,
            Phase.AWAITING_MILITIA_DISCARD: self._militia_discard,
        }
        return dispatch[phase](view)

    # ------------------------------------------------------------------
    # Action phase
    # ------------------------------------------------------------------

    def _action_phase(self, view: PlayerView) -> Action:
        if view.actions > 0:
            playable = [
                c for c in view.your_hand
                if CardType.ACTION in CARD_REGISTRY[c].types
                or CardType.REACTION in CARD_REGISTRY[c].types
            ]
            if playable:
                return PlayAction(random.choice(playable))
        return EndActionPhase()

    # ------------------------------------------------------------------
    # Buy phase
    # ------------------------------------------------------------------

    def _buy_phase(self, view: PlayerView) -> Action:
        # Play treasures one at a time before buying
        treasures = [
            c for c in view.your_hand
            if CardType.TREASURE in CARD_REGISTRY[c].types
        ]
        if treasures:
            return PlayTreasure(random.choice(treasures))

        # Buy a random affordable card (if any buys left)
        if view.buys > 0:
            affordable = [
                name for name, count in view.supply.items()
                if count > 0 and CARD_REGISTRY[name].cost <= view.coins
            ]
            if affordable:
                return BuyCard(random.choice(affordable))

        return EndBuyPhase()

    # ------------------------------------------------------------------
    # Card resolutions
    # ------------------------------------------------------------------

    def _cellar(self, view: PlayerView) -> ResolveCellar:
        # Discard a random subset of hand (any size, including empty)
        n = random.randint(0, len(view.your_hand))
        chosen = tuple(random.sample(list(view.your_hand), n))
        return ResolveCellar(discard_cards=chosen)

    def _mine_trash(self, view: PlayerView) -> ResolveMineTrash:
        treasures = [
            c for c in view.your_hand
            if CardType.TREASURE in CARD_REGISTRY[c].types
        ]
        return ResolveMineTrash(random.choice(treasures))

    def _mine_gain(self, view: PlayerView) -> ResolveMineGain:
        valid = [
            name for name, count in view.supply.items()
            if count > 0
            and CARD_REGISTRY[name].cost <= view.pending_gain_max_cost
            and CardType.TREASURE in CARD_REGISTRY[name].types
        ]
        return ResolveMineGain(random.choice(valid))

    def _remodel_trash(self, view: PlayerView) -> ResolveRemodelTrash:
        return ResolveRemodelTrash(random.choice(list(view.your_hand)))

    def _remodel_gain(self, view: PlayerView) -> ResolveRemodelGain:
        valid = [
            name for name, count in view.supply.items()
            if count > 0 and CARD_REGISTRY[name].cost <= view.pending_gain_max_cost
        ]
        return ResolveRemodelGain(random.choice(valid))

    def _workshop(self, view: PlayerView) -> ResolveWorkshop:
        valid = [
            name for name, count in view.supply.items()
            if count > 0 and CARD_REGISTRY[name].cost <= 4
        ]
        return ResolveWorkshop(random.choice(valid))

    def _militia_discard(self, view: PlayerView) -> ResolveMilitiaDiscard:
        n_discard = max(0, len(view.your_hand) - 3)
        chosen = tuple(random.sample(list(view.your_hand), n_discard))
        return ResolveMilitiaDiscard(discard_cards=chosen)
