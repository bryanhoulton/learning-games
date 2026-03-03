"""
LLM-backed Dominion agent via OpenRouter.

The agent receives only a PlayerView (no raw GameState) and returns an Action.
It builds a natural-language description of the game state, enumerates legal
actions as a numbered list, and asks the LLM to pick one.

Usage:
    OPENROUTER_API_KEY=sk-... python llm_agent.py [seed]
"""

from __future__ import annotations

import json
import os
import random
import sys
from typing import Optional

from openai import OpenAI

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
from cards import CARD_REGISTRY
from models import CardName, CardType, Phase
from runner import run_game
from view import PlayerView


# ---------------------------------------------------------------------------
# Card descriptions (for the LLM prompt)
# ---------------------------------------------------------------------------

CARD_DESCRIPTIONS: dict[CardName, str] = {
    CardName.COPPER:     "+1 coin when played",
    CardName.SILVER:     "+2 coins when played",
    CardName.GOLD:       "+3 coins when played",
    CardName.ESTATE:     "1 Victory Point",
    CardName.DUCHY:      "3 Victory Points",
    CardName.PROVINCE:   "6 Victory Points",
    CardName.CURSE:      "-1 Victory Point",
    CardName.CELLAR:     "+1 Action; discard any cards, draw one per discarded",
    CardName.MARKET:     "+1 Card, +1 Action, +1 Buy, +1 Coin",
    CardName.MILITIA:    "+2 Coins; each opponent discards down to 3 cards",
    CardName.MINE:       "Trash a Treasure; gain a Treasure to hand costing up to 3 more",
    CardName.MOAT:       "+2 Cards; reveals to block Attack cards",
    CardName.REMODEL:    "Trash a card; gain a card costing up to 2 more",
    CardName.SMITHY:     "+3 Cards",
    CardName.VILLAGE:    "+1 Card, +2 Actions",
    CardName.WOODCUTTER: "+1 Buy, +2 Coins",
    CardName.WORKSHOP:   "Gain a card costing up to 4 (free)",
}


# ---------------------------------------------------------------------------
# Legal action enumeration (from a PlayerView)
# ---------------------------------------------------------------------------

def get_legal_actions(view: PlayerView) -> list[Action]:
    """Enumerate all legal actions for the current phase (excluding multi-card choices)."""
    phase = view.phase
    actions: list[Action] = []

    if phase == Phase.ACTION:
        if view.actions > 0:
            seen: set[CardName] = set()
            for card in view.your_hand:
                if card not in seen:
                    defn = CARD_REGISTRY[card]
                    if CardType.ACTION in defn.types or CardType.REACTION in defn.types:
                        actions.append(PlayAction(card))
                        seen.add(card)
        actions.append(EndActionPhase())

    elif phase == Phase.BUY:
        seen = set()
        for card in view.your_hand:
            if card not in seen and CardType.TREASURE in CARD_REGISTRY[card].types:
                actions.append(PlayTreasure(card))
                seen.add(card)
        if view.buys > 0:
            for name in sorted(view.supply, key=lambda n: CARD_REGISTRY[n].cost):
                if view.supply[name] > 0 and CARD_REGISTRY[name].cost <= view.coins:
                    actions.append(BuyCard(name))
        actions.append(EndBuyPhase())

    elif phase == Phase.AWAITING_MINE_TRASH:
        seen = set()
        for card in view.your_hand:
            if card not in seen and CardType.TREASURE in CARD_REGISTRY[card].types:
                actions.append(ResolveMineTrash(card))
                seen.add(card)

    elif phase == Phase.AWAITING_MINE_GAIN:
        for name in sorted(view.supply, key=lambda n: CARD_REGISTRY[n].cost, reverse=True):
            if (view.supply[name] > 0
                    and CARD_REGISTRY[name].cost <= view.pending_gain_max_cost
                    and CardType.TREASURE in CARD_REGISTRY[name].types):
                actions.append(ResolveMineGain(name))

    elif phase == Phase.AWAITING_REMODEL_TRASH:
        seen = set()
        for card in view.your_hand:
            if card not in seen:
                actions.append(ResolveRemodelTrash(card))
                seen.add(card)

    elif phase == Phase.AWAITING_REMODEL_GAIN:
        for name in sorted(view.supply, key=lambda n: CARD_REGISTRY[n].cost, reverse=True):
            if view.supply[name] > 0 and CARD_REGISTRY[name].cost <= view.pending_gain_max_cost:
                actions.append(ResolveRemodelGain(name))

    elif phase == Phase.AWAITING_WORKSHOP_GAIN:
        for name in sorted(view.supply, key=lambda n: CARD_REGISTRY[n].cost, reverse=True):
            if view.supply[name] > 0 and CARD_REGISTRY[name].cost <= 4:
                actions.append(ResolveWorkshop(name))

    return actions


