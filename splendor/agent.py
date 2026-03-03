"""
Agent interface and built-in agents for Splendor.

Agents receive a PlayerView (never raw GameState) and return an Action.

LLMAgent maintains a persistent conversation history across the whole game,
receiving formatted game events as they happen and reasoning before each move.
Set OPENROUTER_API_KEY before using it.
"""

from __future__ import annotations

import json
import os
import random
import re
from abc import ABC, abstractmethod
from itertools import combinations
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
from cards import CARD_REGISTRY, NOBLE_REGISTRY
from models import GEM_COLORS, GemColor, Phase
from view import PlayerView


_RULES = """\
You are playing Splendor. Rules:
- On your turn do exactly one of:
  (a) Take 2–3 gem tokens of different colors (each must have ≥1 in supply)
  (b) Take 2 gems of the same color (that color must have ≥4 in supply)
  (c) Reserve a card from the board or a deck top — receive 1 gold token if available (max 3 reserved)
  (d) Buy a card from the board or your reserved cards — cost = printed cost minus your card bonuses; gold is a wildcard
- Development cards give a permanent gem bonus (reduces future costs) and victory points
- Nobles automatically visit at end of turn when your card-bonus totals meet their requirements (+3 VP each)
- If you hold >10 gems after your action you must return some to the supply
- The first player to end a turn with ≥15 VP triggers the final round; highest VP after the round wins (tiebreak: fewer purchased cards)
Respond with only a valid JSON object — no explanation.\
"""

_STRATEGY = """\
Optimal strategy:
1. On turn 1, study the available nobles and pick 1–2 to target. Choose the pair with the most color overlap — that minimises the number of distinct colors you need to develop.
2. Commit to those 2–3 colors for the entire game. Do not spread bonuses across all 5 colors.
3. Early game (turns 1–15): buy tier-1 cards almost exclusively for their bonuses, not their VP. A 0-VP tier-1 card that gives you a bonus in a target color is better than a 1-VP card in an irrelevant color.
4. Mid game: once you have 3+ bonuses in each target color, tier-2 cards become cheap or free. Buy them to accelerate toward tier-3 and nobles.
5. Never hoard gems. Gems you cannot spend in the next 1–2 turns are wasted tempo. Take gems only when you have a specific card in mind.
6. Aim to hit 15 VP in 25–35 turns. Count your VP each turn and accelerate when close.
7. Reserve a card only to block an opponent who is one purchase away from a critical noble or high-VP card — not just for the gold.\
"""


class Agent(ABC):
    """Base class for all Splendor agents."""

    @abstractmethod
    def choose_action(self, view: PlayerView) -> Action: ...

    def on_game_start(self, engine, player_name: str) -> None:
        """Called by the runner after engine creation. Override to subscribe to events."""


# ---------------------------------------------------------------------------
# Random agent
# ---------------------------------------------------------------------------

class RandomAgent(Agent):
    """Picks uniformly at random from legal options at each decision point."""

    def choose_action(self, view: PlayerView) -> Action:
        if view.phase == Phase.AWAITING_DISCARD:
            return self._discard(view)
        if view.phase == Phase.AWAITING_NOBLE_CHOICE:
            return ChooseNoble(random.choice(list(view.pending_noble_choices)))

        options: list[Action] = []

        for card_id in _buyable_cards(view):
            options.append(BuyCard(card_id))

        if len(view.your_reserved) < 3:
            for tier, slots in view.board.items():
                for card_id in slots:
                    if card_id is not None:
                        options.append(ReserveBoardCard(card_id))
            for tier in (1, 2, 3):
                if view.deck_sizes.get(tier, 0) > 0:
                    options.append(ReserveDeckTop(tier))

        available = [c for c in GEM_COLORS if view.gem_supply.get(c, 0) >= 1]
        if len(available) >= 1:
            chosen = tuple(random.sample(available, min(3, len(available))))
            options.append(TakeDifferentGems(chosen))

        for color in GEM_COLORS:
            if view.gem_supply.get(color, 0) >= 4:
                options.append(TakeDoubleGem(color))

        if not options:
            raise RuntimeError("No legal actions available.")

        return random.choice(options)

    def _discard(self, view: PlayerView) -> DiscardGems:
        gems = dict(view.your_gems)
        total = sum(gems.values())
        to_return: dict[GemColor, int] = {c: 0 for c in GemColor}
        while total > 10:
            have = [c for c, v in gems.items() if v > 0]
            pick = random.choice(have)
            gems[pick] -= 1
            to_return[pick] += 1
            total -= 1
        return DiscardGems({c: v for c, v in to_return.items() if v > 0})


