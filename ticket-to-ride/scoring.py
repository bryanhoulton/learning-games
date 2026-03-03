"""
End-game scoring logic.

All functions are pure — they read GameState but never mutate it.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Optional

from models import GameState, RouteId


# ---------------------------------------------------------------------------
# Destination ticket completion
# ---------------------------------------------------------------------------

def _build_adjacency(claimed_routes: dict[RouteId, int], player_index: int) -> dict[str, set[str]]:
    """Return adjacency list for cities connected by routes owned by *player_index*."""
    adj: dict[str, set[str]] = defaultdict(set)
    for route_id, owner in claimed_routes.items():
        if owner == player_index:
            adj[route_id.city_a].add(route_id.city_b)
            adj[route_id.city_b].add(route_id.city_a)
    return adj


def _cities_connected(adj: dict[str, set[str]], city_a: str, city_b: str) -> bool:
    """BFS to check if city_a and city_b are connected in *adj*."""
    if city_a == city_b:
        return True
    visited = {city_a}
    queue = deque([city_a])
    while queue:
        current = queue.popleft()
        for neighbour in adj.get(current, []):
            if neighbour == city_b:
                return True
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append(neighbour)
    return False


def calculate_destination_ticket_bonuses(state: GameState) -> dict[int, int]:
    """
    Return a dict mapping player_index -> net ticket bonus/penalty.

    Completed tickets add their point value; incomplete tickets subtract it.
    """
    result: dict[int, int] = defaultdict(int)

    for i, player in enumerate(state.players):
        adj = _build_adjacency(state.claimed_routes, i)
        for ticket in player.destination_tickets:
            if _cities_connected(adj, ticket.city_a, ticket.city_b):
                result[i] += ticket.points
            else:
                result[i] -= ticket.points

    return result


# ---------------------------------------------------------------------------
# Longest continuous route
# ---------------------------------------------------------------------------

def _longest_path_from(
    adj: dict[str, set[str]],
    start: str,
    visited_edges: frozenset[tuple[str, str]],
) -> int:
    """
    DFS to find the longest path (in edges) reachable from *start*
    without reusing any edge in *visited_edges*.
    """
    best = 0
    for neighbour in adj.get(start, []):
        edge = (min(start, neighbour), max(start, neighbour))
        if edge not in visited_edges:
            length = 1 + _longest_path_from(
                adj, neighbour, visited_edges | {edge}
            )
            if length > best:
                best = length
    return best


def _longest_path(adj: dict[str, set[str]]) -> int:
    """Return the length (number of route segments) of the longest continuous route."""
    cities = set(adj.keys())
    best = 0
    for city in cities:
        length = _longest_path_from(adj, city, frozenset())
        if length > best:
            best = length
    return best


def find_longest_route_player(state: GameState) -> Optional[int]:
    """
    Return the index of the player with the longest continuous route (≥1).
    Returns None if no routes have been claimed.
    In case of a tie, *all* tied players receive the bonus — but this function
    returns the first one found (the caller may want to loop for ties).

    Note: the standard rules say only ONE player gets the bonus if tied.
    Here we return the player_index of the sole winner, or None on a true tie
    so the caller can award to nobody (house rule). In practice Ticket to Ride
    awards the bonus to all tied players — change the caller to handle that.
    """
    lengths: list[tuple[int, int]] = []  # (player_index, length)

    for i, player in enumerate(state.players):
        adj = _build_adjacency(state.claimed_routes, i)
        if adj:
            length = _longest_path(adj)
            lengths.append((i, length))

    if not lengths:
        return None

    max_length = max(l for _, l in lengths)
    if max_length == 0:
        return None

    winners = [i for i, l in lengths if l == max_length]
    # Standard rules: all tied players receive the bonus.
    # Return the first; the engine awards all tied players.
    return winners[0] if len(winners) == 1 else None


def find_all_longest_route_players(state: GameState) -> list[int]:
    """Return ALL player indices tied for the longest route."""
    lengths: list[tuple[int, int]] = []

    for i in range(len(state.players)):
        adj = _build_adjacency(state.claimed_routes, i)
        if adj:
            length = _longest_path(adj)
            lengths.append((i, length))

    if not lengths:
        return []

    max_length = max(l for _, l in lengths)
    if max_length == 0:
        return []

    return [i for i, l in lengths if l == max_length]