# ---------------------------------------------------------------------------
# Prompt formatting helpers
# ---------------------------------------------------------------------------

def _hand_summary(cards: tuple) -> str:
    counts: dict[str, int] = {}
    for c in cards:
        counts[c.value] = counts.get(c.value, 0) + 1
    return ", ".join(
        f"{name}×{n}" if n > 1 else name
        for name, n in sorted(counts.items())
    ) or "(empty)"


def _action_label(action: Action) -> str:
    """One-line human-readable description of an action."""
    if isinstance(action, PlayAction):
        return f"Play {action.card.value}  [{CARD_DESCRIPTIONS.get(action.card, '')}]"
    if isinstance(action, EndActionPhase):
        return "End action phase (go to buy)"
    if isinstance(action, PlayTreasure):
        coins = CARD_REGISTRY[action.card].coins
        return f"Play {action.card.value} (+{coins} coin{'s' if coins != 1 else ''})"
    if isinstance(action, BuyCard):
        defn = CARD_REGISTRY[action.card]
        desc = CARD_DESCRIPTIONS.get(action.card, "")
        return f"Buy {action.card.value}  [cost {defn.cost}  {desc}]"
    if isinstance(action, EndBuyPhase):
        return "End buy phase (pass)"
    if isinstance(action, ResolveMineTrash):
        defn = CARD_REGISTRY[action.card]
        return f"Trash {action.card.value} (cost {defn.cost}) → can gain Treasure up to cost {defn.cost + 3}"
    if isinstance(action, ResolveMineGain):
        defn = CARD_REGISTRY[action.card]
        return f"Gain {action.card.value} to hand (cost {defn.cost})"
    if isinstance(action, ResolveRemodelTrash):
        defn = CARD_REGISTRY[action.card]
        return f"Trash {action.card.value} (cost {defn.cost}) → can gain card up to cost {defn.cost + 2}"
    if isinstance(action, ResolveRemodelGain):
        defn = CARD_REGISTRY[action.card]
        desc = CARD_DESCRIPTIONS.get(action.card, "")
        return f"Gain {action.card.value} to discard (cost {defn.cost})  [{desc}]"
    if isinstance(action, ResolveWorkshop):
        defn = CARD_REGISTRY[action.card]
        desc = CARD_DESCRIPTIONS.get(action.card, "")
        return f"Gain {action.card.value} (cost {defn.cost})  [{desc}]"
    return repr(action)