# ---------------------------------------------------------------------------
# LLM agent (OpenRouter)
# ---------------------------------------------------------------------------

class LLMAgent(Agent):
    """
    Uses an LLM via OpenRouter to choose actions.

    Maintains a persistent conversation history across the entire game:
    - Game events are appended as user messages as they happen
    - On each turn the model responds with a JSON action object
    - Its own responses are preserved in the history for future turns

    Requires OPENROUTER_API_KEY environment variable.
    """

    def __init__(
        self,
        model: str = "google/gemini-3-flash-preview",
        strategy: bool = False,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required: uv add openai")

        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENROUTER_API_KEY environment variable not set.")

        self._client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        self._model = model
        self._strategy = strategy
        self._messages: list[dict] = []
        self._player_name: str = ""
        self.last_reasoning: str = ""

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def on_game_start(self, engine, player_name: str) -> None:
        self._player_name = player_name
        engine.subscribe(self._handle_event)

        # Seed the conversation with rules + initial board state
        nobles_text = "\n".join(
            f"  Noble [{nid}]: {NOBLE_REGISTRY[nid].vp}VP — requires "
            + ", ".join(
                f"{v} {c.value}" for c, v in NOBLE_REGISTRY[nid].requirements.items()
            )
            for nid in engine.state.nobles
        )
        player_order = ", ".join(
            f"{p.name}{'  ← you' if p.name == player_name else ''}"
            for p in engine.state.players
        )

        preamble = _RULES
        if self._strategy:
            preamble = f"{_RULES}\n\n{_STRATEGY}"

        self._messages = [
            {
                "role": "user",
                "content": (
                    f"{preamble}\n\n"
                    f"You are playing as: {player_name}\n"
                    f"Turn order: {player_order}\n\n"
                    f"Nobles available this game:\n{nobles_text}\n\n"
                    f"The game is about to begin. Consider which nobles to target."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Understood. I'll study the nobles and plan my color focus before making my first move."
                ),
            },
        ]

    # ------------------------------------------------------------------
    # Event handler — builds the history the model reads between turns
    # ------------------------------------------------------------------

    def _handle_event(self, event) -> None:
        msg = _format_event(event, self._player_name)
        if msg:
            self._messages.append({"role": "user", "content": msg})

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def choose_action(self, view: PlayerView) -> Action:
        legal = _legal_actions(view)

        phase_context = {
            Phase.AWAITING_DISCARD: (
                f"You have {sum(view.your_gems.values())} gems (max 10). "
                f"Choose which to return."
            ),
            Phase.AWAITING_NOBLE_CHOICE: (
                "Multiple nobles qualify to visit you. Choose one."
            ),
            Phase.PLAYER_TURN: "It is your turn.",
        }.get(view.phase, "")

        turn_prompt = (
            f"{phase_context}\n\n"
            f"Current state:\n{_format_view(view)}\n\n"
            f"{_action_prompt(view, legal)}"
        )

        messages = self._messages + [{"role": "user", "content": turn_prompt}]

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=400,
            temperature=0.7,
        )
        raw = response.choices[0].message.content.strip()

        self._messages.append({"role": "user", "content": turn_prompt})
        self._messages.append({"role": "assistant", "content": raw})
        self.last_reasoning = raw

        try:
            return _parse_action(raw)
        except (ValueError, KeyError, json.JSONDecodeError):
            return random.choice(legal)


# ---------------------------------------------------------------------------
# Helpers shared by agents
# ---------------------------------------------------------------------------

def _buyable_cards(view: PlayerView) -> list[int]:
    bonuses = _compute_bonuses(view)
    candidates = list(view.your_reserved)
    for slots in view.board.values():
        for cid in slots:
            if cid is not None:
                candidates.append(cid)

    affordable = []
    for card_id in candidates:
        card = CARD_REGISTRY[card_id]
        gold_needed = 0
        for color, amount in card.cost.items():
            owed = max(0, amount - bonuses.get(color, 0))
            shortfall = max(0, owed - view.your_gems.get(color, 0))
            gold_needed += shortfall
        if gold_needed <= view.your_gems.get(GemColor.GOLD, 0):
            affordable.append(card_id)
    return affordable


