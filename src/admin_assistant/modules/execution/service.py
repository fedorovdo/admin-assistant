from __future__ import annotations

from concurrent.futures import as_completed
from collections.abc import Callable
from uuid import uuid4
from typing import Protocol

from admin_assistant.app.events import (
    AppEvent,
    OutputChunkReceivedEvent,
    RunCompletedEvent,
    RunCreatedEvent,
    RunStartedEvent,
    TargetCompletedEvent,
    TargetStartedEvent,
)
from admin_assistant.app.task_runner import TaskRunner
from admin_assistant.core.enums import ExecutionMethod, RunKind, RunStatus, StreamType
from admin_assistant.core.errors import NotFoundError, ValidationError
from admin_assistant.core.time import utc_now
from admin_assistant.modules.execution.dto import (
    ActiveRunsQuery,
    CancelRunRequest,
    CommandExecutionResult,
    RunOutputQuery,
    RunLaunchResult,
    RunRequest,
    RunStatusQuery,
    RunStatusSnapshot,
    RunSummary,
    TargetResultView,
    OutputChunkDTO,
)
from admin_assistant.modules.execution.models import RunTargetResult, ScriptRun
from admin_assistant.modules.execution.ports import (
    ExecutionRepository,
    OutputChunkRepository,
    SSHExecutionGateway,
    ScriptReader,
    ServerReader,
)
from admin_assistant.modules.scripts.models import Script
from admin_assistant.modules.servers.models import Server
from admin_assistant.modules.servers.ports import SecretStore


class ExecutionService(Protocol):
    def start_run(self, request: RunRequest) -> RunLaunchResult:
        ...

    def cancel_run(self, request: CancelRunRequest) -> None:
        ...

    def get_run_status(self, query: RunStatusQuery) -> RunStatusSnapshot:
        ...

    def list_run_output(self, query: RunOutputQuery) -> tuple[OutputChunkDTO, ...]:
        ...

    def list_active_runs(self, query: ActiveRunsQuery) -> tuple[RunSummary, ...]:
        ...


