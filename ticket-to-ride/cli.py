"""
Ticket to Ride — Terminal CLI

Run with: python cli.py
"""

from __future__ import annotations

import sys

from engine import GameEngine
from game_runner import GameRunner
from terminal_player import TerminalPlayerAgent, bold, sep


def _ask(prompt: str) -> str:
    try:
        return input(f"\n{prompt} ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")
        sys.exit(0)


def setup_players() -> list[str]:
    sep("═")
    print(bold("  🚂  TICKET TO RIDE  🚂"))
    sep("═")
    print()
    raw = _ask("How many players? [2-5]:")
    try:
        n = int(raw)
        if not 2 <= n <= 5:
            raise ValueError
    except ValueError:
        print("Defaulting to 2 players.")
        n = 2

    names = []
    for i in range(n):
        name = _ask(f"  Name for player {i+1}:").strip() or f"Player {i+1}"
        names.append(name)
    return names


def main() -> None:
    names = setup_players()
    engine = GameEngine.new_game(names)
    agents = [TerminalPlayerAgent(name) for name in names]
    runner = GameRunner(engine, agents)
    runner.run()


if __name__ == "__main__":
    main()
