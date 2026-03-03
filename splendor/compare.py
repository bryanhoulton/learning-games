"""
Compare LLMAgent with and without strategy guidance across multiple seeds.
Reports VP and turn count for each condition.
"""

import sys
from agent import LLMAgent, RandomAgent
from engine import GameEngine
from events import TurnEnded
from cards import CARD_REGISTRY, NOBLE_REGISTRY
from models import Phase
from actions import (
    BuyCard, ChooseNoble, DiscardGems, ReserveBoardCard,
    ReserveDeckTop, TakeDoubleGem, TakeDifferentGems,
)
from view import get_player_view


def _execute(engine, actor, action):
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


def run(agents: dict, seed: int) -> tuple[int, int]:
    """Returns (llm_vp, llm_turns)."""
    player_names = list(agents.keys())
    engine = GameEngine.new_game(player_names, seed=seed)
    state = engine.state

    llm_name = next(n for n, a in agents.items() if isinstance(a, LLMAgent))
    turn_count = [0]

    def count_turns(event):
        if isinstance(event, TurnEnded) and event.player_name == llm_name:
            turn_count[0] += 1

    engine.subscribe(count_turns)

    for name, agent in agents.items():
        agent.on_game_start(engine, name)

    while not state.is_game_over:
        actor = state.current_player.name
        view = get_player_view(state, actor)
        action = agents[actor].choose_action(view)
        _execute(engine, actor, action)

    llm = next(p for p in state.players if p.name == llm_name)
    vp = (
        sum(CARD_REGISTRY[c].vp for c in llm.purchased)
        + sum(NOBLE_REGISTRY[n].vp for n in llm.nobles)
    )
    return vp, turn_count[0]


seeds = [1, 2, 3, 4, 5, 10, 42, 99]

print(f"{'seed':>5}  {'plain VP':>8}  {'plain turns':>11}  {'strat VP':>8}  {'strat turns':>11}  {'VP diff':>7}  {'turns diff':>10}")
print("-" * 72)

for seed in seeds:
    vp1, t1 = run({"LLM": LLMAgent(strategy=False), "Random": RandomAgent()}, seed)
    vp2, t2 = run({"LLM": LLMAgent(strategy=True),  "Random": RandomAgent()}, seed)
    vdiff = vp2 - vp1
    tdiff = t2 - t1
    print(f"{seed:>5}  {vp1:>8}  {t1:>11}  {vp2:>8}  {t2:>11}  {vdiff:>+7}  {tdiff:>+10}")

print()
