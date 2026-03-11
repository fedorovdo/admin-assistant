from __future__ import annotations

from typing import Protocol

from admin_assistant.modules.ai.dto import AIAnalysisView
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
from admin_assistant.modules.history.ports import HistoryReadStore


class HistoryQueryService(Protocol):
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


class DefaultHistoryQueryService(HistoryQueryService):
    def __init__(self, read_store: HistoryReadStore) -> None:
        self._read_store = read_store

    def list_runs(self, query: RunHistoryQuery) -> RunHistoryPage:
        return self._read_store.list_runs(query)

    def get_run_details(self, query: RunDetailsQuery) -> RunDetailsView:
        return self._read_store.get_run_details(query)

    def get_console_replay(self, query: ConsoleReplayQuery) -> ConsoleReplayView:
        return self._read_store.get_console_replay(query)

    def list_analyses(self, query: AnalysisHistoryQuery) -> AnalysisHistoryPage:
        return self._read_store.list_analyses(query)

    def get_analysis_details(self, query: AnalysisDetailsQuery) -> AIAnalysisView:
        return self._read_store.get_analysis_details(query)
