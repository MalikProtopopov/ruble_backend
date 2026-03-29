"""Campaign business rules."""

from dataclasses import dataclass

# Valid status transitions
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"active"}),
    "active": frozenset({"paused", "completed"}),
    "paused": frozenset({"active"}),
    "completed": frozenset({"archived"}),
}


class InvalidStatusTransition(Exception):
    """Raised when attempting an invalid campaign status transition."""
    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f"Transition '{current}' → '{target}' is not allowed")


def validate_status_transition(current: str, target: str) -> None:
    """Raise InvalidStatusTransition if the move is not allowed."""
    allowed = VALID_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidStatusTransition(current, target)