def _format_state(view: PlayerView) -> str:
    lines: list[str] = []

    lines.append(f"=== GAME STATE (your turn: {view.current_player_name}) ===")
    lines.append(f"Phase: {view.phase.name}  |  Actions: {view.actions}  Buys: {view.buys}  Coins: {view.coins}")
    lines.append("")

    lines.append(f"YOUR HAND ({len(view.your_hand)}): {_hand_summary(view.your_hand)}")
    lines.append(f"Your draw pile: {view.your_draw_pile_size} cards remaining")

    recent_discard = view.your_discard[-6:] if view.your_discard else ()
    more = len(view.your_discard) - len(recent_discard)
    discard_str = ", ".join(c.value for c in recent_discard)
    if more > 0:
        discard_str = f"...{more} more, " + discard_str
    lines.append(f"Your discard ({len(view.your_discard)}): {discard_str or '(empty)'}")
    lines.append("")

    lines.append("SUPPLY:")
    for name in sorted(view.supply, key=lambda n: CARD_REGISTRY[n].cost):
        count = view.supply[name]
        if count == 0:
            continue
        defn = CARD_REGISTRY[name]
        vp = f"  {defn.vp:+d}VP" if defn.vp != 0 else ""
        desc = CARD_DESCRIPTIONS.get(name, "")
        lines.append(f"  {name.value:<12} {count:>2} left  cost {defn.cost}{vp}  — {desc}")
    lines.append("")

    if view.trash:
        lines.append(f"TRASH: {', '.join(c.value for c in view.trash)}")
        lines.append("")

    lines.append("OPPONENTS:")
    for other in view.others:
        vp_now = sum(CARD_REGISTRY[c].vp for c in other.discard)
        lines.append(
            f"  {other.name}: {other.hand_size} in hand, "
            f"{other.draw_pile_size} in draw, "
            f"{len(other.discard)} in discard"
        )
    lines.append("")

    if view.pending_gain_max_cost:
        to_hand = " (gained to hand)" if view.pending_gain_to_hand else " (gained to discard)"
        lines.append(f"PENDING: can gain a card costing up to {view.pending_gain_max_cost}{to_hand}")
        lines.append("")

    if view.militia_targets:
        lines.append(f"MILITIA: you must discard down to 3 cards (discard {len(view.your_hand) - 3})")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON extraction and parsing (structured output)
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> dict:
    """Extract the last JSON object from a string (handles reasoning + JSON responses)."""
    last_brace = raw.rfind("}")
    if last_brace == -1:
        raise ValueError(f"No JSON object found in response: {raw!r}")
    first_brace = raw.rfind("{", 0, last_brace)
    if first_brace == -1:
        raise ValueError(f"No JSON object found in response: {raw!r}")
    return json.loads(raw[first_brace : last_brace + 1])


def _parse_action(raw: str, view: PlayerView) -> Action:
    data = _extract_json(raw)
    action_type = data["action_type"]

    if action_type == "play_action":
        return PlayAction(CardName(data["card"]))
    elif action_type == "end_action_phase":
        return EndActionPhase()
    elif action_type == "play_treasure":
        return PlayTreasure(CardName(data["card"]))
    elif action_type == "buy_card":
        return BuyCard(CardName(data["card"]))
    elif action_type == "end_buy_phase":
        return EndBuyPhase()
    elif action_type == "resolve_cellar":
        cards = tuple(CardName(c) for c in data.get("discard_cards", []))
        return ResolveCellar(discard_cards=cards)
    elif action_type == "resolve_mine_trash":
        return ResolveMineTrash(CardName(data["card"]))
    elif action_type == "resolve_mine_gain":
        return ResolveMineGain(CardName(data["card"]))
    elif action_type == "resolve_remodel_trash":
        return ResolveRemodelTrash(CardName(data["card"]))
    elif action_type == "resolve_remodel_gain":
        return ResolveRemodelGain(CardName(data["card"]))
    elif action_type == "resolve_workshop":
        return ResolveWorkshop(CardName(data["card"]))
    elif action_type == "resolve_militia_discard":
        cards = tuple(CardName(c) for c in data["discard_cards"])
        return ResolveMilitiaDiscard(discard_cards=cards)
    else:
        raise ValueError(f"Unknown action_type: {action_type!r}")


