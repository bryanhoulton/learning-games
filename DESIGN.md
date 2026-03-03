# Game Engine Design Principles

Principles used across every game in this repo. Language-agnostic; applied in Python here.

---

## 1. Separate data from logic

Keep two distinct layers:

- **Models** — pure data structures. No methods that mutate state. No imports from the engine.
- **Engine** — owns the game state and is the only place rules are enforced. All mutations go through it.

If a model method does more than read its own fields, it belongs in the engine.

---

## 2. One source of truth

There is exactly one `GameState` object. The engine reads and writes it exclusively. External code (UI, AI, tests) only ever reads it — never writes directly.

---

## 3. Actions return events, not booleans

Every public engine method returns a list of events describing what happened. Callers learn *what changed* without polling state before and after. This also makes the engine trivially observable.

---

## 4. Observers, not callbacks

External code subscribes to events via `engine.subscribe(handler)`. The engine emits events but never calls back into UI or AI code. Dependency flows one way: UI depends on engine, not the reverse.

---

## 5. Raise on illegal moves, don't return error codes

Illegal actions raise typed exceptions (`NotYourTurn`, `WrongPhase`, `InsufficientCards`, etc.) that subclass a common `GameError`. Callers can catch narrowly or broadly. No sentinel return values.

---

## 6. Model multi-step interactions as explicit phases

When a card or action requires a follow-up decision (discard these cards, choose what to gain, etc.), the engine transitions to a named waiting phase. The player must call a dedicated `resolve_*` method to continue. This keeps turn flow as simple state, not a hidden call stack.

---

## 7. Build the engine before the UI

The engine must be fully tested and playable before any rendering code is written. The CLI or GUI is a read-only consumer of state and events — it should be possible to swap it out without touching the engine.

---

## 8. Tests are the first UI

Write tests that exercise the engine directly, using helper functions to set up specific scenarios (force a player's hand, drain a supply pile, etc.). If a mechanic is hard to test, the API is wrong.

---

## 9. Static game content lives outside the engine

Card definitions, board layouts, and scoring tables are pure data. Put them in a dedicated file (`cards.py`, `board.py`). The engine imports them; they do not import the engine.

---

## 10. Factory methods for setup complexity

Game initialization is complex and stateful (shuffling, dealing, choosing starting conditions). Encapsulate it in a `@classmethod` factory (`Engine.new_game(...)`) rather than a multi-step setup sequence the caller has to orchestrate.

---

## 11. Enforce information hiding through a view layer

Bots and LLMs must never receive the raw `GameState` — it contains hidden information (other players' hands, face-down deck contents, private tickets). Instead, each game exposes a `get_player_view(state, player_name) -> PlayerView` function that returns a filtered projection containing only what that player could legitimately observe at the table.

Rules for building a view:
- **Hidden from everyone**: face-down deck contents and order (only the size is known)
- **Hidden from opponents**: your hand cards, your destination tickets / private objectives
- **Visible to all**: board state, scores, claim ownership, public discard piles, deck sizes
- **Conditionally visible**: pending-decision data (e.g. offered tickets) only appears in the view of the player who must act on it

The `PlayerView` is an immutable, frozen snapshot. It contains no references back to the live `GameState`, so a bot cannot accidentally mutate or inspect beyond its scope.

This principle extends naturally to partial observability: if you later add fog-of-war or secret information mechanics, `get_player_view` is the only place those rules live.
