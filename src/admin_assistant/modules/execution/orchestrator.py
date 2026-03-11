from __future__ import annotations

from admin_assistant.modules.execution.dto import RunRequest


class ExecutionOrchestrator:
    def start(self, request: RunRequest) -> None:
        raise NotImplementedError
