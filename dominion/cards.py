"""
Dominion card definitions.

CARD_REGISTRY maps every CardName to its CardDef.
FIRST_GAME_KINGDOM is the recommended starter set of 10 kingdom cards.
supply_counts() returns the starting pile sizes for a given player count.
"""

from __future__ import annotations

from models import CardDef, CardName, CardType

T = CardType.TREASURE
V = CardType.VICTORY
C = CardType.CURSE
A = CardType.ACTION
R = CardType.REACTION

CARD_REGISTRY: dict[CardName, CardDef] = {
    # ------------------------------------------------------------------
    # Treasure cards
    # ------------------------------------------------------------------
    CardName.COPPER: CardDef(
        name=CardName.COPPER, cost=0,
        types=frozenset([T]),
        coins=1,
    ),
    CardName.SILVER: CardDef(
        name=CardName.SILVER, cost=3,
        types=frozenset([T]),
        coins=2,
    ),
    CardName.GOLD: CardDef(
        name=CardName.GOLD, cost=6,
        types=frozenset([T]),
        coins=3,
    ),

    # ------------------------------------------------------------------
    # Victory cards
    # ------------------------------------------------------------------
    CardName.ESTATE: CardDef(
        name=CardName.ESTATE, cost=2,
        types=frozenset([V]),
        vp=1,
    ),
    CardName.DUCHY: CardDef(
        name=CardName.DUCHY, cost=5,
        types=frozenset([V]),
        vp=3,
    ),
    CardName.PROVINCE: CardDef(
        name=CardName.PROVINCE, cost=8,
        types=frozenset([V]),
        vp=6,
    ),

    # ------------------------------------------------------------------
    # Curse
    # ------------------------------------------------------------------
    CardName.CURSE: CardDef(
        name=CardName.CURSE, cost=0,
        types=frozenset([C]),
        vp=-1,
    ),

    # ------------------------------------------------------------------
    # Kingdom cards — First Game set
    # ------------------------------------------------------------------

    # Cellar (cost 2): +1 Action; Discard any # of cards; +1 Card per discarded
    CardName.CELLAR: CardDef(
        name=CardName.CELLAR, cost=2,
        types=frozenset([A]),
        plus_actions=1,
        # The discard/draw part is handled interactively in the engine
    ),

    # Market (cost 5): +1 Card, +1 Action, +1 Buy, +1 Coin
    CardName.MARKET: CardDef(
        name=CardName.MARKET, cost=5,
        types=frozenset([A]),
        plus_cards=1, plus_actions=1, plus_buys=1, plus_coins=1,
    ),

    # Militia (cost 4): +2 Coins; each other player discards down to 3
    CardName.MILITIA: CardDef(
        name=CardName.MILITIA, cost=4,
        types=frozenset([A]),
        plus_coins=2,
        is_attack=True,
    ),

    # Mine (cost 5): Trash a Treasure; gain a Treasure to hand costing up to 3 more
    CardName.MINE: CardDef(
        name=CardName.MINE, cost=5,
        types=frozenset([A]),
    ),

    # Moat (cost 2): +2 Cards; Reaction — block attacks
    CardName.MOAT: CardDef(
        name=CardName.MOAT, cost=2,
        types=frozenset([A, R]),
        plus_cards=2,
        is_reaction=True,
    ),

    # Remodel (cost 4): Trash a card; gain a card costing up to 2 more
    CardName.REMODEL: CardDef(
        name=CardName.REMODEL, cost=4,
        types=frozenset([A]),
    ),

    # Smithy (cost 4): +3 Cards
    CardName.SMITHY: CardDef(
        name=CardName.SMITHY, cost=4,
        types=frozenset([A]),
        plus_cards=3,
    ),

    # Village (cost 3): +1 Card, +2 Actions
    CardName.VILLAGE: CardDef(
        name=CardName.VILLAGE, cost=3,
        types=frozenset([A]),
        plus_cards=1, plus_actions=2,
    ),

    # Woodcutter (cost 3): +1 Buy, +2 Coins
    CardName.WOODCUTTER: CardDef(
        name=CardName.WOODCUTTER, cost=3,
        types=frozenset([A]),
        plus_buys=1, plus_coins=2,
    ),

    # Workshop (cost 3): Gain a card costing up to 4
    CardName.WORKSHOP: CardDef(
        name=CardName.WORKSHOP, cost=3,
        types=frozenset([A]),
    ),
}

# The recommended first-game kingdom
FIRST_GAME_KINGDOM: list[CardName] = [
    CardName.CELLAR,
    CardName.MARKET,
    CardName.MILITIA,
    CardName.MINE,
    CardName.MOAT,
    CardName.REMODEL,
    CardName.SMITHY,
    CardName.VILLAGE,
    CardName.WOODCUTTER,
    CardName.WORKSHOP,
]


def supply_counts(num_players: int, kingdom: list[CardName]) -> dict[CardName, int]:
    """Return starting supply pile sizes for the given player count and kingdom."""
    if not 2 <= num_players <= 4:
        raise ValueError("Dominion supports 2-4 players.")

    counts: dict[CardName, int] = {
        CardName.COPPER:   60 - (7 * num_players),   # players start with 7 each
        CardName.SILVER:   40,
        CardName.GOLD:     30,
        CardName.ESTATE:   24 - (3 * num_players),   # players start with 3 each
        CardName.DUCHY:    8 if num_players <= 2 else 12,
        CardName.PROVINCE: 8 if num_players <= 2 else 12,
        CardName.CURSE:    10 * (num_players - 1),
    }

    for card_name in kingdom:
        counts[card_name] = 10

    return counts
