"""
Dominion game runner.

Orchestrates a full game between agents, feeding each agent only its
PlayerView and dispatching the returned Action to the engine.

Usage:
    python runner.py
"""

from __future__ import annotations

import sys
from typing import Optional

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
from agent import Agent, RandomAgent
from engine import GameEngine
from models import GameState, Phase
from view import PlayerView, get_player_view


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------

def _execute(engine: GameEngine, actor: str, action: Action) -> None:
    """Translate an Action value into the appropriate engine method call."""
    if isinstance(action, PlayAction):
        engine.play_action(actor, action.card)
    elif isinstance(action, EndActionPhase):
        engine.end_action_phase(actor)
    elif isinstance(action, PlayTreasure):
        engine.play_treasure(actor, action.card)
    elif isinstance(action, BuyCard):
        engine.buy_card(actor, action.card)
    elif isinstance(action, EndBuyPhase):
        engine.end_buy_phase(actor)
    elif isinstance(action, ResolveCellar):
        engine.resolve_cellar(actor, list(action.discard_cards))
    elif isinstance(action, ResolveMineTrash):
        engine.resolve_mine_trash(actor, action.card)
    elif isinstance(action, ResolveMineGain):
        engine.resolve_mine_gain(actor, action.card)
    elif isinstance(action, ResolveRemodelTrash):
        engine.resolve_remodel_trash(actor, action.card)
    elif isinstance(action, ResolveRemodelGain):
        engine.resolve_remodel_gain(actor, action.card)
    elif isinstance(action, ResolveWorkshop):
        engine.resolve_workshop(actor, action.card)
    elif isinstance(action, ResolveMilitiaDiscard):
        engine.resolve_militia_discard(actor, list(action.discard_cards))
    else:
        raise ValueError(f"Unknown action type: {type(action)}")


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log_action(actor: str, action: Action) -> None:
    name = type(action).__name__
    if isinstance(action, (PlayAction, PlayTreasure,
                           BuyCard, ResolveMineTrash, ResolveMineGain,
                           ResolveRemodelTrash, ResolveRemodelGain, ResolveWorkshop)):
        print(f"  {actor}: {name}({action.card.value})")
    elif isinstance(action, (ResolveCellar, ResolveMilitiaDiscard)):
        cards = ", ".join(c.value for c in action.discard_cards) or "none"
        print(f"  {actor}: {name}([{cards}])")
    else:
        print(f"  {actor}: {name}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_game(
    agents: dict,               # dict[str, Agent]  player_name -> agent
    seed: Optional[int] = None,
    verbose: bool = True,
) -> GameState:
    """
    Run a complete game. Returns the final GameState.

    agents keys must match the player names passed to new_game.
    """
    player_names = list(agents.keys())
    engine = GameEngine.new_game(player_names, seed=seed)
    state = engine.state

    if verbose:
        print(f"=== New game: {', '.join(player_names)} ===\n")

    turn = 0
    last_turn_actor = None
    while not state.is_game_over:
        # Determine who must act right now
        if state.phase == Phase.AWAITING_MILITIA_DISCARD:
            actor = state.players[state.militia_targets[0]].name
        else:
            actor = state.current_player.name

        # Log turn header exactly once per player turn (guard against re-entry
        # when phase stays ACTION after playing a card like Moat or Village)
        if (state.phase == Phase.ACTION
                and actor == state.current_player.name
                and actor != last_turn_actor):
            turn += 1
            last_turn_actor = actor
            if verbose:
                supply_str = "  ".join(
                    f"{k.value}:{v}"
                    for k, v in state.supply.items()
                    if v > 0 and k.value in ("Province", "Duchy", "Estate", "Curse")
                )
                print(f"-- Turn {turn}: {actor}  [{supply_str}]")

        # Build view and ask agent
        view = get_player_view(state, actor)
        action = agents[actor].choose_action(view)

        if verbose:
            _log_action(actor, action)

        _execute(engine, actor, action)

        # When the turn ends, clear the guard so the next player triggers a header
        if state.current_player.name != last_turn_actor:
            last_turn_actor = None

    # Final scores
    if verbose:
        print("\n=== Game over ===")
        scores = {
            p.name: sum(
                __import__('cards').CARD_REGISTRY[c].vp
                for c in p.all_cards()
            )
            for p in state.players
        }
        for name, vp in sorted(scores.items(), key=lambda x: -x[1]):
            print(f"  {name}: {vp} VP")
        winner = max(scores, key=lambda n: scores[n])
        print(f"\nWinner: {winner}")

    return state


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None

    players = ["Alice", "Bob", "Carol", "Dave"]
    agents = {name: RandomAgent() for name in players}

    run_game(agents, seed=seed, verbose=True)
