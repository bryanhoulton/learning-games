"""
Splendor card and noble definitions.

CARD_REGISTRY maps card_id -> CardDef.
NOBLE_REGISTRY maps noble_id -> NobleDef.

Card IDs:   1-40  = tier 1,  41-70 = tier 2,  71-90 = tier 3
Noble IDs:  101-110
"""

from __future__ import annotations

from models import CardDef, GemColor, NobleDef

D = GemColor.DIAMOND
S = GemColor.SAPPHIRE
E = GemColor.EMERALD
R = GemColor.RUBY
O = GemColor.ONYX


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _c(id: int, tier: int, bonus: GemColor, vp: int, **cost_kwargs) -> CardDef:
    """Shorthand card constructor. Pass cost as keyword args, e.g. onyx=2, ruby=1."""
    color_map = {
        "diamond": D, "sapphire": S, "emerald": E, "ruby": R, "onyx": O,
    }
    cost = {color_map[k]: v for k, v in cost_kwargs.items() if v > 0}
    return CardDef(id=id, tier=tier, bonus_color=bonus, vp=vp, cost=cost)


def _n(id: int, vp: int, **req_kwargs) -> NobleDef:
    """Shorthand noble constructor. Pass requirements as keyword args."""
    color_map = {
        "diamond": D, "sapphire": S, "emerald": E, "ruby": R, "onyx": O,
    }
    reqs = {color_map[k]: v for k, v in req_kwargs.items() if v > 0}
    return NobleDef(id=id, vp=vp, requirements=reqs)


# ---------------------------------------------------------------------------
# Tier 1 cards (IDs 1–40, eight per bonus color)
# ---------------------------------------------------------------------------

_TIER1: list[CardDef] = [
    # --- Onyx bonus ---
    _c( 1, 1, O, 0, sapphire=1, emerald=1, ruby=1, diamond=1),
    _c( 2, 1, O, 0, sapphire=2, emerald=1),
    _c( 3, 1, O, 0, sapphire=1, emerald=1, ruby=1),
    _c( 4, 1, O, 0, sapphire=1, emerald=2),
    _c( 5, 1, O, 0, sapphire=2, ruby=1),
    _c( 6, 1, O, 0, sapphire=3),
    _c( 7, 1, O, 0, sapphire=1, diamond=1, ruby=2),
    _c( 8, 1, O, 1, sapphire=4),

    # --- Diamond bonus ---
    _c( 9, 1, D, 0, onyx=1, ruby=1, sapphire=1, emerald=1),
    _c(10, 1, D, 0, onyx=2, ruby=1),
    _c(11, 1, D, 0, onyx=1, ruby=1, emerald=1),
    _c(12, 1, D, 0, onyx=2, sapphire=1),
    _c(13, 1, D, 0, onyx=1, emerald=2),
    _c(14, 1, D, 0, onyx=3),
    _c(15, 1, D, 0, onyx=1, ruby=2, emerald=1),
    _c(16, 1, D, 1, onyx=4),

    # --- Emerald bonus ---
    _c(17, 1, E, 0, diamond=1, ruby=1, sapphire=1, onyx=1),
    _c(18, 1, E, 0, diamond=2, sapphire=1),
    _c(19, 1, E, 0, diamond=1, sapphire=2),
    _c(20, 1, E, 0, diamond=2, onyx=1),
    _c(21, 1, E, 0, diamond=1, sapphire=1, ruby=1),
    _c(22, 1, E, 0, diamond=3),
    _c(23, 1, E, 0, ruby=1, onyx=1, diamond=2),
    _c(24, 1, E, 1, diamond=4),

    # --- Ruby bonus ---
    _c(25, 1, R, 0, emerald=1, diamond=1, sapphire=1, onyx=1),
    _c(26, 1, R, 0, emerald=2, onyx=1),
    _c(27, 1, R, 0, emerald=1, onyx=2),
    _c(28, 1, R, 0, emerald=2, diamond=1),
    _c(29, 1, R, 0, emerald=1, onyx=1, sapphire=1),
    _c(30, 1, R, 0, emerald=3),
    _c(31, 1, R, 0, emerald=2, diamond=1, onyx=1),
    _c(32, 1, R, 1, emerald=4),

    # --- Sapphire bonus ---
    _c(33, 1, S, 0, ruby=1, emerald=1, diamond=1, onyx=1),
    _c(34, 1, S, 0, ruby=2, diamond=1),
    _c(35, 1, S, 0, ruby=1, diamond=2),
    _c(36, 1, S, 0, ruby=2, emerald=1),
    _c(37, 1, S, 0, ruby=1, emerald=1, diamond=1),
    _c(38, 1, S, 0, ruby=3),
    _c(39, 1, S, 0, ruby=2, onyx=1, diamond=1),
    _c(40, 1, S, 1, ruby=4),
]

# ---------------------------------------------------------------------------
# Tier 2 cards (IDs 41–70, six per bonus color)
# ---------------------------------------------------------------------------