def _compute_bonuses(view: PlayerView) -> dict[GemColor, int]:
    bonuses: dict[GemColor, int] = {c: 0 for c in GEM_COLORS}
    for card_id in view.your_purchased:
        bonuses[CARD_REGISTRY[card_id].bonus_color] += 1
    return bonuses


def _legal_actions(view: PlayerView) -> list[Action]:
    if view.phase == Phase.AWAITING_DISCARD:
        return _discard_options(view)

    if view.phase == Phase.AWAITING_NOBLE_CHOICE:
        return [ChooseNoble(nid) for nid in view.pending_noble_choices]

    actions: list[Action] = []

    for card_id in _buyable_cards(view):
        actions.append(BuyCard(card_id))

    if len(view.your_reserved) < 3:
        for tier, slots in view.board.items():
            for card_id in slots:
                if card_id is not None:
                    actions.append(ReserveBoardCard(card_id))
        for tier in (1, 2, 3):
            if view.deck_sizes.get(tier, 0) > 0:
                actions.append(ReserveDeckTop(tier))

    available = [c for c in GEM_COLORS if view.gem_supply.get(c, 0) >= 1]
    if len(available) >= 3:
        for combo in combinations(available, 3):
            actions.append(TakeDifferentGems(tuple(combo)))
    elif len(available) == 2:
        actions.append(TakeDifferentGems(tuple(available)))
    elif len(available) == 1:
        actions.append(TakeDifferentGems(tuple(available)))

    for color in GEM_COLORS:
        if view.gem_supply.get(color, 0) >= 4:
            actions.append(TakeDoubleGem(color))

    return actions


def _discard_options(view: PlayerView) -> list[Action]:
    """Enumerate all distinct ways to return gems down to exactly 10."""
    total = sum(view.your_gems.values())
    n_return = total - 10
    if n_return <= 0:
        return [DiscardGems({})]

    # Build a flat list of individual gem tokens the player holds
    tokens: list[GemColor] = []
    for color, count in view.your_gems.items():
        tokens.extend([color] * count)

    seen: set[tuple] = set()
    options: list[Action] = []
    for combo in combinations(tokens, n_return):
        key = tuple(sorted(c.value for c in combo))
        if key in seen:
            continue
        seen.add(key)
        d: dict[GemColor, int] = {}
        for c in combo:
            d[c] = d.get(c, 0) + 1
        options.append(DiscardGems(d))
    return options


# ---------------------------------------------------------------------------
# Event formatter
# ---------------------------------------------------------------------------

