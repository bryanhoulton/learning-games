"""
LLMPlayerAgent — drives a player using an LLM via OpenRouter.

The agent formats the current PlayerView into a prompt, asks the LLM to
choose an action as JSON, then parses and returns the corresponding
PlayerAction. Errors from the engine are fed back into the next prompt.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Optional

from openrouter import OpenRouter

from models import Color, Phase, RouteId
from player_agent import (
    ClaimRouteAction,
    DrawCardAction,
    DrawTicketsAction,
    KeepTicketsAction,
    PlayerAction,
    PlayerAgent,
)
from player_view import PlayerView

DEFAULT_MODEL = "openai/gpt-4o-mini"


# ---------------------------------------------------------------------------
# View → prompt
# ---------------------------------------------------------------------------

def _view_to_prompt(view: PlayerView, error: Optional[str]) -> str:
    lines = []

    lines.append(f"You are playing Ticket to Ride as '{view.my_name}'.")
    turn_str = "YOUR turn" if view.is_my_turn else f"{view.current_player_name}'s turn"
    lines.append(f"It is {turn_str}.")
    if view.last_round:
        lines.append("*** LAST ROUND in progress ***")

    lines.append("")
    lines.append("=== YOUR STATUS ===")
    lines.append(f"Trains remaining: {view.my_trains_remaining}")
    lines.append(f"Score (routes only): {view.my_score}")

    hand = Counter(view.my_hand)
    hand_str = ", ".join(f"{c.value}×{n}" for c, n in hand.items() if n > 0) or "(empty)"
    lines.append(f"Hand: {hand_str}")

    lines.append("Destination tickets:")
    for t in view.my_tickets:
        lines.append(f"  [{t.id}] {t.city_a} ↔ {t.city_b}  ({t.points} pts)")

    claimed = [f"{rid.city_a}-{rid.city_b}" for rid in view.my_claimed_routes]
    lines.append(f"Your claimed routes: {', '.join(claimed) or '(none)'}")

    lines.append("")
    lines.append("=== BOARD ===")
    face_up = ", ".join(f"slot{i}:{c.value}" for i, c in enumerate(view.face_up_cards))
    lines.append(f"Face-up cards: {face_up}")
    lines.append(f"Train deck size: {view.train_deck_size}")
    lines.append(f"Destination deck size: {view.destination_deck_size}")

    lines.append("")
    lines.append("=== OPPONENTS ===")
    for opp in view.opponents:
        lines.append(
            f"  {opp.name}: score={opp.score}, trains={opp.trains_remaining}, "
            f"cards={opp.hand_size}, tickets={opp.ticket_count}"
        )

    lines.append("")
    lines.append("=== CLAIMED ROUTES ON BOARD ===")
    if view.all_claimed_routes:
        for rid, owner in view.all_claimed_routes.items():
            lines.append(f"  {rid.city_a}-{rid.city_b} (idx {rid.index}): owned by {owner}")
    else:
        lines.append("  (none yet)")

    # Phase-specific instructions
    lines.append("")
    lines.append("=== YOUR ACTION ===")

    if view.phase == Phase.KEEPING_TICKETS:
        lines.append(f"You must keep at least {view.min_tickets_to_keep} of these offered tickets:")
        for t in view.pending_tickets:
            lines.append(f"  [{t.id}] {t.city_a} ↔ {t.city_b}  ({t.points} pts)")
        lines.append("")
        lines.append('Respond with JSON: {"action_type": "keep_tickets", "ticket_ids": [<id>, ...]}')

    elif view.phase == Phase.DRAWING_CARDS:
        lines.append("You already drew one card. Draw your second (no face-up locomotives).")
        lines.append("")
        lines.append(
            'Respond with JSON: {"action_type": "draw_card", "slot": <0-4 or null for deck>}'
        )

    else:  # CHOOSE_ACTION
        # Build claimable routes list for context
        claimable = _claimable_routes(view)
        lines.append("Choose one of:")
        lines.append('  {"action_type": "draw_card", "slot": <0-4 or null for deck>}')
        lines.append('  {"action_type": "draw_tickets"}  (if destination deck is not empty)')
        if claimable:
            lines.append('  {"action_type": "claim_route", "city_a": "...", "city_b": "...", "route_index": 0, "cards": ["color", ...]}')
            lines.append("  Affordable routes:")
            for rid, payment in claimable:
                route = view.routes[rid]
                cost = ", ".join(c.value for c in payment)
                lines.append(
                    f"    {rid.city_a} → {rid.city_b} (idx {rid.index}, len={route.length}, "
                    f"+{route.points}pts) — pay: [{cost}]"
                )
        lines.append("")
        lines.append("Respond with only the JSON object.")

    if error:
        lines.append("")
        lines.append(f"Your previous action was REJECTED: {error}")
        lines.append("Choose a different valid action.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Response → PlayerAction
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> dict:
    """Extract the last JSON object from a string (handles reasoning + JSON responses)."""
    # Find the last {...} block
    last_brace = raw.rfind("}")
    if last_brace == -1:
        raise ValueError(f"No JSON object found in response: {raw!r}")
    first_brace = raw.rfind("{", 0, last_brace)
    if first_brace == -1:
        raise ValueError(f"No JSON object found in response: {raw!r}")
    return json.loads(raw[first_brace:last_brace + 1])


def _parse_action(raw: str, view: PlayerView) -> PlayerAction:
    data = _extract_json(raw)
    action_type = data["action_type"]

    if action_type == "draw_card":
        slot = data.get("slot")  # None or int
        return DrawCardAction(slot=slot)

    elif action_type == "claim_route":
        city_a = data["city_a"]
        city_b = data["city_b"]
        route_index = int(data.get("route_index", 0))
        cards = tuple(Color(c) for c in data["cards"])
        return ClaimRouteAction(
            route_id=RouteId(city_a, city_b, route_index),
            cards=cards,
        )

    elif action_type == "draw_tickets":
        return DrawTicketsAction()

    elif action_type == "keep_tickets":
        ticket_ids = tuple(int(i) for i in data["ticket_ids"])
        return KeepTicketsAction(ticket_ids=ticket_ids)

    else:
        raise ValueError(f"Unknown action_type: {action_type!r}")


# ---------------------------------------------------------------------------
# Route affordability (mirrors random_player.py, works purely from PlayerView)
# ---------------------------------------------------------------------------

def _cheapest_payment(route, hand_counts: Counter, wild_count: int) -> Optional[list[Color]]:
    n = route.length
    candidates = [route.color] if route.color != Color.WILD else [
        c for c in Color if c != Color.WILD
    ]
    best = None
    for color in candidates:
        have = hand_counts[color]
        needed = n - have
        if needed <= 0:
            return [color] * n
        elif needed <= wild_count:
            if best is None:
                best = [color] * have + [Color.WILD] * needed
    return best


def _claimable_routes(view: PlayerView) -> list[tuple[RouteId, list[Color]]]:
    hand_counts = Counter(view.my_hand)
    wild_count = hand_counts[Color.WILD]
    claimable = []
    for rid, route in view.routes.items():
        if rid in view.all_claimed_routes:
            continue
        if view.my_trains_remaining < route.length:
            continue
        if view.num_players <= 3:
            sibling_blocked = any(
                RouteId(route.city_a, route.city_b, idx) != rid
                and RouteId(route.city_a, route.city_b, idx) in view.all_claimed_routes
                and view.all_claimed_routes[RouteId(route.city_a, route.city_b, idx)] == view.my_name
                for idx in range(2)
            )
            if sibling_blocked:
                continue
        payment = _cheapest_payment(route, hand_counts, wild_count)
        if payment is not None:
            claimable.append((rid, payment))
    return claimable


# ---------------------------------------------------------------------------
# LLMPlayerAgent
# ---------------------------------------------------------------------------

class LLMPlayerAgent(PlayerAgent):

    def __init__(
        self,
        player_name: str,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._name = player_name
        self._model = model
        self._client = OpenRouter(api_key=api_key or os.environ["OPENROUTER_API_KEY"])

    @property
    def name(self) -> str:
        return self._name

    def choose_action(self, view: PlayerView, error: Optional[str] = None) -> PlayerAction:
        prompt = _view_to_prompt(view, error)
        import sys
        print(f"  [LLM:{self._name}] querying {self._model}...", flush=True)

        resp = self._client.chat.send(
            model=self._model,
            timeout_ms=15000,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are playing Ticket to Ride. Rules: players take turns either "
                        "(a) drawing 2 train cards, (b) claiming a route by spending matching "
                        "cards, or (c) drawing destination tickets and keeping at least 1. "
                        "Destination tickets score bonus points if both cities are connected "
                        "by your routes at game end, or subtract points if not. "
                        "Locomotives (wild) substitute for any color. "
                        "Respond with only a valid JSON object — no explanation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        raw = resp.choices[0].message.content
        print(f"  [LLM:{self._name}] response: {raw}", flush=True)

        return _parse_action(raw, view)