_TIER2: list[CardDef] = [
    # --- Onyx bonus ---
    _c(41, 2, O, 1, sapphire=2, emerald=3),
    _c(42, 2, O, 1, sapphire=3, diamond=2, ruby=2),
    _c(43, 2, O, 2, sapphire=1, emerald=4, diamond=2),
    _c(44, 2, O, 2, sapphire=3, emerald=3, diamond=2),
    _c(45, 2, O, 2, sapphire=5),
    _c(46, 2, O, 3, sapphire=6),

    # --- Diamond bonus ---
    _c(47, 2, D, 1, onyx=2, ruby=3),
    _c(48, 2, D, 1, onyx=3, sapphire=2, emerald=2),
    _c(49, 2, D, 2, ruby=1, onyx=4, sapphire=2),
    _c(50, 2, D, 2, onyx=3, ruby=3, emerald=2),
    _c(51, 2, D, 2, onyx=5),
    _c(52, 2, D, 3, onyx=6),

    # --- Emerald bonus ---
    _c(53, 2, E, 1, diamond=2, sapphire=3),
    _c(54, 2, E, 1, diamond=3, ruby=2, onyx=2),
    _c(55, 2, E, 2, sapphire=1, diamond=4, ruby=2),
    _c(56, 2, E, 2, diamond=3, sapphire=3, onyx=2),
    _c(57, 2, E, 2, diamond=5),
    _c(58, 2, E, 3, diamond=6),

    # --- Ruby bonus ---
    _c(59, 2, R, 1, emerald=2, onyx=3),
    _c(60, 2, R, 1, emerald=3, sapphire=2, diamond=2),
    _c(61, 2, R, 2, onyx=1, emerald=4, sapphire=2),
    _c(62, 2, R, 2, emerald=3, onyx=3, diamond=2),
    _c(63, 2, R, 2, emerald=5),
    _c(64, 2, R, 3, emerald=6),

    # --- Sapphire bonus ---
    _c(65, 2, S, 1, ruby=2, diamond=3),
    _c(66, 2, S, 1, ruby=3, emerald=2, onyx=2),
    _c(67, 2, S, 2, diamond=1, ruby=4, emerald=2),
    _c(68, 2, S, 2, ruby=3, diamond=3, onyx=2),
    _c(69, 2, S, 2, ruby=5),
    _c(70, 2, S, 3, ruby=6),
]

# ---------------------------------------------------------------------------
# Tier 3 cards (IDs 71–90, four per bonus color)
# ---------------------------------------------------------------------------

_TIER3: list[CardDef] = [
    # --- Onyx bonus ---
    _c(71, 3, O, 3, sapphire=3, diamond=3, ruby=3, emerald=5),
    _c(72, 3, O, 4, emerald=3, sapphire=6, diamond=3),
    _c(73, 3, O, 4, sapphire=7),
    _c(74, 3, O, 5, sapphire=3, emerald=3, diamond=3, ruby=3),

    # --- Diamond bonus ---
    _c(75, 3, D, 3, onyx=3, sapphire=3, ruby=3, emerald=5),
    _c(76, 3, D, 4, ruby=3, onyx=6, sapphire=3),
    _c(77, 3, D, 4, onyx=7),
    _c(78, 3, D, 5, onyx=3, ruby=3, sapphire=3, emerald=3),

    # --- Emerald bonus ---
    _c(79, 3, E, 3, diamond=3, ruby=3, sapphire=3, onyx=5),
    _c(80, 3, E, 4, sapphire=3, diamond=6, ruby=3),
    _c(81, 3, E, 4, diamond=7),
    _c(82, 3, E, 5, diamond=3, sapphire=3, ruby=3, onyx=3),

    # --- Ruby bonus ---
    _c(83, 3, R, 3, emerald=3, sapphire=3, diamond=3, onyx=5),
    _c(84, 3, R, 4, onyx=3, emerald=6, sapphire=3),
    _c(85, 3, R, 4, emerald=7),
    _c(86, 3, R, 5, emerald=3, onyx=3, sapphire=3, diamond=3),

    # --- Sapphire bonus ---
    _c(87, 3, S, 3, ruby=3, diamond=3, onyx=3, emerald=5),
    _c(88, 3, S, 4, diamond=3, ruby=6, onyx=3),
    _c(89, 3, S, 4, ruby=7),
    _c(90, 3, S, 5, ruby=3, diamond=3, onyx=3, emerald=3),
]

# ---------------------------------------------------------------------------
# Noble tiles (IDs 101–110)
# ---------------------------------------------------------------------------

_NOBLES: list[NobleDef] = [
    _n(101, 3, ruby=4,    sapphire=4),
    _n(102, 3, diamond=4, sapphire=4),
    _n(103, 3, onyx=4,    ruby=4),
    _n(104, 3, diamond=3, sapphire=3, emerald=3),
    _n(105, 3, diamond=3, sapphire=3, onyx=3),
    _n(106, 3, emerald=4, sapphire=4),
    _n(107, 3, diamond=4, onyx=4),
    _n(108, 3, diamond=3, ruby=3,    emerald=3),
    _n(109, 3, onyx=3,    ruby=3,    diamond=3),
    _n(110, 3, emerald=3, sapphire=3, onyx=3),
]

# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

CARD_REGISTRY: dict[int, CardDef] = {
    card.id: card for card in _TIER1 + _TIER2 + _TIER3
}

NOBLE_REGISTRY: dict[int, NobleDef] = {
    noble.id: noble for noble in _NOBLES
}

TIER_CARD_IDS: dict[int, list[int]] = {
    1: [c.id for c in _TIER1],
    2: [c.id for c in _TIER2],
    3: [c.id for c in _TIER3],
}

ALL_NOBLE_IDS: list[int] = [n.id for n in _NOBLES]