def _format_event(event, player_name: str) -> Optional[str]:
    from events import (
        CardBought, CardReserved, GameOver, GemsTaken, GemsReturned,
        NobleVisited, TurnEnded, TurnStarted,
    )

    you = event.player_name == player_name if hasattr(event, "player_name") else False

    if isinstance(event, GemsTaken):
        gems = _gems_str(event.gems)
        return f"You took {gems}." if you else f"{event.player_name} took {gems}."

    if isinstance(event, GemsReturned):
        gems = _gems_str(event.gems)
        return (
            f"You returned {gems} (over 10-gem limit)."
            if you else f"{event.player_name} returned {gems}."
        )

    if isinstance(event, CardReserved):
        card = CARD_REGISTRY[event.card_id]
        desc = _card_desc(card)
        gold = " and took 1 gold" if event.gold_taken else ""
        return (
            f"You reserved {desc}{gold}."
            if you else f"{event.player_name} reserved {desc}{gold}."
        )

    if isinstance(event, CardBought):
        card = CARD_REGISTRY[event.card_id]
        desc = _card_desc(card)
        paid = _gems_str(event.gems_paid)
        gold = f" + {event.gold_used} gold" if event.gold_used else ""
        return (
            f"You bought {desc}, paying {paid}{gold}."
            if you else f"{event.player_name} bought {desc}, paying {paid}{gold}."
        )

    if isinstance(event, NobleVisited):
        noble = NOBLE_REGISTRY[event.noble_id]
        return (
            f"Noble [{event.noble_id}] visited you! (+{noble.vp} VP)"
            if you else
            f"Noble [{event.noble_id}] visited {event.player_name} (+{noble.vp} VP)."
        )

    if isinstance(event, TurnStarted):
        # Own TurnStarted is handled by choose_action prompt; suppress it here
        if event.player_name == player_name:
            return None
        return f"--- {event.player_name}'s turn ---"

    if isinstance(event, TurnEnded):
        return (
            f"Your turn ended. You now have {event.vp} VP."
            if you else f"{event.player_name}'s turn ended ({event.vp} VP)."
        )

    if isinstance(event, GameOver):
        scores = ", ".join(f"{n}: {v}VP" for n, v in event.scores.items())
        return f"Game over! {scores}. Winner: {event.winner}."

    return None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_view(view: PlayerView) -> str:
    bonuses = _compute_bonuses(view)
    lines = [
        f"Your gems:    {_gems_str(view.your_gems)}",
        f"Your bonuses: {_gems_str(bonuses)}",
        f"Your VP: {view.your_vp}",
        f"Reserved: {[_card_desc(CARD_REGISTRY[c]) for c in view.your_reserved] or 'none'}",
        "",
        f"Gem supply: {_gems_str(view.gem_supply)}",
        "Board:",
    ]
    for tier in (1, 2, 3):
        row = []
        for cid in view.board.get(tier, []):
            row.append("---" if cid is None else f"[{cid}] {_card_desc(CARD_REGISTRY[cid])}")
        lines.append(f"  Tier {tier}: {',  '.join(row)}")

    lines.append("Nobles on board:")
    for nid in view.nobles:
        n = NOBLE_REGISTRY[nid]
        reqs = ", ".join(f"{v} {c.value}" for c, v in n.requirements.items())
        lines.append(f"  [{nid}] {n.vp}VP — needs {reqs}")

    lines.append("Opponents:")
    for o in view.others:
        b = {c: 0 for c in GEM_COLORS}
        for cid in o.purchased:
            b[CARD_REGISTRY[cid].bonus_color] += 1
        lines.append(
            f"  {o.name}: {o.vp}VP  gems={_gems_str(o.gems)}  "
            f"bonuses={_gems_str(b)}  cards={len(o.purchased)}  reserved={len(o.reserved)}"
        )
    return "\n".join(lines)


def _format_actions(actions: list[Action]) -> str:
    return "\n".join(f"  {i}: {_action_str(a)}" for i, a in enumerate(actions))


def _action_str(action: Action) -> str:
    if isinstance(action, BuyCard):
        c = CARD_REGISTRY[action.card_id]
        return f"Buy {_card_desc(c)}"
    if isinstance(action, TakeDifferentGems):
        return f"Take {', '.join(c.value for c in action.colors)}"
    if isinstance(action, TakeDoubleGem):
        return f"Take 2× {action.color.value}"
    if isinstance(action, ReserveBoardCard):
        c = CARD_REGISTRY[action.card_id]
        return f"Reserve {_card_desc(c)}"
    if isinstance(action, ReserveDeckTop):
        return f"Reserve top of tier-{action.tier} deck"
    if isinstance(action, DiscardGems):
        return f"Return {_gems_str(action.gems)}"
    if isinstance(action, ChooseNoble):
        n = NOBLE_REGISTRY[action.noble_id]
        reqs = ", ".join(f"{v} {c.value}" for c, v in n.requirements.items())
        return f"Claim noble [{action.noble_id}] ({n.vp}VP, needs {reqs})"
    return str(action)


def _card_desc(card) -> str:
    return (
        f"[{card.id}] T{card.tier} {card.bonus_color.value} "
        f"{card.vp}VP cost={_cost_str(card.cost)}"
    )


def _gems_str(gems: dict) -> str:
    parts = [f"{c.value[0].upper()}:{v}" for c, v in gems.items() if v > 0]
    return "{" + ", ".join(parts) + "}" if parts else "{}"


def _cost_str(cost: dict) -> str:
    parts = [f"{c.value[0].upper()}:{v}" for c, v in cost.items() if v > 0]
    return "{" + ", ".join(parts) + "}" if parts else "{free}"


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


