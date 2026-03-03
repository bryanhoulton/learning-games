"""Game-specific exceptions."""


class GameError(Exception):
    """Base for all game rule violations."""


class InvalidAction(GameError):
    """Attempted action is not legal in the current game state."""


class NotYourTurn(GameError):
    pass


class WrongPhase(GameError):
    pass


class InsufficientCards(GameError):
    pass


class RouteAlreadyClaimed(GameError):
    pass


class InsufficientTrains(GameError):
    pass
