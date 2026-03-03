"""
Dominion — Game Engine

Owns GameState and enforces all rules. Every mutation goes through here.
Emits Event objects that external code can observe.

Turn structure:
  1. ACTION phase  — play action cards (or call end_action_phase to skip)
  2. BUY phase     — play treasures, buy cards (or call end_buy_phase to skip)
  3. Cleanup       — automatic on end_buy_phase: discard everything, draw 5

Multi-step card effects interrupt the turn with an AWAITING_* phase.
The active decider during AWAITING_MILITIA_DISCARD is militia_targets[0],
not current_player.

Usage:
    engine = GameEngine.new_game(["Alice", "Bob"])
    engine.end_action_phase("Alice")
    engine.play_all_treasures("Alice")
    engine.buy_card("Alice", CardName.SILVER)
    engine.end_buy_phase("Alice")
"""

from __future__ import annotations

import random
from typing import Callable, Optional

from cards import CARD_REGISTRY, FIRST_GAME_KINGDOM, supply_counts
from errors import (
    InsufficientCards,
    InvalidAction,
    InvalidCard,
    NotYourTurn,
    WrongPhase,
)
from events import (
    ActionPlayed,
    CardBought,
    CardGained,
    CardTrashed,
    CardsDiscarded,
    CardsDrawn,
    Event,
    GameOver,
    MilitiaAttack,
    MilitiaBlocked,
    TreasurePlayed,
    TurnEnded,
    TurnStarted,
)
from models import CardName, CardType, GameState, Phase, Player


