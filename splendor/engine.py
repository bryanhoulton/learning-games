"""
Splendor — Game Engine

Owns GameState and enforces all rules. Every mutation goes through here.
Emits Event objects that external code can observe.

Turn structure (exactly one action per turn):
  • take_different_gems  — take 2–3 tokens of distinct colours
  • take_double_gem      — take 2 tokens of the same colour (≥4 in supply)
  • reserve_board_card   — reserve a face-up card; take 1 gold if available
  • reserve_deck_top     — reserve the top of a tier deck; take 1 gold if available
  • buy_card             — buy from board or reserved; engine pays with bonuses + gems + gold

After any action:
  1. If gem total > 10 → AWAITING_DISCARD (call discard_gems)
  2. Else check which nobles the player qualifies for
     • 0 nobles → end turn
     • 1 noble  → auto-award, then end turn
     • 2+ nobles → AWAITING_NOBLE_CHOICE (call choose_noble)

End game: first player to end a turn with ≥ 15 VP triggers the final round.
Game ends when it would be player 0's turn again after the final round is set.

Usage:
    engine = GameEngine.new_game(["Alice", "Bob"])
    engine.take_different_gems("Alice", [GemColor.RUBY, GemColor.ONYX, GemColor.SAPPHIRE])
    engine.buy_card("Bob", 5)
"""

from __future__ import annotations

import random
from typing import Callable, Optional

from cards import ALL_NOBLE_IDS, CARD_REGISTRY, NOBLE_REGISTRY, TIER_CARD_IDS
from errors import (
    InsufficientGems,
    InvalidAction,
    InvalidCard,
    InvalidNoble,
    NotYourTurn,
    WrongPhase,
)
from events import (
    CardBought,
    CardReserved,
    Event,
    GameOver,
    GemsTaken,
    GemsReturned,
    NobleVisited,
    TurnEnded,
    TurnStarted,
)
from models import GEM_COLORS, GemColor, GameState, Phase, Player


