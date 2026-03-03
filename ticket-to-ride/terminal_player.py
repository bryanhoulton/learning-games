"""
TerminalPlayerAgent — interactive terminal implementation of PlayerAgent.

Ports all the interactive UI logic from cli.py into a proper agent class.
"""

from __future__ import annotations

import sys
from collections import Counter
from typing import Optional

from events import (
    CardDrawnFromDeck,
    CardDrawnFromFaceUp,
    DestinationTicketsKept,
    DestinationTicketsOffered,
    Event,
    FaceUpCardReplaced,
    FaceUpCardsReset,
    GameOver,
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

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

COLOR_CODES = {
    Color.RED:    "\033[91m",
    Color.BLUE:   "\033[94m",
    Color.GREEN:  "\033[92m",
    Color.YELLOW: "\033[93m",
    Color.ORANGE: "\033[38;5;208m",
    Color.PINK:   "\033[95m",
    Color.WHITE:  "\033[97m",
    Color.BLACK:  "\033[90m",
    Color.WILD:   "\033[96m",
}

PLAYER_COLOR_CODES = ["91", "94", "92", "93", "90"]  # red blue green yellow black


def colorize(color: Color, text: str) -> str:
    return f"{COLOR_CODES[color]}{text}{RESET}"


def bold(text: str) -> str:
    return f"{BOLD}{text}{RESET}"


def dim(text: str) -> str:
    return f"{DIM}{text}{RESET}"


def player_label(name: str, index: int) -> str:
    code = PLAYER_COLOR_CODES[index % len(PLAYER_COLOR_CODES)]
    return f"\033[{code}m{bold(name)}{RESET}"


def card_str(c: Color) -> str:
    return colorize(c, c.value.upper())


def hand_summary(hand: tuple[Color, ...]) -> str:
    counts = Counter(hand)
    parts = []
    for color in Color:
        if counts[color]:
            parts.append(f"{card_str(color)}×{counts[color]}")
    return "  ".join(parts) if parts else dim("(empty)")


def sep(char: str = "─", width: int = 60) -> None:
    print(dim(char * width))


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def _ask(prompt: str) -> str:
    try:
        return input(f"\n{prompt} ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")
        sys.exit(0)


def _choose(prompt: str, options: list[str], allow_back: bool = False) -> Optional[int]:
    """Display numbered options, return 0-based index. Returns None if user types 'b'."""
    print()
    for i, opt in enumerate(options):
        print(f"  {bold(str(i+1))}) {opt}")
    if allow_back:
        print(f"  {dim('b')} {dim('back')}")
    while True:
        raw = _ask(prompt + f" [1-{len(options)}]:")
        if allow_back and raw.lower() == "b":
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print("  Invalid choice, try again.")


# ---------------------------------------------------------------------------
# Display helpers (work with PlayerView)
# ---------------------------------------------------------------------------

def print_status(view: PlayerView) -> None:
    sep()
    # Print self first, then opponents in order
    all_players = []
    opp_iter = iter(view.opponents)
    for i in range(view.num_players):
        if i == view.my_index:
            all_players.append((i, view.my_name, view.my_score, view.my_trains_remaining,
                                 len(view.my_hand), len(view.my_tickets)))
        else:
            opp = next(opp_iter)
            all_players.append((i, opp.name, opp.score, opp.trains_remaining,
                                 opp.hand_size, opp.ticket_count))

    for i, name, score, trains, cards, tickets in all_players:
        label = player_label(name, i)
        marker = bold("▶") if name == view.current_player_name else " "
        print(
            f"  {marker} {label:30s}  "
            f"score={bold(str(score))}  "
            f"trains={trains}  "
            f"cards={cards}  "
            f"tickets={tickets}"
        )
    sep()
    face_up_str = "  ".join(
        f"{i+1}:{card_str(c)}" for i, c in enumerate(view.face_up_cards)
    )
    print(f"  Face-up: {face_up_str}")
    print(f"  Deck: {view.train_deck_size} card(s) remaining   Destination deck: {view.destination_deck_size}")
    sep()


def print_hand(view: PlayerView) -> None:
    print(f"\n  {bold(view.my_name)}'s hand: {hand_summary(view.my_hand)}")


def print_tickets(view: PlayerView) -> None:
    from collections import defaultdict, deque
    from scoring import _build_adjacency, _cities_connected

    # Build adjacency from all_claimed_routes for this player
    adj: dict[str, set[str]] = defaultdict(set)
    for rid, owner_name in view.all_claimed_routes.items():
        if owner_name == view.my_name:
            adj[rid.city_a].add(rid.city_b)
            adj[rid.city_b].add(rid.city_a)

    print(f"\n  {bold(view.my_name)}'s destination tickets:")
    if not view.my_tickets:
        print(dim("    (none)"))
        return
    for t in view.my_tickets:
        done = _cities_connected(adj, t.city_a, t.city_b)
        status = "\033[92m✓\033[0m" if done else "\033[91m✗\033[0m"
        pts = f"+{t.points}" if done else f"-{t.points}"
        print(f"    {status} {t.city_a} ↔ {t.city_b}  [{pts} pts]")


def print_game_over(event: GameOver) -> None:
    sep("═")
    print(bold("\n  GAME OVER\n"))
    sorted_scores = sorted(event.scores.items(), key=lambda x: -x[1])
    for i, (name, score) in enumerate(sorted_scores):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "  "
        print(f"  {medal}  {bold(name):20s}  {score} pts")
    print(f"\n  {bold('Winner:')} {event.winner}")
    sep("═")


# ---------------------------------------------------------------------------
# Route affordability helpers (work with hand counts from PlayerView)
# ---------------------------------------------------------------------------

def _cheapest_payment(route, hand_counts: Counter, wild_count: int) -> Optional[list[Color]]:
    """Return a valid payment list or None if unaffordable."""
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
            payment = [color] * have + [Color.WILD] * needed
            if best is None:
                best = payment

    return best


def _claimable_routes(view: PlayerView) -> list[tuple[RouteId, list[Color]]]:
    """Return list of (route_id, cheapest_payment) for routes the player can afford."""
    hand_counts = Counter(view.my_hand)
    wild_count = hand_counts[Color.WILD]

    claimable = []
    for rid, route in sorted(view.routes.items(), key=lambda x: (x[1].city_a, x[1].city_b, x[1].index)):
        if rid in view.all_claimed_routes:
            continue
        if view.my_trains_remaining < route.length:
            continue

        # Double-route restriction for small games
        if view.num_players <= 3:
            sibling_blocked = False
            for idx in range(2):
                sibling = RouteId(route.city_a, route.city_b, idx)
                if sibling != rid and sibling in view.all_claimed_routes:
                    if view.all_claimed_routes[sibling] == view.my_name:
                        sibling_blocked = True
                        break
            if sibling_blocked:
                continue

        payment = _cheapest_payment(route, hand_counts, wild_count)
        if payment is not None:
            claimable.append((rid, payment))

    return claimable


# ---------------------------------------------------------------------------
# TerminalPlayerAgent
# ---------------------------------------------------------------------------

class TerminalPlayerAgent(PlayerAgent):

    def __init__(self, player_name: str) -> None:
        self._name = player_name
        self._routes: dict = {}  # cached from last view for use in on_event

    @property
    def name(self) -> str:
        return self._name

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def on_event(self, event: Event) -> None:
        if isinstance(event, CardDrawnFromDeck):
            print(f"  {bold(event.player_name)} draws a card from the deck.")
        elif isinstance(event, CardDrawnFromFaceUp):
            print(f"  {bold(event.player_name)} takes {card_str(event.card)} from slot {event.slot+1}.")
        elif isinstance(event, FaceUpCardReplaced):
            print(dim(f"  Slot {event.slot+1} refilled with {card_str(event.new_card)}."))
        elif isinstance(event, FaceUpCardsReset):
            print(f"  {bold('3 locomotives!')} Face-up cards reshuffled.")
        elif isinstance(event, DestinationTicketsOffered):
            pass  # handled interactively via choose_action
        elif isinstance(event, DestinationTicketsKept):
            kept = len(event.kept)
            returned = len(event.returned)
            print(f"  {bold(event.player_name)} keeps {kept} ticket(s), returns {returned}.")
        elif isinstance(event, RouteClaimed):
            spent = "  ".join(card_str(c) for c in event.cards_spent)
            route = self._routes.get(event.route_id)
            if route:
                print(
                    f"  {bold(event.player_name)} claims "
                    f"{bold(route.city_a)} → {bold(route.city_b)} "
                    f"(+{event.points_scored} pts)  [{spent}]"
                )
            else:
                print(
                    f"  {bold(event.player_name)} claims a route "
                    f"(+{event.points_scored} pts)  [{spent}]"
                )
        elif isinstance(event, LastRoundTriggered):
            print(f"\n  {bold('⚠  LAST ROUND!')} {event.player_name} has only {event.trains_remaining} trains left.")
        elif isinstance(event, GameOver):
            print_game_over(event)

    # ------------------------------------------------------------------
    # Action selection
    # ------------------------------------------------------------------

    def choose_action(self, view: PlayerView, error: Optional[str] = None) -> PlayerAction:
        self._routes = view.routes  # cache for on_event route name lookups

        if error:
            print(f"  {bold('Error:')} {error}")

        if view.phase == Phase.KEEPING_TICKETS:
            return self._choose_keep_tickets(view)
        elif view.phase == Phase.DRAWING_CARDS:
            return self._choose_second_card(view)
        else:
            return self._choose_main_action(view)

    def _choose_main_action(self, view: PlayerView) -> PlayerAction:
        print(f"\n{player_label(view.my_name, view.my_index)}'s turn")
        print_status(view)
        print_hand(view)

        while True:
            action = _choose(
                "Choose action:",
                ["Draw train cards", "Claim a route", "Draw destination tickets", "View my tickets"],
            )
            if action == 0:
                return self._choose_first_card(view)
            elif action == 1:
                result = self._choose_claim_route(view)
                if result is not None:
                    return result
                # returned None = user went back; re-show menu
            elif action == 2:
                return DrawTicketsAction()
            elif action == 3:
                print_tickets(view)
                # viewing tickets doesn't cost a turn — loop back

    def _choose_first_card(self, view: PlayerView) -> DrawCardAction:
        face_up_str = "  ".join(
            f"{i+1}:{card_str(c)}" for i, c in enumerate(view.face_up_cards)
        )
        print(f"\n  Face-up: {face_up_str}  |  {len(view.face_up_cards)+1}: deck")
        slots = [f"Take {card_str(c)} (slot {i+1})" for i, c in enumerate(view.face_up_cards)]
        slots.append("Draw from deck (blind)")
        choice = _choose("Which card?", slots)
        if choice == len(view.face_up_cards):
            return DrawCardAction(slot=None)
        return DrawCardAction(slot=choice)

    def _choose_second_card(self, view: PlayerView) -> DrawCardAction:
        print_hand(view)
        face_up_str = "  ".join(
            f"{i+1}:{card_str(c)}" for i, c in enumerate(view.face_up_cards)
        )
        print(f"\n  Face-up: {face_up_str}  |  {len(view.face_up_cards)+1}: deck")
        print(dim("  (Draw your second card — no face-up locomotives)"))
        slots = [f"Take {card_str(c)} (slot {i+1})" for i, c in enumerate(view.face_up_cards)]
        slots.append("Draw from deck (blind)")
        choice = _choose("Which card?", slots)
        if choice == len(view.face_up_cards):
            return DrawCardAction(slot=None)
        return DrawCardAction(slot=choice)

    def _choose_claim_route(self, view: PlayerView) -> Optional[ClaimRouteAction]:
        claimable = _claimable_routes(view)
        if not claimable:
            print(dim("  No routes you can afford right now."))
            return None

        options = []
        for rid, payment in claimable:
            route = view.routes[rid]
            payment_str = "  ".join(card_str(c) for c in payment)
            color_str = colorize(route.color, route.color.value) if route.color != Color.WILD else dim("any")
            options.append(
                f"{route.city_a} → {route.city_b}  "
                f"(len={route.length}, {color_str})  "
                f"cost: {payment_str}  +{route.points}pts"
            )

        choice = _choose("Which route to claim? (b=back)", options, allow_back=True)
        if choice is None:
            return None

        rid, payment = claimable[choice]
        return ClaimRouteAction(route_id=rid, cards=tuple(payment))

    def _choose_keep_tickets(self, view: PlayerView) -> KeepTicketsAction:
        tickets = view.pending_tickets
        min_keep = view.min_tickets_to_keep

        print(f"\n  Choose destination tickets to keep (minimum {min_keep}):")
        for i, t in enumerate(tickets):
            print(f"    {bold(str(i+1))}) {t.city_a} ↔ {t.city_b}  [{t.points} pts]")

        while True:
            raw = _ask(f"  Enter numbers to keep (e.g. 1 2), min {min_keep}:")
            try:
                chosen = [int(x) - 1 for x in raw.split()]
                if len(chosen) < min_keep:
                    print(f"  Must keep at least {min_keep}.")
                    continue
                if not all(0 <= c < len(tickets) for c in chosen):
                    print("  Invalid selection.")
                    continue
                chosen_ids = tuple(tickets[c].id for c in chosen)
                return KeepTicketsAction(ticket_ids=chosen_ids)
            except ValueError as e:
                print(f"  Error: {e}")