def _action_prompt(view: PlayerView, legal: list[Action]) -> str:
    """Build phase-specific instructions with JSON schema examples."""
    lines: list[str] = []

    if view.phase == Phase.ACTION:
        playable: set[CardName] = set()
        for card in view.your_hand:
            defn = CARD_REGISTRY[card]
            if CardType.ACTION in defn.types or CardType.REACTION in defn.types:
                playable.add(card)

        lines.append("=== ACTION PHASE ===")
        lines.append(f"Actions remaining: {view.actions}")
        lines.append("")
        lines.append("Choose one:")
        if playable and view.actions > 0:
            for card in sorted(playable, key=lambda c: c.value):
                desc = CARD_DESCRIPTIONS.get(card, "")
                lines.append(
                    f'  Play {card.value}: {{"action_type": "play_action", "card": "{card.value}"}}  [{desc}]'
                )
        lines.append(
            '  End action phase: {"action_type": "end_action_phase"}'
        )

    elif view.phase == Phase.BUY:
        lines.append("=== BUY PHASE ===")
        lines.append(f"Buys: {view.buys}  Coins: {view.coins}")
        lines.append("")

        unplayed: set[CardName] = set()
        for card in view.your_hand:
            if CardType.TREASURE in CARD_REGISTRY[card].types:
                unplayed.add(card)

        lines.append("Choose one:")
        if unplayed:
            for card in sorted(unplayed, key=lambda c: CARD_REGISTRY[c].cost):
                coins = CARD_REGISTRY[card].coins
                lines.append(
                    f'  Play treasure: {{"action_type": "play_treasure", "card": "{card.value}"}}  (+{coins} coin{"s" if coins != 1 else ""})'
                )

        if view.buys > 0:
            affordable = [
                name for name in sorted(view.supply, key=lambda n: CARD_REGISTRY[n].cost)
                if view.supply[name] > 0 and CARD_REGISTRY[name].cost <= view.coins
            ]
            for name in affordable:
                defn = CARD_REGISTRY[name]
                desc = CARD_DESCRIPTIONS.get(name, "")
                lines.append(
                    f'  Buy: {{"action_type": "buy_card", "card": "{name.value}"}}  [cost {defn.cost}  {desc}]'
                )

        lines.append('  End buy phase: {"action_type": "end_buy_phase"}')

    elif view.phase == Phase.AWAITING_CELLAR_DISCARD:
        hand_list = ", ".join(c.value for c in view.your_hand)
        lines.append("=== CELLAR ===")
        lines.append("Discard any cards from your hand, then draw one per discarded.")
        lines.append(f"Your hand: {hand_list}")
        lines.append("")
        lines.append(
            'Respond with JSON: {"action_type": "resolve_cellar", "discard_cards": ["Card1", "Card2", ...]}'
        )
        lines.append('  (use empty list [] to discard nothing)')

    elif view.phase == Phase.AWAITING_MILITIA_DISCARD:
        n = len(view.your_hand) - 3
        hand_list = ", ".join(c.value for c in view.your_hand)
        lines.append("=== MILITIA ATTACK ===")
        lines.append(f"You must discard exactly {n} card(s) to keep only 3.")
        lines.append(f"Your hand: {hand_list}")
        lines.append("")
        lines.append(
            '{"action_type": "resolve_militia_discard", "discard_cards": ["Card1", ...]}'
        )

    elif view.phase == Phase.AWAITING_MINE_TRASH:
        trashable = set()
        for card in view.your_hand:
            if CardType.TREASURE in CARD_REGISTRY[card].types:
                trashable.add(card)
        lines.append("=== MINE — trash a Treasure ===")
        for card in sorted(trashable, key=lambda c: CARD_REGISTRY[c].cost):
            defn = CARD_REGISTRY[card]
            lines.append(
                f'  Trash {card.value} (cost {defn.cost}) → gain up to cost {defn.cost + 3}: '
                f'{{"action_type": "resolve_mine_trash", "card": "{card.value}"}}'
            )

    elif view.phase == Phase.AWAITING_MINE_GAIN:
        lines.append(f"=== MINE — gain a Treasure costing up to {view.pending_gain_max_cost} ===")
        for name in sorted(view.supply, key=lambda n: CARD_REGISTRY[n].cost, reverse=True):
            if (view.supply[name] > 0
                    and CARD_REGISTRY[name].cost <= view.pending_gain_max_cost
                    and CardType.TREASURE in CARD_REGISTRY[name].types):
                lines.append(
                    f'  {{"action_type": "resolve_mine_gain", "card": "{name.value}"}}  (cost {CARD_REGISTRY[name].cost})'
                )

    elif view.phase == Phase.AWAITING_REMODEL_TRASH:
        hand_set: set[CardName] = set()
        for card in view.your_hand:
            hand_set.add(card)
        lines.append("=== REMODEL — trash a card from hand ===")
        for card in sorted(hand_set, key=lambda c: CARD_REGISTRY[c].cost):
            defn = CARD_REGISTRY[card]
            lines.append(
                f'  Trash {card.value} (cost {defn.cost}) → gain up to cost {defn.cost + 2}: '
                f'{{"action_type": "resolve_remodel_trash", "card": "{card.value}"}}'
            )

    elif view.phase == Phase.AWAITING_REMODEL_GAIN:
        lines.append(f"=== REMODEL — gain a card costing up to {view.pending_gain_max_cost} ===")
        for name in sorted(view.supply, key=lambda n: CARD_REGISTRY[n].cost, reverse=True):
            if view.supply[name] > 0 and CARD_REGISTRY[name].cost <= view.pending_gain_max_cost:
                desc = CARD_DESCRIPTIONS.get(name, "")
                lines.append(
                    f'  {{"action_type": "resolve_remodel_gain", "card": "{name.value}"}}  [cost {CARD_REGISTRY[name].cost}  {desc}]'
                )

    elif view.phase == Phase.AWAITING_WORKSHOP_GAIN:
        lines.append("=== WORKSHOP — gain a card costing up to 4 ===")
        for name in sorted(view.supply, key=lambda n: CARD_REGISTRY[n].cost, reverse=True):
            if view.supply[name] > 0 and CARD_REGISTRY[name].cost <= 4:
                desc = CARD_DESCRIPTIONS.get(name, "")
                lines.append(
                    f'  {{"action_type": "resolve_workshop", "card": "{name.value}"}}  [cost {CARD_REGISTRY[name].cost}  {desc}]'
                )

    lines.append("")
    lines.append("Respond with only the JSON object.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM Agent
# ---------------------------------------------------------------------------

class LLMAgent(Agent):
    """
    Picks actions using an LLM via OpenRouter's OpenAI-compatible API.

    All hidden information is kept out of the prompt — the agent only sees
    what get_player_view() exposes.
    """

    SYSTEM_PROMPT = (
        "You are playing Dominion, a deck-building card game. "
        "Rules: each turn you have an Action phase (play Action cards) then a Buy phase "
        "(play Treasures for coins, spend coins to buy cards from the supply). "
        "At end of turn, discard everything and draw 5 new cards. "
        "The game ends when the Province pile or any 3 supply piles are empty. "
        "Final score = total Victory Points across all cards in your deck. "
        "Respond with only a valid JSON object — no explanation."
    )

    def __init__(
        self,
        model: str = "openai/gpt-4o-mini",
        api_key: Optional[str] = None,
        verbose: bool = True,
    ) -> None:
        self.model = model
        self.verbose = verbose
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ["OPENROUTER_API_KEY"],
        )
        self._fallback = RandomAgent()

    def choose_action(self, view: PlayerView) -> Action:
        if view.phase == Phase.BUY:
            treasures = [c for c in view.your_hand if CardType.TREASURE in CARD_REGISTRY[c].types]
            if treasures:
                return PlayTreasure(treasures[0])

        legal = get_legal_actions(view)
        if not legal and view.phase not in (Phase.AWAITING_CELLAR_DISCARD, Phase.AWAITING_MILITIA_DISCARD):
            return self._fallback.choose_action(view)

        state_str = _format_state(view)
        action_info = _action_prompt(view, legal)

        prompt = f"{state_str}\n{action_info}"
        raw = self._call(prompt)

        if self.verbose:
            print(f"    [LLM response: {raw[:120]}]")

        try:
            action = _parse_action(raw, view)
            return action
        except (ValueError, KeyError, json.JSONDecodeError):
            pass

        if self.verbose:
            print(f"    [LLM parse failed, falling back to random]")
        if legal:
            return random.choice(legal)
        return self._fallback.choose_action(view)

    def _call(self, prompt: str) -> str:
        if self.verbose:
            print(f"    [{self.model} thinking...]", end="", flush=True)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.2,
        )
        if self.verbose:
            print("\r", end="", flush=True)
        return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Main — 1 LLM player vs 3 random opponents
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    model = sys.argv[2] if len(sys.argv) > 2 else "openai/gpt-4o-mini"

    agents = {
        "LLM":   LLMAgent(model=model, verbose=True),
        "Rand1": RandomAgent(),
        "Rand2": RandomAgent(),
        "Rand3": RandomAgent(),
    }

    run_game(agents, seed=seed, verbose=True)
