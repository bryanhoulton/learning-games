"""
USA Ticket to Ride board data.

All cities, routes, and destination tickets hard-coded from the original game.
Returns immutable collections used to initialise GameState.
"""

from __future__ import annotations

from models import Color, DestinationTicket, Route, RouteId


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _route(city_a: str, city_b: str, length: int, color: Color, index: int = 0) -> Route:
    rid = RouteId(city_a, city_b, index)
    # Normalise city order to match RouteId canonicalisation
    return Route(
        id=rid,
        city_a=rid.city_a,
        city_b=rid.city_b,
        length=length,
        color=color,
        index=index,
    )


def build_routes() -> dict[RouteId, Route]:
    """Return all routes on the USA board keyed by RouteId."""
    routes_list: list[Route] = [
        # Vancouver - Seattle (double)
        _route("Vancouver", "Seattle", 1, Color.WILD, 0),
        _route("Vancouver", "Seattle", 1, Color.WILD, 1),
        # Vancouver - Calgary
        _route("Vancouver", "Calgary", 3, Color.WILD),
        # Seattle - Calgary
        _route("Seattle", "Calgary", 4, Color.WILD),
        # Seattle - Portland (double)
        _route("Seattle", "Portland", 1, Color.WILD, 0),
        _route("Seattle", "Portland", 1, Color.WILD, 1),
        # Portland - San Francisco (double)
        _route("Portland", "San Francisco", 5, Color.GREEN, 0),
        _route("Portland", "San Francisco", 5, Color.PINK, 1),
        # Portland - Salt Lake City
        _route("Portland", "Salt Lake City", 6, Color.BLUE),
        # Calgary - Winnipeg
        _route("Calgary", "Winnipeg", 6, Color.WHITE),
        # Calgary - Helena
        _route("Calgary", "Helena", 4, Color.WILD),
        # Helena - Winnipeg
        _route("Helena", "Winnipeg", 4, Color.BLUE),
        # Helena - Seattle  (no direct; skip)
        # Helena - Duluth
        _route("Helena", "Duluth", 6, Color.ORANGE),
        # Helena - Omaha
        _route("Helena", "Omaha", 5, Color.RED),
        # Helena - Denver
        _route("Helena", "Denver", 4, Color.GREEN),
        # Helena - Salt Lake City
        _route("Helena", "Salt Lake City", 3, Color.PINK),
        # Salt Lake City - Denver (double)
        _route("Salt Lake City", "Denver", 3, Color.RED, 0),
        _route("Salt Lake City", "Denver", 3, Color.YELLOW, 1),
        # Salt Lake City - Las Vegas
        _route("Salt Lake City", "Las Vegas", 3, Color.ORANGE),
        # San Francisco - Salt Lake City (double)
        _route("San Francisco", "Salt Lake City", 5, Color.ORANGE, 0),
        _route("San Francisco", "Salt Lake City", 5, Color.WHITE, 1),
        # San Francisco - Los Angeles (double)
        _route("San Francisco", "Los Angeles", 3, Color.PINK, 0),
        _route("San Francisco", "Los Angeles", 3, Color.YELLOW, 1),
        # Los Angeles - Las Vegas
        _route("Los Angeles", "Las Vegas", 2, Color.WILD),
        # Los Angeles - Phoenix
        _route("Los Angeles", "Phoenix", 3, Color.WILD),
        # Los Angeles - El Paso
        _route("Los Angeles", "El Paso", 6, Color.BLACK),
        # Las Vegas - Phoenix  (no direct in standard game)
        # Phoenix - Denver
        _route("Phoenix", "Denver", 5, Color.WHITE),
        # Phoenix - El Paso
        _route("Phoenix", "El Paso", 3, Color.WILD),
        # Phoenix - Santa Fe
        _route("Phoenix", "Santa Fe", 3, Color.WILD),  # note: not in all editions; included in original
        # Denver - Omaha
        _route("Denver", "Omaha", 4, Color.PINK),
        # Denver - Kansas City (double)
        _route("Denver", "Kansas City", 4, Color.BLACK, 0),
        _route("Denver", "Kansas City", 4, Color.ORANGE, 1),
        # Denver - Oklahoma City
        _route("Denver", "Oklahoma City", 4, Color.RED),
        # Denver - Santa Fe
        _route("Denver", "Santa Fe", 2, Color.WILD),
        # Santa Fe - Oklahoma City
        _route("Santa Fe", "Oklahoma City", 3, Color.BLUE),
        # Santa Fe - El Paso
        _route("Santa Fe", "El Paso", 2, Color.WILD),
        # El Paso - Oklahoma City
        _route("El Paso", "Oklahoma City", 5, Color.YELLOW),
        # El Paso - Dallas
        _route("El Paso", "Dallas", 4, Color.RED),
        # El Paso - Houston
        _route("El Paso", "Houston", 6, Color.GREEN),
        # El Paso - Juarez (not standard — skip)
        # Winnipeg - Duluth
        _route("Winnipeg", "Duluth", 4, Color.BLACK),
        # Winnipeg - Sault St. Marie
        _route("Winnipeg", "Sault St. Marie", 6, Color.WILD),
        # Duluth - Omaha (double)
        _route("Duluth", "Omaha", 2, Color.WILD, 0),
        _route("Duluth", "Omaha", 2, Color.WILD, 1),
        # Duluth - Chicago
        _route("Duluth", "Chicago", 3, Color.RED),
        # Duluth - Toronto
        _route("Duluth", "Toronto", 6, Color.PINK),
        # Duluth - Sault St. Marie
        _route("Duluth", "Sault St. Marie", 3, Color.WILD),
        # Omaha - Kansas City (double)
        _route("Omaha", "Kansas City", 1, Color.WILD, 0),
        _route("Omaha", "Kansas City", 1, Color.WILD, 1),
        # Omaha - Chicago
        _route("Omaha", "Chicago", 4, Color.BLUE),
        # Kansas City - Saint Louis (double)
        _route("Kansas City", "Saint Louis", 2, Color.BLUE, 0),
        _route("Kansas City", "Saint Louis", 2, Color.PINK, 1),
        # Kansas City - Oklahoma City (double)
        _route("Kansas City", "Oklahoma City", 2, Color.WILD, 0),
        _route("Kansas City", "Oklahoma City", 2, Color.WILD, 1),
        # Oklahoma City - Little Rock
        _route("Oklahoma City", "Little Rock", 2, Color.WILD),
        # Oklahoma City - Dallas (double)
        _route("Oklahoma City", "Dallas", 2, Color.WILD, 0),
        _route("Oklahoma City", "Dallas", 2, Color.WILD, 1),
        # Dallas - Little Rock
        _route("Dallas", "Little Rock", 2, Color.WILD),
        # Dallas - Houston (double)
        _route("Dallas", "Houston", 1, Color.WILD, 0),
        _route("Dallas", "Houston", 1, Color.WILD, 1),
        # Houston - New Orleans
        _route("Houston", "New Orleans", 2, Color.WILD),
        # Little Rock - Saint Louis
        _route("Little Rock", "Saint Louis", 2, Color.WILD),
        # Little Rock - Nashville
        _route("Little Rock", "Nashville", 3, Color.WHITE),
        # Little Rock - New Orleans
        _route("Little Rock", "New Orleans", 3, Color.GREEN),
        # Saint Louis - Nashville
        _route("Saint Louis", "Nashville", 2, Color.WILD),
        # Saint Louis - Chicago (double)
        _route("Saint Louis", "Chicago", 2, Color.GREEN, 0),
        _route("Saint Louis", "Chicago", 2, Color.WHITE, 1),
        # Saint Louis - Pittsburgh
        _route("Saint Louis", "Pittsburgh", 5, Color.GREEN),
        # Chicago - Pittsburgh (double)
        _route("Chicago", "Pittsburgh", 3, Color.BLACK, 0),
        _route("Chicago", "Pittsburgh", 3, Color.ORANGE, 1),
        # Chicago - Toronto
        _route("Chicago", "Toronto", 4, Color.WHITE),
        # Sault St. Marie - Toronto
        _route("Sault St. Marie", "Toronto", 2, Color.WILD),
        # Sault St. Marie - Montreal
        _route("Sault St. Marie", "Montreal", 5, Color.BLACK),
        # Toronto - Pittsburgh
        _route("Toronto", "Pittsburgh", 2, Color.WILD),
        # Toronto - Montreal
        _route("Toronto", "Montreal", 3, Color.WILD),
        # Pittsburgh - Washington
        _route("Pittsburgh", "Washington", 2, Color.BLACK),
        # Pittsburgh - New York (double)
        _route("Pittsburgh", "New York", 2, Color.WHITE, 0),
        _route("Pittsburgh", "New York", 2, Color.GREEN, 1),
        # Pittsburgh - Nashville
        _route("Pittsburgh", "Nashville", 4, Color.YELLOW),
        # Nashville - Atlanta
        _route("Nashville", "Atlanta", 1, Color.WILD),
        # Nashville - Raleigh
        _route("Nashville", "Raleigh", 3, Color.BLACK),
        # New Orleans - Atlanta (double)
        _route("New Orleans", "Atlanta", 4, Color.ORANGE, 0),
        _route("New Orleans", "Atlanta", 4, Color.YELLOW, 1),
        # New Orleans - Miami
        _route("New Orleans", "Miami", 6, Color.RED),
        # Atlanta - Raleigh (double)
        _route("Atlanta", "Raleigh", 2, Color.WILD, 0),
        _route("Atlanta", "Raleigh", 2, Color.WILD, 1),
        # Atlanta - Charleston
        _route("Atlanta", "Charleston", 2, Color.WILD),
        # Atlanta - Miami
        _route("Atlanta", "Miami", 5, Color.BLUE),
        # Charleston - Raleigh
        _route("Charleston", "Raleigh", 2, Color.WILD),
        # Raleigh - Washington (double)
        _route("Raleigh", "Washington", 2, Color.WILD, 0),
        _route("Raleigh", "Washington", 2, Color.WILD, 1),
        # Washington - New York (double)
        _route("Washington", "New York", 2, Color.ORANGE, 0),
        _route("Washington", "New York", 2, Color.BLACK, 1),
        # Montreal - New York
        _route("Montreal", "New York", 3, Color.BLUE),
        # Montreal - Boston (double)
        _route("Montreal", "Boston", 2, Color.WILD, 0),
        _route("Montreal", "Boston", 2, Color.WILD, 1),
        # New York - Boston (double)
        _route("New York", "Boston", 2, Color.YELLOW, 0),
        _route("New York", "Boston", 2, Color.RED, 1),
        # Miami - Charleston  (not in original; skip)
    ]

    return {r.id: r for r in routes_list}


