"""Event-bus port boundary."""

from collections.abc import Callable
from typing import Protocol

from research_workspace.domain.events import DomainEvent


EventHandler = Callable[[DomainEvent], None]


class EventBus(Protocol):
    """Dormant event publication and subscription contract."""

    def publish(self, event: DomainEvent) -> None:
        raise NotImplementedError

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        raise NotImplementedError