class GameEngine:
    """
    Encapsulates all Splendor game logic.

    All public methods return list[Event] and raise GameError subclasses
    on illegal moves.
    """

    def __init__(self, state: GameState) -> None:
        self._state = state
        self._event_handlers: list[Callable[[Event], None]] = []

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def new_game(
        cls,
        player_names: list[str],
        seed: Optional[int] = None,
    ) -> "GameEngine":
        if seed is not None:
            random.seed(seed)

        if not 2 <= len(player_names) <= 4:
            raise ValueError("Splendor supports 2-4 players.")

        n = len(player_names)

        # Gem supply per player count
        gems_per_color = {2: 4, 3: 5, 4: 7}[n]
        gem_supply = {c: gems_per_color for c in GEM_COLORS}
        gem_supply[GemColor.GOLD] = 5

        # Shuffle decks per tier
        decks: dict[int, list[int]] = {}
        for tier in (1, 2, 3):
            ids = list(TIER_CARD_IDS[tier])
            random.shuffle(ids)
            decks[tier] = ids

        # Deal 4 face-up cards per tier
        board: dict[int, list[Optional[int]]] = {}
        for tier in (1, 2, 3):
            row: list[Optional[int]] = []
            for _ in range(4):
                row.append(decks[tier].pop() if decks[tier] else None)
            board[tier] = row

        # Choose nobles: num_players + 1
        noble_ids = random.sample(ALL_NOBLE_IDS, n + 1)

        players = [
            Player(
                name=name,
                gems={c: 0 for c in list(GemColor)},
            )
            for name in player_names
        ]

        state = GameState(
            players=players,
            board=board,
            decks=decks,
            nobles=noble_ids,
            gem_supply=gem_supply,
        )

        engine = cls(state)

        evt = TurnStarted(player_name=state.current_player.name)
        engine._emit(evt)

        return engine

    # ------------------------------------------------------------------
    # Event subscription
    # ------------------------------------------------------------------

    def subscribe(self, handler: Callable[[Event], None]) -> None:
        self._event_handlers.append(handler)

    def _emit(self, event: Event) -> None:
        for h in self._event_handlers:
            h(event)

    # ------------------------------------------------------------------
    # Public read access
    # ------------------------------------------------------------------

    @property
    def state(self) -> GameState:
        return self._state

    # ------------------------------------------------------------------
    # Main actions
    # ------------------------------------------------------------------

    def take_different_gems(
        self, player_name: str, colors: list[GemColor]
    ) -> list[Event]:
        """
        Take 2 or 3 tokens of different colours.
        • 3 colours: each must have ≥ 1 token available.
        • 2 colours: same rules apply (valid but uncommon; only when fewer than
          3 colours have tokens).
        Gold cannot be taken this way.
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.PLAYER_TURN)

        available_colors = [c for c in GEM_COLORS if s.gem_supply.get(c, 0) >= 1]
        if len(colors) == 1 and len(available_colors) > 1:
            raise InvalidAction("Can only take 1 gem when it is the sole remaining colour.")
        if not 1 <= len(colors) <= 3:
            raise InvalidAction("Must choose 1, 2, or 3 different gem colours.")

        if len(set(colors)) != len(colors):
            raise InvalidAction("All chosen colours must be different.")

        if GemColor.GOLD in colors:
            raise InvalidAction("Gold cannot be taken via this action.")

        for color in colors:
            if s.gem_supply.get(color, 0) < 1:
                raise InsufficientGems(
                    f"No {color.value} tokens left in supply."
                )

        player = s.current_player
        taken: dict[GemColor, int] = {}
        for color in colors:
            s.gem_supply[color] -= 1
            player.gems[color] = player.gems.get(color, 0) + 1
            taken[color] = taken.get(color, 0) + 1

        evt = GemsTaken(player_name=player_name, gems=taken)
        self._emit(evt)
        return [evt] + self._after_action(player_name)

    def take_double_gem(
        self, player_name: str, color: GemColor
    ) -> list[Event]:
        """
        Take 2 tokens of the same colour. Requires ≥ 4 of that colour in
        supply. Gold cannot be taken this way.
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.PLAYER_TURN)

        if color == GemColor.GOLD:
            raise InvalidAction("Gold cannot be taken via this action.")

        if s.gem_supply.get(color, 0) < 4:
            raise InsufficientGems(
                f"Need ≥ 4 {color.value} tokens to take double; "
                f"only {s.gem_supply.get(color, 0)} available."
            )

        player = s.current_player
        s.gem_supply[color] -= 2
        player.gems[color] = player.gems.get(color, 0) + 2

        evt = GemsTaken(player_name=player_name, gems={color: 2})
        self._emit(evt)
        return [evt] + self._after_action(player_name)

    def reserve_board_card(
        self, player_name: str, card_id: int
    ) -> list[Event]:
        """Reserve a face-up card from the board. Take 1 gold if available."""
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.PLAYER_TURN)

        player = s.current_player

        if len(player.reserved) >= 3:
            raise InvalidAction("Cannot reserve more than 3 cards.")

        # Find the card on the board
        tier = self._find_board_card(card_id)
        if tier is None:
            raise InvalidCard(
                f"Card {card_id} is not face-up on the board."
            )

        # Remove from board slot and refill
        slot = s.board[tier].index(card_id)
        s.board[tier][slot] = None
        self._refill_slot(tier, slot)

        player.reserved.append(card_id)
        gold_taken = self._give_gold(player)

        evt = CardReserved(
            player_name=player_name,
            card_id=card_id,
            tier=tier,
            gold_taken=gold_taken,
        )
        self._emit(evt)
        return [evt] + self._after_action(player_name)

    def reserve_deck_top(
        self, player_name: str, tier: int
    ) -> list[Event]:
        """Reserve the top card from a tier deck. Take 1 gold if available."""
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.PLAYER_TURN)

        if tier not in (1, 2, 3):
            raise InvalidAction(f"Tier must be 1, 2, or 3; got {tier}.")

        player = s.current_player

        if len(player.reserved) >= 3:
            raise InvalidAction("Cannot reserve more than 3 cards.")

        if not s.decks[tier]:
            raise InvalidAction(f"Tier {tier} deck is empty.")

        card_id = s.decks[tier].pop()
        player.reserved.append(card_id)
        gold_taken = self._give_gold(player)

        evt = CardReserved(
            player_name=player_name,
            card_id=card_id,
            tier=tier,
            gold_taken=gold_taken,
        )
        self._emit(evt)
        return [evt] + self._after_action(player_name)

    def buy_card(
        self, player_name: str, card_id: int
    ) -> list[Event]:
        """
        Buy a card from the face-up board or from your reserved cards.

        Payment is computed automatically:
          1. Subtract permanent bonuses (purchased cards) from cost.
          2. Pay remaining with gems; use gold for any shortfall.
        Raises InsufficientGems if the player cannot afford the card.
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.PLAYER_TURN)

        player = s.current_player
        card_def = CARD_REGISTRY.get(card_id)
        if card_def is None:
            raise InvalidCard(f"Unknown card ID {card_id}.")

        # Card must be on board or in player's reserved
        from_board = self._find_board_card(card_id)
        from_reserved = card_id in player.reserved

        if from_board is None and not from_reserved:
            raise InvalidCard(
                f"Card {card_id} is not available to buy "
                "(not on board or in your reserved cards)."
            )

        # Calculate payment
        bonuses = self._player_bonuses(player)
        gems_paid: dict[GemColor, int] = {}
        gold_needed = 0

        for color, amount in card_def.cost.items():
            owed = max(0, amount - bonuses.get(color, 0))
            have = player.gems.get(color, 0)
            pay = min(owed, have)
            shortfall = owed - pay
            gems_paid[color] = pay
            gold_needed += shortfall

        if gold_needed > player.gems.get(GemColor.GOLD, 0):
            raise InsufficientGems(
                f"Cannot afford card {card_id}. "
                f"Need {gold_needed} gold but have "
                f"{player.gems.get(GemColor.GOLD, 0)}."
            )

        # Deduct gems from player and return to supply
        for color, amount in gems_paid.items():
            player.gems[color] -= amount
            s.gem_supply[color] = s.gem_supply.get(color, 0) + amount

        if gold_needed:
            player.gems[GemColor.GOLD] -= gold_needed
            s.gem_supply[GemColor.GOLD] = s.gem_supply.get(GemColor.GOLD, 0) + gold_needed

        # Move card to purchased
        if from_board is not None:
            slot = s.board[from_board].index(card_id)
            s.board[from_board][slot] = None
            self._refill_slot(from_board, slot)
        else:
            player.reserved.remove(card_id)

        player.purchased.append(card_id)

        evt = CardBought(
            player_name=player_name,
            card_id=card_id,
            gems_paid={c: v for c, v in gems_paid.items() if v > 0},
            gold_used=gold_needed,
        )
        self._emit(evt)
        return [evt] + self._after_action(player_name)

    # ------------------------------------------------------------------
    # Resolution actions
    # ------------------------------------------------------------------

    def discard_gems(
        self, player_name: str, gems: dict[GemColor, int]
    ) -> list[Event]:
        """
        Return gems to bring hand total to ≤ 10.
        Called when in AWAITING_DISCARD phase.
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.AWAITING_DISCARD)

        player = s.current_player
        total_before = _gem_total(player.gems)
        total_returning = sum(gems.values())
        total_after = total_before - total_returning

        if total_after > 10:
            raise InvalidAction(
                f"After returning {total_returning} gem(s) you would still have "
                f"{total_after} (must be ≤ 10)."
            )

        for color, amount in gems.items():
            if amount <= 0:
                continue
            if player.gems.get(color, 0) < amount:
                raise InsufficientGems(
                    f"Cannot return {amount} {color.value}; "
                    f"you only have {player.gems.get(color, 0)}."
                )
            player.gems[color] -= amount
            s.gem_supply[color] = s.gem_supply.get(color, 0) + amount

        evt = GemsReturned(player_name=player_name, gems={c: v for c, v in gems.items() if v > 0})
        self._emit(evt)

        s.phase = Phase.PLAYER_TURN  # reset so _check_nobles_then_end works
        return [evt] + self._check_nobles_then_end(player_name)

    def choose_noble(
        self, player_name: str, noble_id: int
    ) -> list[Event]:
        """
        Choose which noble to receive when multiple qualify.
        Called when in AWAITING_NOBLE_CHOICE phase.
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.AWAITING_NOBLE_CHOICE)

        if noble_id not in s.pending_noble_choices:
            raise InvalidNoble(
                f"Noble {noble_id} is not among your choices: "
                f"{s.pending_noble_choices}."
            )

        s.pending_noble_choices = []
        events = self._award_noble(s.current_player, noble_id)
        return events + self._end_turn()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assert_active(self, player_name: str) -> None:
        if self._state.current_player.name != player_name:
            raise NotYourTurn(
                f"It is {self._state.current_player.name}'s turn, not {player_name}'s."
            )

    def _assert_phase(self, *allowed: Phase) -> None:
        if self._state.phase not in allowed:
            raise WrongPhase(
                f"Expected phase(s) {[p.name for p in allowed]}, "
                f"got {self._state.phase.name}."
            )

    def _give_gold(self, player: Player) -> bool:
        """Give player 1 gold token if supply has any. Returns True if given."""
        s = self._state
        if s.gem_supply.get(GemColor.GOLD, 0) > 0:
            s.gem_supply[GemColor.GOLD] -= 1
            player.gems[GemColor.GOLD] = player.gems.get(GemColor.GOLD, 0) + 1
            return True
        return False

    def _find_board_card(self, card_id: int) -> Optional[int]:
        """Return the tier where card_id is face-up, or None."""
        for tier, row in self._state.board.items():
            if card_id in row:
                return tier
        return None

    def _refill_slot(self, tier: int, slot: int) -> None:
        """Fill an empty board slot from the tier deck if possible."""
        s = self._state
        if s.decks[tier]:
            s.board[tier][slot] = s.decks[tier].pop()

    def _player_bonuses(self, player: Player) -> dict[GemColor, int]:
        """Count purchased card bonuses by colour."""
        bonuses: dict[GemColor, int] = {c: 0 for c in GEM_COLORS}
        for card_id in player.purchased:
            color = CARD_REGISTRY[card_id].bonus_color
            bonuses[color] += 1
        return bonuses

    def _player_vp(self, player: Player) -> int:
        card_vp = sum(CARD_REGISTRY[cid].vp for cid in player.purchased)
        noble_vp = sum(NOBLE_REGISTRY[nid].vp for nid in player.nobles)
        return card_vp + noble_vp

    def _eligible_nobles(self, player: Player) -> list[int]:
        """Return IDs of nobles on the board that the player currently qualifies for."""
        s = self._state
        bonuses = self._player_bonuses(player)
        result = []
        for noble_id in s.nobles:
            noble = NOBLE_REGISTRY[noble_id]
            if all(bonuses.get(c, 0) >= req for c, req in noble.requirements.items()):
                result.append(noble_id)
        return result

    def _award_noble(self, player: Player, noble_id: int) -> list[Event]:
        """Move noble from board to player. Emit NobleVisited."""
        s = self._state
        s.nobles.remove(noble_id)
        player.nobles.append(noble_id)
        evt = NobleVisited(player_name=player.name, noble_id=noble_id)
        self._emit(evt)
        return [evt]

    def _after_action(self, player_name: str) -> list[Event]:
        """
        Called after every main action. Handles gem overflow and noble checks.
        Returns additional events. May change phase.
        """
        s = self._state
        player = s.current_player

        # Step 1: gem overflow
        if _gem_total(player.gems) > 10:
            s.phase = Phase.AWAITING_DISCARD
            return []

        # Step 2: nobles + end turn
        return self._check_nobles_then_end(player_name)

    def _check_nobles_then_end(self, player_name: str) -> list[Event]:
        """Check noble eligibility then end the turn (or wait for noble choice)."""
        s = self._state
        player = s.current_player
        eligible = self._eligible_nobles(player)

        if len(eligible) == 0:
            return self._end_turn()
        elif len(eligible) == 1:
            events = self._award_noble(player, eligible[0])
            return events + self._end_turn()
        else:
            # Multiple nobles qualify — player must choose
            s.pending_noble_choices = list(eligible)
            s.phase = Phase.AWAITING_NOBLE_CHOICE
            return []

    def _end_turn(self) -> list[Event]:
        """
        Emit TurnEnded, check for final-round trigger, advance to next player.
        If the final round was triggered and we've wrapped back to player 0, end game.
        """
        s = self._state
        player = s.current_player
        vp = self._player_vp(player)
        events: list[Event] = []

        turn_evt = TurnEnded(player_name=player.name, vp=vp)
        events.append(turn_evt)
        self._emit(turn_evt)

        # Trigger final round if any player reached 15 VP
        if vp >= 15 and not s.final_round:
            s.final_round = True

        # Advance
        next_index = (s.current_player_index + 1) % s.num_players
        if s.final_round and next_index == 0:
            return events + self._end_game()

        s.current_player_index = next_index
        s.phase = Phase.PLAYER_TURN

        start_evt = TurnStarted(player_name=s.current_player.name)
        events.append(start_evt)
        self._emit(start_evt)
        return events

    def _end_game(self) -> list[Event]:
        s = self._state
        s.phase = Phase.GAME_OVER

        scores = {p.name: self._player_vp(p) for p in s.players}

        # Tie-break: fewer purchased cards wins
        def sort_key(name: str):
            p = next(pl for pl in s.players if pl.name == name)
            return (-scores[name], len(p.purchased))

        winner = min(scores.keys(), key=sort_key)

        evt = GameOver(scores=scores, winner=winner)
        self._emit(evt)
        return [evt]


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------

def _gem_total(gems: dict) -> int:
    return sum(gems.values())
