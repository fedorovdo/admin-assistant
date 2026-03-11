from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any


EventHandler = Callable[[object], None]


class EventBus:
    def publish(self, event: object) -> None:
        raise NotImplementedError

    def subscribe(self, event_type: type[object], handler: EventHandler) -> None:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    def __init__(self) -> None:
        self._handlers: dict[type[object], list[EventHandler]] = defaultdict(list)

    def publish(self, event: object) -> None:
        for event_type, handlers in self._handlers.items():
            if isinstance(event, event_type):
                for handler in handlers:
                    handler(event)

    def subscribe(self, event_type: type[object], handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

