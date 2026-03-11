from __future__ import annotations

from admin_assistant.core.enums import RunKind, RunStatus
from admin_assistant.modules.history.dto import (
    AnalysisDetailsQuery,
    AnalysisHistoryPage,
    AnalysisHistoryQuery,
    ConsoleReplayQuery,
    ConsoleReplayView,
    RunDetailsQuery,
    RunDetailsView,
    RunHistoryItem,
    RunHistoryPage,
    RunHistoryQuery,
)
from admin_assistant.modules.history.service import DefaultHistoryQueryService


class FakeHistoryReadStore:
    def list_runs(self, query: RunHistoryQuery) -> RunHistoryPage:
        del query
        return RunHistoryPage(
            items=(
                RunHistoryItem(
                    run_id="run-1",
                    run_kind=RunKind.COMMAND,
                    status=RunStatus.SUCCEEDED,
                    target_count=1,
                ),
            ),
            total_count=1,
        )

    def get_run_details(self, query: RunDetailsQuery) -> RunDetailsView:
        return RunDetailsView(
            run_id=query.run_id,
            run_kind=RunKind.COMMAND,
            status=RunStatus.SUCCEEDED,
            target_count=1,
        )

    def get_console_replay(self, query: ConsoleReplayQuery) -> ConsoleReplayView:
        del query
        return ConsoleReplayView()

    def list_analyses(self, query: AnalysisHistoryQuery) -> AnalysisHistoryPage:
        del query
        return AnalysisHistoryPage(items=(), total_count=0)

    def get_analysis_details(self, query: AnalysisDetailsQuery):
        from admin_assistant.core.enums import AIAnalysisStatus
        from admin_assistant.modules.ai.dto import AIAnalysisView

        return AIAnalysisView(
            id=query.analysis_id,
            run_id="run-1",
            provider_config_id="provider-1",
            status=AIAnalysisStatus.COMPLETED,
        )


def test_history_query_service_delegates_to_read_store() -> None:
    service = DefaultHistoryQueryService(read_store=FakeHistoryReadStore())

    run_page = service.list_runs(RunHistoryQuery())
    run_details = service.get_run_details(RunDetailsQuery(run_id="run-1"))
    replay = service.get_console_replay(ConsoleReplayQuery(run_id="run-1"))
    analyses = service.list_analyses(AnalysisHistoryQuery())
    analysis = service.get_analysis_details(AnalysisDetailsQuery(analysis_id="analysis-1"))

    assert run_page.total_count == 1
    assert run_details.run_id == "run-1"
    assert replay.all_hosts_lines == ()
    assert analyses.total_count == 0
    assert analysis.id == "analysis-1"
