"""Game-specific exceptions."""


class GameError(Exception):
    """Base for all game rule violations."""


class NotYourTurn(GameError):
    pass


class WrongPhase(GameError):
    pass


class InvalidAction(GameError):
    """Attempted action is not legal in the current game state."""


class InsufficientGems(GameError):
    pass


class InvalidCard(GameError):
    pass


class InvalidNoble(GameError):
    pass
