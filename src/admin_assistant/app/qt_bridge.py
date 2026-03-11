from __future__ import annotations

from admin_assistant.app.event_bus import EventBus
from admin_assistant.app.events import AppEvent

try:
    from PySide6.QtCore import QObject, Signal
except ModuleNotFoundError:
    class QtEventBridge:  # type: ignore[no-redef]
        def __init__(self, event_bus: EventBus) -> None:
            self._event_bus = event_bus
            self._subscribers: list[object] = []

        def _forward_event(self, event: object) -> None:
            return
else:
    class QtEventBridge(QObject):
        event_published = Signal(object)

        def __init__(self, event_bus: EventBus) -> None:
            super().__init__()
            self._event_bus = event_bus
            self._event_bus.subscribe(AppEvent, self._forward_event)

        def _forward_event(self, event: object) -> None:
            self.event_published.emit(event)
