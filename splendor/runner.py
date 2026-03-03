"""
Splendor game runner.

Orchestrates a full game between agents, feeding each agent only its
PlayerView and dispatching the returned Action to the engine.

Usage:
    python runner.py           # 4 random agents
    python runner.py 42        # seeded run
"""

from __future__ import annotations

import sys
from typing import Optional

from actions import (
    Action,
    BuyCard,
    ChooseNoble,
    DiscardGems,
    ReserveBoardCard,
    ReserveDeckTop,
    TakeDoubleGem,
    TakeDifferentGems,
)
from agent import Agent, RandomAgent
from engine import GameEngine
from models import GameState, Phase
from view import get_player_view


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------

def _execute(engine: GameEngine, actor: str, action: Action) -> None:
    """Translate an Action value into the appropriate engine method call."""
    if isinstance(action, TakeDifferentGems):
        engine.take_different_gems(actor, list(action.colors))
    elif isinstance(action, TakeDoubleGem):
        engine.take_double_gem(actor, action.color)
    elif isinstance(action, ReserveBoardCard):
        engine.reserve_board_card(actor, action.card_id)
    elif isinstance(action, ReserveDeckTop):
        engine.reserve_deck_top(actor, action.tier)
    elif isinstance(action, BuyCard):
        engine.buy_card(actor, action.card_id)
    elif isinstance(action, DiscardGems):
        engine.discard_gems(actor, action.gems)
    elif isinstance(action, ChooseNoble):
        engine.choose_noble(actor, action.noble_id)
    else:
        raise ValueError(f"Unknown action type: {type(action)}")


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log_action(actor: str, action: Action) -> None:
    name = type(action).__name__
    if isinstance(action, TakeDifferentGems):
        colors = ", ".join(c.value for c in action.colors)
        print(f"  {actor}: {name}({colors})")
    elif isinstance(action, TakeDoubleGem):
        print(f"  {actor}: {name}({action.color.value})")
    elif isinstance(action, (ReserveBoardCard, BuyCard)):
        print(f"  {actor}: {name}(card={action.card_id})")
    elif isinstance(action, ReserveDeckTop):
        print(f"  {actor}: {name}(tier={action.tier})")
    elif isinstance(action, DiscardGems):
        parts = ", ".join(f"{c.value}:{v}" for c, v in action.gems.items() if v > 0)
        print(f"  {actor}: {name}({{{parts}}})")
    elif isinstance(action, ChooseNoble):
        print(f"  {actor}: {name}(noble={action.noble_id})")
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

    # Let agents subscribe to events and receive initial game context
    for name, agent in agents.items():
        agent.on_game_start(engine, name)

    if verbose:
        print(f"=== New Splendor game: {', '.join(player_names)} ===\n")

    turn = 0
    while not state.is_game_over:
        actor = state.current_player.name

        if state.phase == Phase.PLAYER_TURN:
            turn += 1
            if verbose:
                vp_str = "  ".join(
                    f"{p.name}:{engine._player_vp(p)}vp"
                    for p in state.players
                )
                print(f"-- Turn {turn}: {actor}  [{vp_str}]")

        view = get_player_view(state, actor)
        action = agents[actor].choose_action(view)

        if verbose:
            reasoning = getattr(agents[actor], "last_reasoning", None)
            if reasoning:
                for line in reasoning.splitlines():
                    print(f"    {line}")
            _log_action(actor, action)

        _execute(engine, actor, action)

    if verbose:
        print("\n=== Game over ===")
        for p in sorted(state.players, key=lambda p: -engine._player_vp(p)):
            print(f"  {p.name}: {engine._player_vp(p)} VP")
        scores = {p.name: engine._player_vp(p) for p in state.players}
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