class GameEngine:
    """
    Encapsulates all Dominion game logic.

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
        kingdom: Optional[list[CardName]] = None,
        seed: Optional[int] = None,
    ) -> "GameEngine":
        if seed is not None:
            random.seed(seed)

        if not 2 <= len(player_names) <= 4:
            raise ValueError("Dominion supports 2-4 players.")

        if kingdom is None:
            kingdom = FIRST_GAME_KINGDOM

        if len(kingdom) != 10:
            raise ValueError("Kingdom must contain exactly 10 cards.")

        supply = supply_counts(len(player_names), kingdom)

        players = []
        for name in player_names:
            p = Player(name=name)
            # Starting deck: 7 Copper + 3 Estate, shuffled
            p.draw_pile = [CardName.COPPER] * 7 + [CardName.ESTATE] * 3
            random.shuffle(p.draw_pile)
            players.append(p)

        state = GameState(
            players=players,
            supply=supply,
            trash=[],
            current_player_index=0,
            phase=Phase.ACTION,
            actions=1,
            buys=1,
            coins=0,
        )

        engine = cls(state)

        # Each player draws their opening hand of 5
        for player in state.players:
            engine._draw_cards(player, 5)

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
    # Action phase
    # ------------------------------------------------------------------

    def play_action(self, player_name: str, card_name: CardName) -> list[Event]:
        """Play an action card from hand. Decrements actions by 1."""
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.ACTION)

        player = s.current_player
        if card_name not in player.hand:
            raise InsufficientCards(f"{card_name.value} is not in your hand.")

        card_def = CARD_REGISTRY[card_name]
        if CardType.ACTION not in card_def.types and CardType.REACTION not in card_def.types:
            raise InvalidCard(f"{card_name.value} is not an action card.")

        if s.actions < 1:
            raise InvalidAction("No actions remaining.")

        # Spend the action and move card to played area
        s.actions -= 1
        player.hand.remove(card_name)
        player.played.append(card_name)

        evt = ActionPlayed(player_name=player_name, card=card_name)
        self._emit(evt)
        events: list[Event] = [evt]

        events += self._apply_action_effects(player, card_def)
        return events

    def end_action_phase(self, player_name: str) -> list[Event]:
        """Move directly to BUY phase (skipping remaining actions)."""
        self._assert_active(player_name)
        self._assert_phase(Phase.ACTION)
        self._state.phase = Phase.BUY
        return []

    # ------------------------------------------------------------------
    # Multi-step card resolutions
    # ------------------------------------------------------------------

    def resolve_cellar(self, player_name: str, discard_cards: list[CardName]) -> list[Event]:
        """
        Discard any number of cards from hand, then draw that many.
        Called after play_action(Cellar).
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.AWAITING_CELLAR_DISCARD)

        player = s.current_player

        # Validate cards are in hand
        hand_copy = player.hand[:]
        for card in discard_cards:
            if card not in hand_copy:
                raise InsufficientCards(f"{card.value} is not in your hand.")
            hand_copy.remove(card)

        events: list[Event] = []

        # Discard the chosen cards
        for card in discard_cards:
            player.hand.remove(card)
            player.discard.append(card)

        if discard_cards:
            evt = CardsDiscarded(player_name=player_name, cards=list(discard_cards))
            events.append(evt)
            self._emit(evt)

        # Draw replacement cards
        drawn = self._draw_cards(player, len(discard_cards))
        if drawn:
            evt = CardsDrawn(player_name=player_name, count=len(drawn))
            events.append(evt)
            self._emit(evt)

        s.phase = Phase.ACTION
        return events

    def resolve_mine_trash(self, player_name: str, trash_card: CardName) -> list[Event]:
        """
        Trash a treasure from hand (step 1 of Mine).
        Transitions to AWAITING_MINE_GAIN.
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.AWAITING_MINE_TRASH)

        player = s.current_player
        if trash_card not in player.hand:
            raise InsufficientCards(f"{trash_card.value} is not in your hand.")

        card_def = CARD_REGISTRY[trash_card]
        if CardType.TREASURE not in card_def.types:
            raise InvalidCard(f"{trash_card.value} is not a Treasure.")

        player.hand.remove(trash_card)
        s.trash.append(trash_card)
        s.pending_gain_max_cost = card_def.cost + 3
        s.pending_gain_to_hand = True

        evt = CardTrashed(player_name=player_name, card=trash_card)
        self._emit(evt)

        # Check if there's anything to gain (must be a treasure ≤ max cost in supply)
        valid = self._valid_gain_cards(CardType.TREASURE, s.pending_gain_max_cost)
        if not valid:
            # No valid treasures to gain — skip the gain step
            s.phase = Phase.ACTION
            return [evt]

        s.phase = Phase.AWAITING_MINE_GAIN
        return [evt]

    def resolve_mine_gain(self, player_name: str, gain_card: CardName) -> list[Event]:
        """
        Gain a treasure to hand (step 2 of Mine).
        The card must cost ≤ (trashed card cost + 3).
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.AWAITING_MINE_GAIN)

        card_def = CARD_REGISTRY[gain_card]
        if CardType.TREASURE not in card_def.types:
            raise InvalidCard(f"{gain_card.value} is not a Treasure.")

        if card_def.cost > s.pending_gain_max_cost:
            raise InvalidAction(
                f"{gain_card.value} costs {card_def.cost}, max allowed is {s.pending_gain_max_cost}."
            )

        events: list[Event] = []
        evt = self._gain_card(s.current_player, gain_card, to_hand=True)
        events.append(evt)

        s.phase = Phase.ACTION
        return events

    def resolve_remodel_trash(self, player_name: str, trash_card: CardName) -> list[Event]:
        """
        Trash any card from hand (step 1 of Remodel).
        Transitions to AWAITING_REMODEL_GAIN.
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.AWAITING_REMODEL_TRASH)

        player = s.current_player
        if trash_card not in player.hand:
            raise InsufficientCards(f"{trash_card.value} is not in your hand.")

        card_def = CARD_REGISTRY[trash_card]
        player.hand.remove(trash_card)
        s.trash.append(trash_card)
        s.pending_gain_max_cost = card_def.cost + 2
        s.pending_gain_to_hand = False

        evt = CardTrashed(player_name=player_name, card=trash_card)
        self._emit(evt)

        # Check if there's anything valid to gain
        valid = [
            name for name, count in s.supply.items()
            if count > 0 and CARD_REGISTRY[name].cost <= s.pending_gain_max_cost
        ]
        if not valid:
            s.phase = Phase.ACTION
            return [evt]

        s.phase = Phase.AWAITING_REMODEL_GAIN
        return [evt]

    def resolve_remodel_gain(self, player_name: str, gain_card: CardName) -> list[Event]:
        """
        Gain any card to discard (step 2 of Remodel).
        The card must cost ≤ (trashed card cost + 2).
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.AWAITING_REMODEL_GAIN)

        card_def = CARD_REGISTRY[gain_card]
        if card_def.cost > s.pending_gain_max_cost:
            raise InvalidAction(
                f"{gain_card.value} costs {card_def.cost}, max allowed is {s.pending_gain_max_cost}."
            )

        if s.supply.get(gain_card, 0) < 1:
            raise InvalidAction(f"{gain_card.value} is not available in the supply.")

        evt = self._gain_card(s.current_player, gain_card, to_hand=False)
        s.phase = Phase.ACTION
        return [evt]

    def resolve_workshop(self, player_name: str, gain_card: CardName) -> list[Event]:
        """Gain a card costing up to 4 to discard."""
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.AWAITING_WORKSHOP_GAIN)

        card_def = CARD_REGISTRY[gain_card]
        if card_def.cost > 4:
            raise InvalidAction(
                f"{gain_card.value} costs {card_def.cost}; Workshop can only gain cards costing up to 4."
            )

        if s.supply.get(gain_card, 0) < 1:
            raise InvalidAction(f"{gain_card.value} is not available in the supply.")

        evt = self._gain_card(s.current_player, gain_card, to_hand=False)
        s.phase = Phase.ACTION
        return [evt]

    def resolve_militia_discard(
        self, player_name: str, discard_cards: list[CardName]
    ) -> list[Event]:
        """
        The front militia target discards cards until they have ≤3.
        This is called by an opponent of the current player.
        """
        s = self._state
        self._assert_phase(Phase.AWAITING_MILITIA_DISCARD)

        if not s.militia_targets:
            raise InvalidAction("No militia targets remaining.")

        target_idx = s.militia_targets[0]
        target = s.players[target_idx]

        if target.name != player_name:
            raise NotYourTurn(
                f"Waiting for {target.name} to discard, not {player_name}."
            )

        required_discards = max(0, len(target.hand) - 3)
        if len(discard_cards) != required_discards:
            raise InvalidAction(
                f"Must discard exactly {required_discards} card(s) "
                f"(hand has {len(target.hand)}, must end at 3)."
            )

        hand_copy = target.hand[:]
        for card in discard_cards:
            if card not in hand_copy:
                raise InsufficientCards(f"{card.value} is not in your hand.")
            hand_copy.remove(card)

        events: list[Event] = []
        for card in discard_cards:
            target.hand.remove(card)
            target.discard.append(card)

        if discard_cards:
            evt = CardsDiscarded(player_name=player_name, cards=list(discard_cards))
            events.append(evt)
            self._emit(evt)

        s.militia_targets.pop(0)

        if not s.militia_targets:
            s.phase = Phase.ACTION

        return events

    # ------------------------------------------------------------------
    # Buy phase
    # ------------------------------------------------------------------

    def play_treasure(self, player_name: str, card_name: CardName) -> list[Event]:
        """Play a single treasure from hand, adding its coins to the pool."""
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.BUY)

        player = s.current_player
        if card_name not in player.hand:
            raise InsufficientCards(f"{card_name.value} is not in your hand.")

        card_def = CARD_REGISTRY[card_name]
        if CardType.TREASURE not in card_def.types:
            raise InvalidCard(f"{card_name.value} is not a Treasure.")

        player.hand.remove(card_name)
        player.played.append(card_name)
        s.coins += card_def.coins

        evt = TreasurePlayed(
            player_name=player_name,
            card=card_name,
            coins_added=card_def.coins,
            total_coins=s.coins,
        )
        self._emit(evt)
        return [evt]

    def play_all_treasures(self, player_name: str) -> list[Event]:
        """Play every treasure currently in hand."""
        self._assert_active(player_name)
        self._assert_phase(Phase.BUY)

        player = self._state.current_player
        treasures = [c for c in player.hand if CardType.TREASURE in CARD_REGISTRY[c].types]

        events: list[Event] = []
        for card in treasures:
            events += self.play_treasure(player_name, card)
        return events

    def buy_card(self, player_name: str, card_name: CardName) -> list[Event]:
        """
        Buy one card from the supply.
        Costs 1 buy + the card's coin cost.
        """
        s = self._state
        self._assert_active(player_name)
        self._assert_phase(Phase.BUY)

        if s.buys < 1:
            raise InvalidAction("No buys remaining.")

        if card_name not in CARD_REGISTRY:
            raise InvalidCard(f"{card_name.value} is not a valid card.")

        card_def = CARD_REGISTRY[card_name]

        if card_def.cost > s.coins:
            raise InvalidAction(
                f"{card_name.value} costs {card_def.cost} but you only have {s.coins} coin(s)."
            )

        if s.supply.get(card_name, 0) < 1:
            raise InvalidAction(f"{card_name.value} is not available in the supply.")

        s.supply[card_name] -= 1
        s.buys -= 1
        s.coins -= card_def.cost
        s.current_player.discard.append(card_name)

        evt = CardBought(player_name=player_name, card=card_name, cost=card_def.cost)
        self._emit(evt)
        return [evt]

    def end_buy_phase(self, player_name: str) -> list[Event]:
        """
        End the buy phase, triggering cleanup and advancing to the next player.
        If the game-end condition is now met, ends the game instead.
        """
        self._assert_active(player_name)
        self._assert_phase(Phase.BUY)
        return self._end_turn()

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

    def _emit(self, event: Event) -> None:
        for h in self._event_handlers:
            h(event)

    def _draw_cards(self, player: Player, count: int) -> list[CardName]:
        """Draw up to *count* cards, reshuffling discard into draw pile as needed."""
        drawn: list[CardName] = []
        for _ in range(count):
            if not player.draw_pile:
                if not player.discard:
                    break
                player.draw_pile = player.discard[:]
                player.discard = []
                random.shuffle(player.draw_pile)
            if player.draw_pile:
                card = player.draw_pile.pop()
                player.hand.append(card)
                drawn.append(card)
        return drawn

    def _gain_card(
        self, player: Player, card_name: CardName, to_hand: bool = False
    ) -> CardGained:
        """
        Move one copy of card_name from supply to the player's discard (or hand).
        Raises InvalidAction if the pile is empty.
        """
        s = self._state
        if s.supply.get(card_name, 0) < 1:
            raise InvalidAction(f"{card_name.value} is not available in the supply.")

        s.supply[card_name] -= 1
        if to_hand:
            player.hand.append(card_name)
        else:
            player.discard.append(card_name)

        destination = "hand" if to_hand else "discard"
        evt = CardGained(player_name=player.name, card=card_name, destination=destination)
        self._emit(evt)
        return evt

    def _valid_gain_cards(self, required_type: CardType, max_cost: int) -> list[CardName]:
        """Return supply card names of required_type with cost ≤ max_cost and count > 0."""
        s = self._state
        return [
            name for name, count in s.supply.items()
            if count > 0
            and CARD_REGISTRY[name].cost <= max_cost
            and required_type in CARD_REGISTRY[name].types
        ]

    def _apply_action_effects(self, player: Player, card_def) -> list[Event]:
        """
        Apply the card's immediate effects (draw, +actions, +buys, +coins)
        then transition to any required AWAITING phase for interactive effects.
        """
        s = self._state
        events: list[Event] = []

        # Immediate stat bonuses
        s.actions += card_def.plus_actions
        s.buys    += card_def.plus_buys
        s.coins   += card_def.plus_coins

        if card_def.plus_cards:
            drawn = self._draw_cards(player, card_def.plus_cards)
            if drawn:
                evt = CardsDrawn(player_name=player.name, count=len(drawn))
                events.append(evt)
                self._emit(evt)

        # Special interactive effects
        name = card_def.name

        if name == CardName.MILITIA:
            events += self._setup_militia(player)

        elif name == CardName.CELLAR:
            # +1 Action already applied above; now wait for discard choices
            s.phase = Phase.AWAITING_CELLAR_DISCARD

        elif name == CardName.MINE:
            treasures = [
                c for c in player.hand
                if CardType.TREASURE in CARD_REGISTRY[c].types
            ]
            if treasures:
                s.phase = Phase.AWAITING_MINE_TRASH
            # else: nothing to trash, stay in ACTION

        elif name == CardName.REMODEL:
            if player.hand:
                s.phase = Phase.AWAITING_REMODEL_TRASH
            # else: nothing to trash, stay in ACTION

        elif name == CardName.WORKSHOP:
            valid = [
                n for n, count in s.supply.items()
                if count > 0 and CARD_REGISTRY[n].cost <= 4
            ]
            if valid:
                s.phase = Phase.AWAITING_WORKSHOP_GAIN

        return events

    def _setup_militia(self, attacker: Player) -> list[Event]:
        """Identify militia targets (opponents with >3 cards who lack Moat)."""
        s = self._state
        events: list[Event] = []
        targets: list[int] = []

        for i, player in enumerate(s.players):
            if i == s.current_player_index:
                continue
            if CardName.MOAT in player.hand:
                evt = MilitiaBlocked(attacker=attacker.name, defender=player.name)
                events.append(evt)
                self._emit(evt)
                continue
            if len(player.hand) > 3:
                targets.append(i)

        if targets:
            s.militia_targets = targets
            s.phase = Phase.AWAITING_MILITIA_DISCARD
            evt = MilitiaAttack(
                attacker=attacker.name,
                targets=[s.players[i].name for i in targets],
            )
            events.append(evt)
            self._emit(evt)

        return events

    def _end_turn(self) -> list[Event]:
        """Cleanup, check game-end, then advance to the next player."""
        s = self._state
        player = s.current_player
        events: list[Event] = []

        # Cleanup: discard hand + played cards
        player.discard.extend(player.hand)
        player.discard.extend(player.played)
        player.hand = []
        player.played = []

        evt = TurnEnded(player_name=player.name)
        events.append(evt)
        self._emit(evt)

        # Check game-end condition
        if self._check_game_end():
            return events + self._end_game()

        # Current player draws their next hand (cleanup draw)
        drawn = self._draw_cards(player, 5)
        if drawn:
            draw_evt = CardsDrawn(player_name=player.name, count=len(drawn))
            events.append(draw_evt)
            self._emit(draw_evt)

        # Advance to next player
        s.current_player_index = (s.current_player_index + 1) % s.num_players
        s.actions = 1
        s.buys    = 1
        s.coins   = 0
        s.phase   = Phase.ACTION

        evt = TurnStarted(player_name=s.current_player.name)
        events.append(evt)
        self._emit(evt)

        return events

    def _check_game_end(self) -> bool:
        """
        Game ends if:
          - Province pile is empty, OR
          - Any 3 supply piles are empty.
        """
        s = self._state
        if s.supply.get(CardName.PROVINCE, 0) == 0:
            return True
        empty_piles = sum(1 for count in s.supply.values() if count == 0)
        return empty_piles >= 3

    def _end_game(self) -> list[Event]:
        s = self._state
        s.phase = Phase.GAME_OVER

        scores = {}
        for player in s.players:
            scores[player.name] = sum(
                CARD_REGISTRY[c].vp for c in player.all_cards()
            )

        winner = max(scores, key=lambda n: scores[n])

        evt = GameOver(scores=scores, winner=winner)
        self._emit(evt)
        return [evt]
