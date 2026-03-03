"""Run 10 games of Baseline vs Strategy head-to-head."""

from engine import GameEngine
from game_runner import GameRunner
from llm_player import LLMPlayerAgent, SYSTEM_PROMPT
from scoring import (
    calculate_destination_ticket_bonuses,
    find_all_longest_route_players,
    _build_adjacency,
    _cities_connected,
)

LONGEST_ROUTE_BONUS = 10
MODEL = "google/gemini-3-flash-preview"
NUM_GAMES = 10

STRATEGY_PROMPT = (
    "You are an expert Ticket to Ride player. Rules: players take turns either "
    "(a) drawing 2 train cards, (b) claiming a route by spending matching "
    "cards, or (c) drawing destination tickets and keeping at least 1. "
    "Destination tickets score bonus points if both cities are connected "
    "by your routes at game end, or subtract points if not. "
    "Locomotives (wild) substitute for any color.\n\n"
    "STRATEGY GUIDE — follow these principles:\n"
    "1. TICKET SELECTION: Only keep tickets whose cities are geographically "
    "close or share a natural corridor. Drop tickets that would require "
    "building in two opposite directions. Completing 2 tickets reliably is "
    "better than failing 3.\n"
    "2. PLAN FULL PATHS FIRST: Before claiming anything, trace the complete "
    "city-to-city path needed for each ticket. Identify every intermediate "
    "route segment. This is your roadmap for the whole game.\n"
    "3. CONNECTED NETWORK: Never build two disconnected clusters. Every route "
    "you claim should extend your existing network. If you have a northern "
    "group and a southern group, the bridge route between them is your #1 "
    "priority.\n"
    "4. CLAIM BOTTLENECKS FIRST: Single routes on your critical path that "
    "opponents could block should be claimed early, even before you have "
    "optimal cards. Parallel (double) routes are safer to delay.\n"
    "5. DRAW WITH PURPOSE: Only draw cards of colors you need for specific "
    "planned routes. Prefer face-up cards that match your plan over blind "
    "deck draws. Accumulate for your longest planned route first.\n"
    "6. TRAIN BUDGET: You have 45 trains. Sum the lengths of all routes in "
    "your plan. If the total exceeds your trains, shorten the plan or drop "
    "a ticket — do not run out before completing connections.\n"
    "7. ENDGAME: When you or an opponent are low on trains, stop drawing and "
    "claim remaining critical routes immediately. Uncompleted tickets are "
    "devastating (-points).\n"
    "8. OPPONENT AWARENESS: Watch which face-up cards opponents take and which "
    "routes they claim. If they are building toward a route you need, "
    "prioritize claiming it before they do."
)


def run_game(game_num: int, seed: int) -> dict:
    print(f"\n{'='*60}")
    print(f"  GAME {game_num} (seed={seed})")
    print(f"{'='*60}\n")

    names = ["Baseline", "Strategy"]
    engine = GameEngine.new_game(names, seed=seed)

    agents = [
        LLMPlayerAgent(
            "Baseline",
            model=MODEL,
            system_prompt=SYSTEM_PROMPT,
            reasoning_effort="low",
        ),
        LLMPlayerAgent(
            "Strategy",
            model=MODEL,
            system_prompt=STRATEGY_PROMPT,
            reasoning_effort="low",
        ),
    ]

    runner = GameRunner(engine, agents)
    runner.run()

    s = engine.state
    ticket_bonuses = calculate_destination_ticket_bonuses(s)
    longest_winners = find_all_longest_route_players(s)

    results = {}
    for i, p in enumerate(s.players):
        routes_score = sum(s.routes[rid].points for rid in p.claimed_routes)
        ticket_bonus = ticket_bonuses.get(i, 0)
        longest = LONGEST_ROUTE_BONUS if i in longest_winners else 0
        adj = _build_adjacency(s.claimed_routes, i)
        completed = [t for t in p.destination_tickets if _cities_connected(adj, t.city_a, t.city_b)]
        failed = [t for t in p.destination_tickets if not _cities_connected(adj, t.city_a, t.city_b)]

        results[p.name] = {
            "total": p.score,
            "routes_score": routes_score,
            "routes_claimed": len(p.claimed_routes),
            "ticket_bonus": ticket_bonus,
            "longest_bonus": longest,
            "trains_remaining": p.trains_remaining,
            "completed": len(completed),
            "failed": len(failed),
        }

        print(f"  {p.name}: {p.score} pts (routes={routes_score}, tickets={ticket_bonus:+d}, longest={longest})")

    winner = max(s.players, key=lambda p: p.score)
    results["winner"] = winner.name
    print(f"  >>> Winner: {winner.name}")
    return results


def main() -> None:
    all_results = []

    for i in range(NUM_GAMES):
        seed = 100 + i
        result = run_game(i + 1, seed)
        all_results.append(result)

    print(f"\n{'='*60}")
    print(f"  RESULTS AFTER {NUM_GAMES} GAMES")
    print(f"{'='*60}\n")

    strategy_wins = sum(1 for r in all_results if r["winner"] == "Strategy")
    baseline_wins = sum(1 for r in all_results if r["winner"] == "Baseline")

    print(f"  {'Game':<8} {'Baseline':>10} {'Strategy':>10} {'Winner':>12}")
    print(f"  {'-'*42}")
    for i, r in enumerate(all_results):
        b = r["Baseline"]["total"]
        s = r["Strategy"]["total"]
        w = r["winner"]
        print(f"  {i+1:<8} {b:>10} {s:>10} {w:>12}")

    print(f"  {'-'*42}")

    b_avg = sum(r["Baseline"]["total"] for r in all_results) / NUM_GAMES
    s_avg = sum(r["Strategy"]["total"] for r in all_results) / NUM_GAMES
    print(f"  {'Avg':<8} {b_avg:>10.1f} {s_avg:>10.1f}")
    print()
    print(f"  Strategy wins: {strategy_wins}/{NUM_GAMES} ({strategy_wins/NUM_GAMES*100:.0f}%)")
    print(f"  Baseline wins: {baseline_wins}/{NUM_GAMES} ({baseline_wins/NUM_GAMES*100:.0f}%)")
    print(f"  Avg margin: Strategy {s_avg - b_avg:+.1f} pts")

    b_tickets = sum(r["Baseline"]["completed"] for r in all_results)
    s_tickets = sum(r["Strategy"]["completed"] for r in all_results)
    b_failed = sum(r["Baseline"]["failed"] for r in all_results)
    s_failed = sum(r["Strategy"]["failed"] for r in all_results)
    print(f"\n  Tickets completed: Baseline {b_tickets}, Strategy {s_tickets}")
    print(f"  Tickets failed:    Baseline {b_failed}, Strategy {s_failed}")


if __name__ == "__main__":
    main()
