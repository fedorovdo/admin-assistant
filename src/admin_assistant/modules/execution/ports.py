from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from admin_assistant.core.enums import ShellType, StreamType
from admin_assistant.modules.execution.dto import CommandExecutionResult, OutputChunkDTO
from admin_assistant.modules.execution.models import RunTargetResult, ScriptRun
from admin_assistant.modules.scripts.models import Script
from admin_assistant.modules.servers.models import Server


class ExecutionRepository(Protocol):
    def create_run(self, script_run: ScriptRun, targets: Iterable[RunTargetResult]) -> ScriptRun:
        ...

    def update_run(self, script_run: ScriptRun) -> ScriptRun:
        ...

    def get_run(self, run_id: str) -> ScriptRun | None:
        ...

    def update_target_result(self, target: RunTargetResult) -> RunTargetResult:
        ...

    def list_target_results(self, run_id: str) -> tuple[RunTargetResult, ...]:
        ...


class OutputChunkRepository(Protocol):
    def append_output_chunk(
        self,
        target_result_id: str,
        stream: StreamType,
        seq_no: int,
        chunk_text: str,
    ) -> OutputChunkDTO:
        ...

    def list_output_chunks(self, run_id: str) -> tuple[OutputChunkDTO, ...]:
        ...


class ServerReader(Protocol):
    def get(self, server_id: str) -> Server | None:
        ...


class ScriptReader(Protocol):
    def get(self, script_id: str) -> Script | None:
        ...


class SSHExecutionGateway(Protocol):
    def execute_manual_command(
        self,
        server: Server,
        command_text: str,
        shell_type: ShellType,
        requires_sudo: bool = False,
        requires_tty: bool = False,
        timeout_sec: int | None = None,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> CommandExecutionResult:
        ...

    def execute_script(
        self,
        server: Server,
        script: Script,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> CommandExecutionResult:
        ...
