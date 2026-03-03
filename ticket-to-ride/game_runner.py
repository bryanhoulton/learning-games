"""
GameRunner — orchestrates a list of PlayerAgents through the full game loop.

Responsibilities:
- Subscribe all agents to engine events
- Run initial ticket selection for every player
- Drive the turn loop: build PlayerView → ask agent → dispatch to engine
- Retry on GameError, passing the error message back to the agent
"""

from __future__ import annotations

from engine import GameEngine, MIN_KEEP_INITIAL
from errors import GameError
import traceback
from models import Phase
from player_agent import (
    ClaimRouteAction,
    DrawCardAction,
    DrawTicketsAction,
    KeepTicketsAction,
    PlayerAction,
    PlayerAgent,
)
from player_view import build_player_view


class GameRunner:

    def __init__(self, engine: GameEngine, agents: list[PlayerAgent]) -> None:
        self._engine = engine
        # Build name -> agent lookup for fast dispatch
        self._agents: dict[str, PlayerAgent] = {a.name: a for a in agents}
        self._agent_list = agents

        # Subscribe every agent to every engine event
        for agent in agents:
            engine.subscribe(agent.on_event)

    def run(self) -> None:
        self._initial_setup()
        while not self._engine.state.is_game_over:
            self._do_turn()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _initial_setup(self) -> None:
        """
        Let every player choose their starting destination tickets.
        Player 0 was already offered tickets by new_game(); players 1..n-1
        need to be offered first, then each keeps their selection.
        """
        s = self._engine.state
        for i in range(s.num_players):
            if i > 0:
                self._engine._offer_destination_tickets(s.players[i], MIN_KEEP_INITIAL)
            # Now s.phase == KEEPING_TICKETS and s.current_player_index == i
            self._do_turn()

    # ------------------------------------------------------------------
    # Turn loop
    # ------------------------------------------------------------------

    def _do_turn(self) -> None:
        """Run one agent action, retrying on GameError."""
        error: str | None = None
        while True:
            s = self._engine.state
            current_index = s.current_player_index
            current_name = s.current_player.name
            agent = self._agents[current_name]

            view = build_player_view(s, current_index)
            try:
                action = agent.choose_action(view, error)
            except Exception as e:
                traceback.print_exc()
                error = f"Failed to parse your response: {e}. Respond with only a JSON object."
                continue

            try:
                self._dispatch(current_name, action)
                return
            except GameError as e:
                error = str(e)
            except Exception as e:
                traceback.print_exc()
                error = f"Invalid action format: {e}"

    def _dispatch(self, player_name: str, action: PlayerAction) -> None:
        engine = self._engine
        if isinstance(action, DrawCardAction):
            if action.slot is None:
                engine.draw_train_card_from_deck(player_name)
            else:
                engine.draw_train_card_face_up(player_name, action.slot)
        elif isinstance(action, ClaimRouteAction):
            engine.claim_route(player_name, action.route_id, list(action.cards))
        elif isinstance(action, DrawTicketsAction):
            engine.draw_destination_tickets(player_name)
            # After drawing tickets the phase switches to KEEPING_TICKETS;
            # the runner will call _do_turn again and the agent will see the new phase.
        elif isinstance(action, KeepTicketsAction):
            engine.keep_destination_tickets(player_name, list(action.ticket_ids))
        else:
            raise ValueError(f"Unknown action type: {type(action)}")
