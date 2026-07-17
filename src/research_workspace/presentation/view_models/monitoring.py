"""Session-only presentation state for Gate 2 unread indicators."""

from __future__ import annotations


class SessionUnreadState:
    """Viewed markers live only for this presentation instance."""

    def __init__(self) -> None:
        self._viewed: dict[tuple[str, str], str] = {}

    def is_unread(self, entity_type: str, entity_id: object, marker: str) -> bool:
        return self._viewed.get((entity_type, str(entity_id))) != marker

    def mark_viewed(
        self, entity_type: str, entity_id: object, marker: str
    ) -> None:
        self._viewed[(entity_type, str(entity_id))] = marker