def _parse_action(raw: str) -> Action:
    data = _extract_json(raw)
    action_type = data["action_type"]

    if action_type == "take_different_gems":
        colors = tuple(GemColor(c) for c in data["colors"])
        return TakeDifferentGems(colors)
    elif action_type == "take_double_gem":
        return TakeDoubleGem(GemColor(data["color"]))
    elif action_type == "reserve_board_card":
        return ReserveBoardCard(int(data["card_id"]))
    elif action_type == "reserve_deck_top":
        return ReserveDeckTop(int(data["tier"]))
    elif action_type == "buy_card":
        return BuyCard(int(data["card_id"]))
    elif action_type == "discard_gems":
        gems = {GemColor(c): int(v) for c, v in data["gems"].items()}
        return DiscardGems(gems)
    elif action_type == "choose_noble":
        return ChooseNoble(int(data["noble_id"]))
    else:
        raise ValueError(f"Unknown action_type: {action_type!r}")


def _action_prompt(view: PlayerView, legal: list[Action]) -> str:
    """Build phase-specific instructions with JSON schema examples."""
    lines: list[str] = []

    if view.phase == Phase.AWAITING_DISCARD:
        total = sum(view.your_gems.values())
        n_return = total - 10
        gems_str = ", ".join(
            f'"{c.value}": {v}' for c, v in view.your_gems.items() if v > 0
        )
        lines.append(f"You must return {n_return} gem(s) to get down to 10.")
        lines.append(f"Your gems: {{{gems_str}}}")
        lines.append("")
        lines.append(
            'Respond with JSON: {"action_type": "discard_gems", "gems": {"color": count, ...}}'
        )

    elif view.phase == Phase.AWAITING_NOBLE_CHOICE:
        lines.append("Multiple nobles qualify. Choose one:")
        for nid in view.pending_noble_choices:
            n = NOBLE_REGISTRY[nid]
            reqs = ", ".join(f"{v} {c.value}" for c, v in n.requirements.items())
            lines.append(f"  [{nid}] {n.vp}VP — needs {reqs}")
        lines.append("")
        lines.append(
            'Respond with JSON: {"action_type": "choose_noble", "noble_id": <id>}'
        )

    else:
        lines.append("Choose one action:")
        lines.append("")

        buyable = [a for a in legal if isinstance(a, BuyCard)]
        if buyable:
            lines.append(
                'Buy a card: {"action_type": "buy_card", "card_id": <id>}'
            )
            lines.append("  Affordable cards:")
            for a in buyable:
                lines.append(f"    {_card_desc(CARD_REGISTRY[a.card_id])}")
            lines.append("")

        available = [c for c in GEM_COLORS if view.gem_supply.get(c, 0) >= 1]
        if available:
            colors_str = ", ".join(
                f"{c.value} ({view.gem_supply[c]})" for c in available
            )
            n = min(3, len(available))
            lines.append(
                'Take different gems: {"action_type": "take_different_gems", '
                '"colors": ["color1", "color2", ...]}'
            )
            lines.append(f"  Available (pick up to {n}): {colors_str}")
            lines.append("")

        doubles = [c for c in GEM_COLORS if view.gem_supply.get(c, 0) >= 4]
        if doubles:
            colors_str = ", ".join(f"{c.value} ({view.gem_supply[c]})" for c in doubles)
            lines.append(
                'Take 2 of same color: {"action_type": "take_double_gem", "color": "color"}'
            )
            lines.append(f"  Eligible (≥4 in supply): {colors_str}")
            lines.append("")

        if len(view.your_reserved) < 3:
            lines.append(
                'Reserve a board card: {"action_type": "reserve_board_card", "card_id": <id>}'
            )
            available_tiers = [
                t for t in (1, 2, 3) if view.deck_sizes.get(t, 0) > 0
            ]
            if available_tiers:
                tiers_str = ", ".join(str(t) for t in available_tiers)
                lines.append(
                    'Reserve from deck: {"action_type": "reserve_deck_top", '
                    f'"tier": <{tiers_str}>}}'
                )
            lines.append("")

        lines.append("Respond with only the JSON object.")

    return "\n".join(lines)
