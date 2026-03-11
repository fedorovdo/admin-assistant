from __future__ import annotations

from typing import Protocol

from admin_assistant.modules.ai.dto import AIProviderAnalysisResponse
from admin_assistant.modules.ai.models import AIAnalysis, AISuggestedAction
from admin_assistant.modules.execution.dto import OutputChunkDTO, RunLaunchResult, RunRequest
from admin_assistant.modules.execution.models import RunTargetResult, ScriptRun
from admin_assistant.modules.settings.models import AIProviderConfig
from admin_assistant.modules.settings.dto import ProviderConnectionTestResult


class AIProviderClient(Protocol):
    def analyze(
        self,
        prompt: str,
        provider_config: AIProviderConfig,
        api_key: str | None = None,
    ) -> AIProviderAnalysisResponse:
        ...

    def test_connection(
        self,
        provider_config: AIProviderConfig,
        api_key: str | None = None,
    ) -> ProviderConnectionTestResult:
        ...


class AIRepository(Protocol):
    def create_analysis(self, analysis: AIAnalysis) -> AIAnalysis:
        ...

    def create_suggested_actions(
        self,
        actions: tuple[AISuggestedAction, ...],
    ) -> tuple[AISuggestedAction, ...]:
        ...

    def get_analysis(self, analysis_id: str) -> AIAnalysis | None:
        ...

    def get_suggested_action(self, action_id: str) -> AISuggestedAction | None:
        ...

    def list_suggested_actions(self, analysis_id: str) -> tuple[AISuggestedAction, ...]:
        ...

    def update_suggested_action(self, action: AISuggestedAction) -> AISuggestedAction:
        ...


class ExecutionRunLauncher(Protocol):
    def start_run(self, request: RunRequest) -> RunLaunchResult:
        ...


class AnalysisRunReader(Protocol):
    def get_run(self, run_id: str) -> ScriptRun | None:
        ...

    def list_target_results(self, run_id: str) -> tuple[RunTargetResult, ...]:
        ...

    def list_output_chunks(self, run_id: str) -> tuple[OutputChunkDTO, ...]:
        ...
