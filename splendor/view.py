"""
Player-scoped view of game state for Splendor.

get_player_view() produces a PlayerView containing only the information
a real player at the table would have. Use this to feed bots and LLMs —
never hand them the raw GameState.

What is and isn't visible in Splendor:
  - All gem tokens (supply + every player's hand)  → fully visible
  - All purchased cards (all players)              → fully visible
  - All reserved cards (all players)               → fully visible
    (In the physical game reserved cards sit face-up in front of you.)
  - All nobles on the board                        → fully visible
  - Face-down deck contents                        → size only (hidden order)
  - Pending noble choices                          → only shown to active player
"""

from __future__ import annotations

from dataclasses import dataclass

from models import GemColor, GameState, Phase


@dataclass(frozen=True)
class OtherPlayerView:
    name:           str
    gems:           dict    # dict[GemColor, int] — all visible
    reserved:       tuple   # tuple[int, ...] — card IDs (face-up in front of player)
    purchased:      tuple   # tuple[int, ...] — card IDs
    nobles:         tuple   # tuple[int, ...] — noble IDs
    vp:             int     # visible score (cards + nobles)


@dataclass(frozen=True)
class PlayerView:
    # ---- your own info ----
    your_name:      str
    your_gems:      dict    # dict[GemColor, int]
    your_reserved:  tuple   # tuple[int, ...] — card IDs
    your_purchased: tuple   # tuple[int, ...] — card IDs
    your_nobles:    tuple   # tuple[int, ...] — noble IDs
    your_vp:        int

    # ---- public board ----
    board:          dict    # dict[int, list[int|None]]  tier -> 4 slots
    deck_sizes:     dict    # dict[int, int]  tier -> cards remaining (hidden order)
    nobles:         tuple   # tuple[int, ...] — noble IDs available on the board
    gem_supply:     dict    # dict[GemColor, int]
    others:         tuple   # tuple[OtherPlayerView, ...]

    # ---- turn state ----
    current_player_name: str
    phase:               Phase

    # ---- pending decision (only relevant when it's your turn) ----
    pending_noble_choices: tuple    # tuple[int, ...] — noble IDs to choose from


def get_player_view(state: GameState, player_name: str) -> PlayerView:
    """
    Return the subset of GameState that *player_name* is allowed to see.
    Raises ValueError if the player name is not in the game.
    """
    from cards import CARD_REGISTRY, NOBLE_REGISTRY

    me = next((p for p in state.players if p.name == player_name), None)
    if me is None:
        raise ValueError(f"No player named {player_name!r} in this game.")

    def _vp(player) -> int:
        return (
            sum(CARD_REGISTRY[cid].vp for cid in player.purchased)
            + sum(NOBLE_REGISTRY[nid].vp for nid in player.nobles)
        )

    others = tuple(
        OtherPlayerView(
            name=p.name,
            gems=dict(p.gems),
            reserved=tuple(p.reserved),
            purchased=tuple(p.purchased),
            nobles=tuple(p.nobles),
            vp=_vp(p),
        )
        for p in state.players
        if p.name != player_name
    )

    return PlayerView(
        your_name=player_name,
        your_gems=dict(me.gems),
        your_reserved=tuple(me.reserved),
        your_purchased=tuple(me.purchased),
        your_nobles=tuple(me.nobles),
        your_vp=_vp(me),
        board={tier: list(slots) for tier, slots in state.board.items()},
        deck_sizes={tier: len(ids) for tier, ids in state.decks.items()},
        nobles=tuple(state.nobles),
        gem_supply=dict(state.gem_supply),
        others=others,
        current_player_name=state.current_player.name,
        phase=state.phase,
        pending_noble_choices=tuple(state.pending_noble_choices),
    )
