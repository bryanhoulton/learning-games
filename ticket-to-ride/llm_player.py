"""
LLMPlayerAgent — drives a player using an LLM via OpenRouter.

Maintains an append-only conversation history so the LLM has full context
of past turns, actions, reasoning, game events, and errors — like a
human player would.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from openrouter import OpenRouter, components

from events import (
    CardDrawnFromDeck,
    CardDrawnFromFaceUp,
    DestinationTicketsKept,
    DestinationTicketsOffered,
    Event,
    FaceUpCardsReset,
    LastRoundTriggered,
    RouteClaimed,
)
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

SYSTEM_PROMPT = (
    "You are playing Ticket to Ride. Rules: players take turns either "
    "(a) drawing 2 train cards, (b) claiming a route by spending matching "
    "cards, or (c) drawing destination tickets and keeping at least 1. "
    "Destination tickets score bonus points if both cities are connected "
    "by your routes at game end, or subtract points if not. "
    "Locomotives (wild) substitute for any color."
)

_NULLABLE_INT = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
_NULLABLE_STR = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_NULLABLE_STR_ARRAY = {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]}
_NULLABLE_INT_ARRAY = {"anyOf": [{"type": "array", "items": {"type": "integer"}}, {"type": "null"}]}

_KEEP_TICKETS_SCHEMA = components.ResponseFormatJSONSchema(
    type="json_schema",
    json_schema=components.JSONSchemaConfig(
        name="keep_tickets",
        strict=True,
        schema={
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "enum": ["keep_tickets"]},
                "ticket_ids": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["action_type", "ticket_ids"],
            "additionalProperties": False,
        },
    ),
)

_DRAW_SECOND_CARD_SCHEMA = components.ResponseFormatJSONSchema(
    type="json_schema",
    json_schema=components.JSONSchemaConfig(
        name="draw_second_card",
        strict=True,
        schema={
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "enum": ["draw_card"]},
                "slot": _NULLABLE_INT,
            },
            "required": ["action_type", "slot"],
            "additionalProperties": False,
        },
    ),
)

_CHOOSE_ACTION_SCHEMA = components.ResponseFormatJSONSchema(
    type="json_schema",
    json_schema=components.JSONSchemaConfig(
        name="choose_action",
        strict=True,
        schema={
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": ["draw_card", "draw_tickets", "claim_route"],
                },
                "slot": _NULLABLE_INT,
                "city_a": _NULLABLE_STR,
                "city_b": _NULLABLE_STR,
                "route_index": _NULLABLE_INT,
                "cards": _NULLABLE_STR_ARRAY,
                "ticket_ids": _NULLABLE_INT_ARRAY,
            },
            "required": [
                "action_type", "slot", "city_a", "city_b",
                "route_index", "cards", "ticket_ids",
            ],
            "additionalProperties": False,
        },
    ),
)

def _schema_for_phase(phase: Phase) -> components.ResponseFormatJSONSchema:
    if phase == Phase.KEEPING_TICKETS:
        return _KEEP_TICKETS_SCHEMA
    if phase == Phase.DRAWING_CARDS:
        return _DRAW_SECOND_CARD_SCHEMA
    return _CHOOSE_ACTION_SCHEMA


# ---------------------------------------------------------------------------
# Event → human-readable string
# ---------------------------------------------------------------------------

def _format_event(event: Event, my_name: str) -> Optional[str]:
    if isinstance(event, RouteClaimed):
        who = "You" if event.player_name == my_name else event.player_name
        cards = ", ".join(c.value for c in event.cards_spent)
        return (
            f"{who} claimed {event.route_id.city_a}→{event.route_id.city_b} "
            f"(+{event.points_scored}pts, paid [{cards}])"
        )
    if isinstance(event, CardDrawnFromDeck):
        if event.player_name == my_name:
            return None  # you already know from your action
        return f"{event.player_name} drew a card from the deck."
    if isinstance(event, CardDrawnFromFaceUp):
        if event.player_name == my_name:
            return None
        return f"{event.player_name} took a {event.card.value} from face-up slot {event.slot}."
    if isinstance(event, DestinationTicketsKept):
        if event.player_name == my_name:
            return None  # you know what you kept
        return f"{event.player_name} drew destination tickets (kept {len(event.kept)}, returned {len(event.returned)})."
    if isinstance(event, DestinationTicketsOffered):
        return None  # private; handled in the view prompt
    if isinstance(event, FaceUpCardsReset):
        cards = ", ".join(c.value for c in event.new_cards)
        return f"Face-up cards were reset (too many wilds) → [{cards}]"
    if isinstance(event, LastRoundTriggered):
        who = "You" if event.player_name == my_name else event.player_name
        return f"*** {who} triggered the LAST ROUND ({event.trains_remaining} trains left) ***"
    return None


# ---------------------------------------------------------------------------
# View → prompt (state summary for the current turn)
# ---------------------------------------------------------------------------

def _view_to_prompt(view: PlayerView) -> str:
    lines = []

    if view.last_round:
        lines.append("*** LAST ROUND in progress ***")

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

    else:
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

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Response → PlayerAction
# ---------------------------------------------------------------------------

def _parse_action(data: dict) -> PlayerAction:
    action_type = data["action_type"]

    if action_type == "draw_card":
        return DrawCardAction(slot=data.get("slot"))

    if action_type == "claim_route":
        return ClaimRouteAction(
            route_id=RouteId(data["city_a"], data["city_b"], int(data.get("route_index", 0))),
            cards=tuple(Color(c) for c in data["cards"]),
        )

    if action_type == "draw_tickets":
        return DrawTicketsAction()

    if action_type == "keep_tickets":
        return KeepTicketsAction(ticket_ids=tuple(int(i) for i in data["ticket_ids"]))

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
        system_prompt: str = SYSTEM_PROMPT,
        reasoning_effort: str = "medium",
    ) -> None:
        self._name = player_name
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._client = OpenRouter(api_key=api_key or os.environ["OPENROUTER_API_KEY"])
        self._messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        self._event_buffer: list[str] = []
        self._turn_count = 0

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_dir = Path(__file__).parent / "logs" / f"{player_name}_{ts}"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._call_count = 0

    @property
    def name(self) -> str:
        return self._name

    def on_event(self, event: Event) -> None:
        text = _format_event(event, self._name)
        if text:
            self._event_buffer.append(text)

    def choose_action(self, view: PlayerView, error: Optional[str] = None) -> PlayerAction:
        if error:
            self._messages.append({
                "role": "user",
                "content": f"Your action was REJECTED: {error}\nChoose a different valid action.",
            })
        else:
            self._turn_count += 1
            parts: list[str] = []

            if self._turn_count == 1:
                parts.append(f"You are playing Ticket to Ride as '{self._name}'.")

            if self._event_buffer:
                parts.append("=== EVENTS SINCE LAST TURN ===")
                parts.extend(self._event_buffer)
                self._event_buffer.clear()

            parts.append("")
            parts.append(f"--- Turn {self._turn_count} ---")
            parts.append(_view_to_prompt(view))

            self._messages.append({"role": "user", "content": "\n".join(parts)})

        print(f"  [LLM:{self._name}] turn {self._turn_count}, querying {self._model} ({len(self._messages)} messages)...", flush=True)

        resp = self._client.chat.send(
            model=self._model,
            timeout_ms=60000,
            messages=self._messages,
            response_format=_schema_for_phase(view.phase),
            reasoning=components.Reasoning(effort=self._reasoning_effort),
        )

        msg = resp.choices[0].message
        reasoning = getattr(msg, "reasoning", None) or ""
        content = msg.content or ""

        parts = []
        if reasoning:
            parts.append(f"<reasoning>\n{reasoning}\n</reasoning>")
        if content:
            parts.append(content)
        self._messages.append({"role": "assistant", "content": "\n".join(parts)})

        print(f"  [LLM:{self._name}] response: {content}", flush=True)
        if reasoning:
            preview = reasoning[:120].replace("\n", " ")
            print(f"  [LLM:{self._name}] reasoning: {preview}...", flush=True)

        self._log_turn()

        if not content:
            raise ValueError("Model returned empty content (reasoning only, no action JSON).")

        return _parse_action(json.loads(content))

    def _log_turn(self) -> None:
        self._call_count += 1
        entry = {
            "turn": self._turn_count,
            "call": self._call_count,
            "model": self._model,
            "messages": self._messages[:],
        }
        path = self._log_dir / f"{self._call_count:03d}.json"
        with open(path, "w") as f:
            json.dump(entry, f, indent=2)
