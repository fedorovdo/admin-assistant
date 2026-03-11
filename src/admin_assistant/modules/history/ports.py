from __future__ import annotations

from typing import Protocol

from admin_assistant.modules.history.dto import (
    AnalysisDetailsQuery,
    AnalysisHistoryPage,
    AnalysisHistoryQuery,
    ConsoleReplayQuery,
    ConsoleReplayView,
    RunDetailsQuery,
    RunDetailsView,
    RunHistoryPage,
    RunHistoryQuery,
)
from admin_assistant.modules.ai.dto import AIAnalysisView


class HistoryReadStore(Protocol):
    def list_runs(self, query: RunHistoryQuery) -> RunHistoryPage:
        ...

    def get_run_details(self, query: RunDetailsQuery) -> RunDetailsView:
        ...

    def get_console_replay(self, query: ConsoleReplayQuery) -> ConsoleReplayView:
        ...

    def list_analyses(self, query: AnalysisHistoryQuery) -> AnalysisHistoryPage:
        ...

    def get_analysis_details(self, query: AnalysisDetailsQuery) -> AIAnalysisView:
        ...