# ---------------------------------------------------------------------------
# Destination tickets
# ---------------------------------------------------------------------------

def build_destination_tickets() -> list[DestinationTicket]:
    tickets = [
        DestinationTicket(1,  "Los Angeles",    "New York",          21),
        DestinationTicket(2,  "Duluth",          "Houston",           8),
        DestinationTicket(3,  "Sault St. Marie", "Nashville",         8),
        DestinationTicket(4,  "New York",        "Atlanta",           6),
        DestinationTicket(5,  "Portland",        "Nashville",         17),
        DestinationTicket(6,  "Vancouver",       "Montreal",          20),
        DestinationTicket(7,  "Duluth",          "El Paso",           10),
        DestinationTicket(8,  "Toronto",         "Miami",             10),
        DestinationTicket(9,  "Portland",        "Phoenix",           11),
        DestinationTicket(10, "Dallas",          "New York",          11),
        DestinationTicket(11, "Calgary",         "Salt Lake City",    7),
        DestinationTicket(12, "Calgary",         "Phoenix",           13),
        DestinationTicket(13, "Los Angeles",     "Miami",             20),
        DestinationTicket(14, "Winnipeg",        "Little Rock",       11),
        DestinationTicket(15, "San Francisco",   "Atlanta",           17),
        DestinationTicket(16, "Kansas City",     "Houston",           5),
        DestinationTicket(17, "Los Angeles",     "Chicago",           16),
        DestinationTicket(18, "Denver",          "Pittsburgh",        11),
        DestinationTicket(19, "Chicago",         "Santa Fe",          9),
        DestinationTicket(20, "Vancouver",       "Santa Fe",          13),
        DestinationTicket(21, "Boston",          "Miami",             12),
        DestinationTicket(22, "Chicago",         "New Orleans",       7),
        DestinationTicket(23, "Montreal",        "Atlanta",           9),
        DestinationTicket(24, "Seattle",         "Los Angeles",       9),
        DestinationTicket(25, "Denver",          "El Paso",           4),
        DestinationTicket(26, "Helena",          "Los Angeles",       8),
        DestinationTicket(27, "Winnipeg",        "Houston",           12),
        DestinationTicket(28, "Montreal",        "New Orleans",       13),
        DestinationTicket(29, "Seattle",         "New York",          22),
        DestinationTicket(30, "Chicago",         "Miami",             13),
    ]
    return tickets