class DefaultExecutionService(ExecutionService):
    def __init__(
        self,
        repository: ExecutionRepository,
        output_repository: OutputChunkRepository,
        server_reader: ServerReader,
        script_reader: ScriptReader,
        secret_store: SecretStore,
        ssh_gateway: SSHExecutionGateway,
        publish_event: Callable[[AppEvent], None],
        task_runner: TaskRunner,
    ) -> None:
        self._repository = repository
        self._output_repository = output_repository
        self._server_reader = server_reader
        self._script_reader = script_reader
        self._secret_store = secret_store
        self._ssh_gateway = ssh_gateway
        self._publish_event = publish_event
        self._task_runner = task_runner

    def start_run(self, request: RunRequest) -> RunLaunchResult:
        servers = self._load_servers(request.server_ids)

        if request.run_kind in {RunKind.COMMAND, RunKind.AI_ACTION}:
            return self._execute_manual_command(request=request, servers=servers)
        if request.run_kind is RunKind.SCRIPT:
            return self._execute_script(request=request, servers=servers)
        raise ValidationError("Only manual command, AI action, and script execution are implemented in this slice.")

    def cancel_run(self, request: CancelRunRequest) -> None:
        raise NotImplementedError

    def get_run_status(self, query: RunStatusQuery) -> RunStatusSnapshot:
        script_run = self._repository.get_run(query.run_id)
        if script_run is None:
            raise NotFoundError(f"Run '{query.run_id}' was not found.")

        targets = tuple(
            TargetResultView(
                id=target.id,
                server_id=target.server_id,
                server_name=str(target.server_snapshot.get("name", target.server_id)),
                status=target.status,
                exit_code=target.exit_code,
                error_message=target.error_message,
            )
            for target in self._repository.list_target_results(query.run_id)
        )
        return RunStatusSnapshot(
            run_id=script_run.id,
            status=script_run.status,
            started_at=script_run.started_at,
            completed_at=script_run.completed_at,
            targets=targets,
        )

    def list_run_output(self, query: RunOutputQuery) -> tuple[OutputChunkDTO, ...]:
        return self._output_repository.list_output_chunks(query.run_id)

    def list_active_runs(self, query: ActiveRunsQuery) -> tuple[RunSummary, ...]:
        raise NotImplementedError

    def _resolve_server_secrets(self, server: Server) -> tuple[str | None, str | None]:
        password: str | None = None
        key_passphrase: str | None = None

        if server.auth_type.value == "password":
            if not server.credential_ref:
                raise ValidationError("Selected server does not have a stored password reference.")
            password = self._secret_store.read_secret(server.credential_ref)
            if not password:
                raise ValidationError("Stored password could not be resolved from secret storage.")
        elif server.key_passphrase_ref:
            key_passphrase = self._secret_store.read_secret(server.key_passphrase_ref)

        return password, key_passphrase

    def _load_servers(self, server_ids: tuple[str, ...]) -> tuple[Server, ...]:
        if not server_ids:
            raise ValidationError("Execution requires at least one selected server.")

        servers: list[Server] = []
        for server_id in server_ids:
            server = self._server_reader.get(server_id)
            if server is None:
                raise NotFoundError(f"Server '{server_id}' was not found.")
            servers.append(server)
        return tuple(servers)

    def _execute_manual_command(
        self,
        request: RunRequest,
        servers: tuple[Server, ...],
    ) -> RunLaunchResult:
        if not request.command_text or not request.command_text.strip():
            raise ValidationError("Manual command text is required.")

        now = utc_now()
        run_id = str(uuid4())
        targets = tuple(
            self._build_target(
                run_id=run_id,
                server=server,
                started_at=now,
                method=ExecutionMethod.MANUAL_COMMAND,
            )
            for server in servers
        )
        script_run = ScriptRun(
            id=run_id,
            run_kind=request.run_kind,
            status=RunStatus.RUNNING,
            command_snapshot=request.command_text.strip(),
            shell_type=request.shell_type,
            requires_sudo=request.requires_sudo,
            requires_tty=request.requires_tty,
            requested_at=now,
            started_at=now,
            request_ai_analysis=request.request_ai_analysis,
            initiator=request.initiator,
            source_analysis_id=request.source_analysis_id,
            source_action_id=request.source_action_id,
        )
        self._repository.create_run(script_run, targets)
        self._publish_run_created(script_run, targets)
        self._publish_run_started(script_run)

        self._execute_targets(
            targets=targets,
            servers=servers,
            runner=lambda server: self._run_manual_command_on_server(
                server=server,
                command_text=request.command_text.strip(),
                shell_type=request.shell_type,
                requires_sudo=request.requires_sudo,
                requires_tty=request.requires_tty,
                timeout_sec=request.timeout_sec,
            ),
        )
        return self._finalize_run(script_run, targets)

    def _execute_script(
        self,
        request: RunRequest,
        servers: tuple[Server, ...],
    ) -> RunLaunchResult:
        if not request.script_id:
            raise ValidationError("A selected script is required.")

        script = self._script_reader.get(request.script_id)
        if script is None:
            raise NotFoundError(f"Script '{request.script_id}' was not found.")

        now = utc_now()
        run_id = str(uuid4())
        targets = tuple(
            self._build_target(
                run_id=run_id,
                server=server,
                started_at=now,
                method=ExecutionMethod.INLINE_STDIN,
            )
            for server in servers
        )
        script_run = ScriptRun(
            id=run_id,
            run_kind=request.run_kind,
            status=RunStatus.RUNNING,
            script_id=script.id,
            script_snapshot={
                "id": script.id,
                "name": script.name,
                "description": script.description,
                "shell_type": script.shell_type.value,
                "requires_tty": script.requires_tty,
                "timeout_sec": script.timeout_sec,
                "version": script.version,
            },
            shell_type=script.shell_type,
            requires_sudo=False,
            requires_tty=script.requires_tty,
            requested_at=now,
            started_at=now,
            request_ai_analysis=request.request_ai_analysis,
            initiator=request.initiator,
            source_analysis_id=request.source_analysis_id,
            source_action_id=request.source_action_id,
        )
        self._repository.create_run(script_run, targets)
        self._publish_run_created(script_run, targets)
        self._publish_run_started(script_run)

        self._execute_targets(
            targets=targets,
            servers=servers,
            runner=lambda server: self._run_script_on_server(server=server, script=script),
        )
        return self._finalize_run(script_run, targets)

    def _build_target(
        self,
        run_id: str,
        server: Server,
        started_at,
        method: ExecutionMethod,
    ) -> RunTargetResult:
        return RunTargetResult(
            id=str(uuid4()),
            run_id=run_id,
            server_id=server.id,
            server_snapshot={
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "port": server.port,
                "username": server.username,
            },
            status=RunStatus.RUNNING,
            execution_method=method,
            started_at=started_at,
        )

    def _execute_targets(
        self,
        targets: tuple[RunTargetResult, ...],
        servers: tuple[Server, ...],
        runner: Callable[[Server], CommandExecutionResult],
    ) -> None:
        if len(servers) == 1 or self._task_runner is None:
            for target, server in zip(targets, servers, strict=False):
                self._publish_target_started(target)
                result = self._safe_run_target(server=server, runner=runner)
                self._apply_target_result(target=target, result=result)
            return

        future_map = {}
        for target, server in zip(targets, servers, strict=False):
            self._publish_target_started(target)
            future = self._task_runner.submit(self._safe_run_target, server=server, runner=runner)
            future_map[future] = target
        for future in as_completed(future_map):
            target = future_map[future]
            result = future.result()
            self._apply_target_result(target=target, result=result)

    def _safe_run_target(
        self,
        server: Server,
        runner: Callable[[Server], CommandExecutionResult],
    ) -> CommandExecutionResult:
        try:
            return runner(server)
        except Exception as exc:
            return CommandExecutionResult(
                stderr=str(exc),
                exit_code=255,
                error_message=str(exc),
            )

    def _apply_target_result(self, target: RunTargetResult, result: CommandExecutionResult) -> None:
        seq_no = 1
        server_name = str(target.server_snapshot.get("name", target.server_id))
        if result.stdout:
            output_chunk = self._output_repository.append_output_chunk(
                target_result_id=target.id,
                stream=StreamType.STDOUT,
                seq_no=seq_no,
                chunk_text=result.stdout,
            )
            self._publish_event(
                OutputChunkReceivedEvent(
                    correlation_id=target.run_id,
                    run_id=target.run_id,
                    target_result_id=target.id,
                    server_id=target.server_id,
                    server_name=server_name,
                    stream=output_chunk.stream.value,
                    seq_no=output_chunk.seq_no,
                    chunk_text=output_chunk.chunk_text,
                )
            )
            seq_no += 1
        if result.stderr:
            output_chunk = self._output_repository.append_output_chunk(
                target_result_id=target.id,
                stream=StreamType.STDERR,
                seq_no=seq_no,
                chunk_text=result.stderr,
            )
            self._publish_event(
                OutputChunkReceivedEvent(
                    correlation_id=target.run_id,
                    run_id=target.run_id,
                    target_result_id=target.id,
                    server_id=target.server_id,
                    server_name=server_name,
                    stream=output_chunk.stream.value,
                    seq_no=output_chunk.seq_no,
                    chunk_text=output_chunk.chunk_text,
                )
            )

        completed_at = result.completed_at or utc_now()
        target.exit_code = result.exit_code
        target.completed_at = completed_at
        target.error_message = result.error_message or (
            result.stderr.strip() if result.exit_code != 0 and result.stderr.strip() else None
        )
        target.status = RunStatus.SUCCEEDED if result.exit_code == 0 else RunStatus.FAILED
        self._repository.update_target_result(target)
        self._publish_event(
            TargetCompletedEvent(
                correlation_id=target.run_id,
                run_id=target.run_id,
                target_result_id=target.id,
                server_id=target.server_id,
                status=target.status.value,
                exit_code=target.exit_code,
                completed_at=target.completed_at or completed_at,
                error_message=target.error_message,
            )
        )

    def _finalize_run(self, script_run: ScriptRun, targets: tuple[RunTargetResult, ...]) -> RunLaunchResult:
        completed_times = [target.completed_at for target in targets if target.completed_at is not None]
        script_run.completed_at = max(completed_times) if completed_times else utc_now()
        script_run.status = (
            RunStatus.SUCCEEDED
            if all(target.status is RunStatus.SUCCEEDED for target in targets)
            else RunStatus.FAILED
        )
        self._repository.update_run(script_run)
        success_count = sum(1 for target in targets if target.status is RunStatus.SUCCEEDED)
        self._publish_event(
            RunCompletedEvent(
                correlation_id=script_run.id,
                run_id=script_run.id,
                status=script_run.status.value,
                completed_at=script_run.completed_at or utc_now(),
                target_count=len(targets),
                success_count=success_count,
                failure_count=len(targets) - success_count,
                analysis_requested=script_run.request_ai_analysis,
            )
        )
        return RunLaunchResult(run_id=script_run.id, status=script_run.status)

    def _publish_run_created(
        self,
        script_run: ScriptRun,
        targets: tuple[RunTargetResult, ...],
    ) -> None:
        self._publish_event(
            RunCreatedEvent(
                correlation_id=script_run.id,
                run_id=script_run.id,
                run_kind=script_run.run_kind.value,
                server_ids=tuple(target.server_id for target in targets),
                shell_type=script_run.shell_type.value,
                requires_tty=script_run.requires_tty,
                request_ai_analysis=script_run.request_ai_analysis,
                initiator=script_run.initiator,
            )
        )

    def _publish_run_started(self, script_run: ScriptRun) -> None:
        self._publish_event(
            RunStartedEvent(
                correlation_id=script_run.id,
                run_id=script_run.id,
                started_at=script_run.started_at or utc_now(),
            )
        )

    def _publish_target_started(self, target: RunTargetResult) -> None:
        self._publish_event(
            TargetStartedEvent(
                correlation_id=target.run_id,
                run_id=target.run_id,
                target_result_id=target.id,
                server_id=target.server_id,
                server_name=str(target.server_snapshot.get("name", target.server_id)),
                execution_method=target.execution_method.value if target.execution_method else "",
                started_at=target.started_at or utc_now(),
            )
        )

    def _run_manual_command_on_server(
        self,
        server: Server,
        command_text: str,
        shell_type,
        requires_sudo: bool,
        requires_tty: bool,
        timeout_sec: int | None,
    ) -> CommandExecutionResult:
        password, key_passphrase = self._resolve_server_secrets(server)
        return self._ssh_gateway.execute_manual_command(
            server=server,
            command_text=command_text,
            shell_type=shell_type,
            requires_sudo=requires_sudo,
            requires_tty=requires_tty or requires_sudo,
            timeout_sec=timeout_sec,
            password=password,
            key_passphrase=key_passphrase,
        )

    def _run_script_on_server(self, server: Server, script: Script) -> CommandExecutionResult:
        password, key_passphrase = self._resolve_server_secrets(server)
        return self._ssh_gateway.execute_script(
            server=server,
            script=script,
            password=password,
            key_passphrase=key_passphrase,
        )
