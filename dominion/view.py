"""
Player-scoped view of game state for Dominion.

get_player_view() produces a PlayerView containing only the information
a real player at the table would have. Use this to feed bots and LLMs —
never hand them the raw GameState.

What is and isn't visible in Dominion:
  - Your own hand              → fully visible
  - Other players' hands       → size only (you can count their cards)
  - Any discard pile           → fully visible (face-up pile on the table)
  - Any draw pile              → size only (face-down stack)
  - Supply piles               → fully visible
  - Trash                      → fully visible
  - Turn resources (actions, buys, coins) → fully visible
  - Pending decision metadata  → fully visible (observable by everyone)
"""

from __future__ import annotations

from dataclasses import dataclass

from models import CardName, GameState, Phase


@dataclass(frozen=True)
class OtherPlayerView:
    name: str
    hand_size: int          # you can count their cards; you cannot see them
    draw_pile_size: int     # you can count the stack; you cannot see the contents
    discard: tuple          # tuple[CardName, ...] — face-up, fully public


@dataclass(frozen=True)
class PlayerView:
    # ---- your own info ----
    your_name: str
    your_hand: tuple            # tuple[CardName, ...] — only you see this
    your_draw_pile_size: int    # you know how many you have left, not the order
    your_discard: tuple         # tuple[CardName, ...] — public, but included here for convenience

    # ---- public board ----
    supply: dict                # dict[CardName, int]
    trash: tuple                # tuple[CardName, ...]
    others: tuple               # tuple[OtherPlayerView, ...]

    # ---- turn state ----
    current_player_name: str
    phase: Phase
    actions: int
    buys: int
    coins: int

    # ---- pending decision metadata (all observable) ----
    pending_gain_max_cost: int      # non-zero during AWAITING_*_GAIN / AWAITING_WORKSHOP_GAIN
    pending_gain_to_hand: bool      # True for Mine (gains to hand), False otherwise
    militia_targets: tuple          # tuple[str, ...] — names of players who still must discard


def get_player_view(state: GameState, player_name: str) -> PlayerView:
    """
    Return the subset of GameState that *player_name* is allowed to see.
    Raises ValueError if the player name is not in the game.
    """
    me = next((p for p in state.players if p.name == player_name), None)
    if me is None:
        raise ValueError(f"No player named {player_name!r} in this game.")

    others = tuple(
        OtherPlayerView(
            name=p.name,
            hand_size=len(p.hand),
            draw_pile_size=len(p.draw_pile),
            discard=tuple(p.discard),
        )
        for p in state.players
        if p.name != player_name
    )

    return PlayerView(
        your_name=player_name,
        your_hand=tuple(me.hand),
        your_draw_pile_size=len(me.draw_pile),
        your_discard=tuple(me.discard),
        supply=dict(state.supply),
        trash=tuple(state.trash),
        others=others,
        current_player_name=state.current_player.name,
        phase=state.phase,
        actions=state.actions,
        buys=state.buys,
        coins=state.coins,
        pending_gain_max_cost=state.pending_gain_max_cost,
        pending_gain_to_hand=state.pending_gain_to_hand,
        militia_targets=tuple(
            state.players[i].name for i in state.militia_targets
        ),
    )
