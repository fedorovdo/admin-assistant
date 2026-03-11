from __future__ import annotations

from concurrent.futures import Future
from pydantic import SecretStr

from admin_assistant.core.enums import AuthType, HostKeyPolicy, RunKind, RunStatus, ShellType, StreamType
from admin_assistant.core.time import utc_now
from admin_assistant.modules.execution.dto import (
    CommandExecutionResult,
    RunOutputQuery,
    RunRequest,
    RunStatusQuery,
)
from admin_assistant.modules.execution.models import RunTargetResult, ScriptRun
from admin_assistant.modules.execution.service import DefaultExecutionService
from admin_assistant.modules.scripts.dto import ScriptCreateRequest
from admin_assistant.modules.scripts.models import Script
from admin_assistant.modules.scripts.service import DefaultScriptService
from admin_assistant.modules.servers.dto import ServerCreateRequest
from admin_assistant.modules.servers.models import Server
from admin_assistant.modules.servers.service import DefaultServerService


class InMemoryExecutionRepository:
    def __init__(self) -> None:
        self.runs: dict[str, ScriptRun] = {}
        self.targets: dict[str, RunTargetResult] = {}
        self.output_by_run: dict[str, list] = {}
        self.target_to_run: dict[str, str] = {}

    def create_run(self, script_run: ScriptRun, targets) -> ScriptRun:
        self.runs[script_run.id] = script_run
        self.output_by_run.setdefault(script_run.id, [])
        for target in targets:
            self.targets[target.id] = target
            self.target_to_run[target.id] = script_run.id
        return script_run

    def update_run(self, script_run: ScriptRun) -> ScriptRun:
        self.runs[script_run.id] = script_run
        return script_run

    def get_run(self, run_id: str) -> ScriptRun | None:
        return self.runs.get(run_id)

    def update_target_result(self, target: RunTargetResult) -> RunTargetResult:
        self.targets[target.id] = target
        return target

    def list_target_results(self, run_id: str) -> tuple[RunTargetResult, ...]:
        return tuple(target for target in self.targets.values() if target.run_id == run_id)

    def append_output_chunk(self, target_result_id: str, stream: StreamType, seq_no: int, chunk_text: str):
        from admin_assistant.modules.execution.dto import OutputChunkDTO

        created = OutputChunkDTO(
            target_result_id=target_result_id,
            seq_no=seq_no,
            stream=stream,
            chunk_text=chunk_text,
            created_at=utc_now(),
        )
        run_id = self.target_to_run[target_result_id]
        self.output_by_run.setdefault(run_id, []).append(created)
        return created

    def list_output_chunks(self, run_id: str):
        return tuple(self.output_by_run.get(run_id, []))


class InMemoryServerRepository:
    def __init__(self) -> None:
        self.items: dict[str, Server] = {}

    def add(self, server: Server) -> Server:
        self.items[server.id] = server
        return server

    def update(self, server: Server) -> Server:
        self.items[server.id] = server
        return server

    def delete(self, server_id: str) -> None:
        self.items.pop(server_id, None)

    def get(self, server_id: str) -> Server | None:
        return self.items.get(server_id)

    def list(self, search_text: str | None = None) -> list[Server]:
        return list(self.items.values())


class NullScriptReader:
    def get(self, script_id: str):
        return None


class InMemoryScriptRepository:
    def __init__(self) -> None:
        self.items: dict[str, Script] = {}

    def add(self, script: Script) -> Script:
        self.items[script.id] = script
        return script

    def update(self, script: Script) -> Script:
        self.items[script.id] = script
        return script

    def delete(self, script_id: str) -> None:
        self.items.pop(script_id, None)

    def get(self, script_id: str) -> Script | None:
        return self.items.get(script_id)

    def list(self, search_text: str | None = None) -> list[Script]:
        return list(self.items.values())


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def save_secret(self, key: str, value: str) -> str:
        self.values[key] = value
        return key

    def read_secret(self, key: str) -> str | None:
        return self.values.get(key)

    def delete_secret(self, key: str) -> None:
        self.values.pop(key, None)


class StubConnectivityProbe:
    def test_connection(self, server: Server, password: str | None = None, key_passphrase: str | None = None):
        raise NotImplementedError


class FakeExecutionGateway:
    def __init__(self, result: CommandExecutionResult) -> None:
        self.result = result
        self.last_server: Server | None = None
        self.last_command: str | None = None
        self.last_shell_type: ShellType | None = None
        self.last_password: str | None = None
        self.last_requires_sudo: bool = False
        self.last_requires_tty: bool = False
        self.last_script: Script | None = None

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
        self.last_server = server
        self.last_command = command_text
        self.last_shell_type = shell_type
        self.last_password = password
        self.last_requires_sudo = requires_sudo
        self.last_requires_tty = requires_tty
        return self.result

    def execute_script(
        self,
        server: Server,
        script: Script,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> CommandExecutionResult:
        self.last_server = server
        self.last_script = script
        self.last_password = password
        return self.result


class MultiHostExecutionGateway:
    def __init__(self, results_by_host: dict[str, CommandExecutionResult]) -> None:
        self.results_by_host = results_by_host

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
        del command_text, shell_type, requires_sudo, requires_tty, timeout_sec, password, key_passphrase
        return self.results_by_host[server.name]

    def execute_script(
        self,
        server: Server,
        script: Script,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> CommandExecutionResult:
        del script, password, key_passphrase
        return self.results_by_host[server.name]


class InlineTaskRunner:
    def submit(self, func, *args, **kwargs):
        future = Future()
        try:
            future.set_result(func(*args, **kwargs))
        except Exception as exc:  # pragma: no cover - helper path
            future.set_exception(exc)
        return future


def test_execution_service_runs_manual_command_and_persists_outputs() -> None:
    server_repository = InMemoryServerRepository()
    secret_store = MemorySecretStore()
    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )
    created_server = server_service.create_server(
        ServerCreateRequest(
            name="web-01",
            host="192.0.2.10",
            username="root",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("super-secret"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )

    execution_repository = InMemoryExecutionRepository()
    gateway = FakeExecutionGateway(
        CommandExecutionResult(stdout="hello\n", stderr="", exit_code=0, completed_at=utc_now())
    )
    service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=NullScriptReader(),
        secret_store=secret_store,
        ssh_gateway=gateway,
        publish_event=lambda event: None,
        task_runner=None,  # type: ignore[arg-type]
    )

    launch = service.start_run(
        RunRequest(
            run_kind=RunKind.COMMAND,
            server_ids=(created_server.id,),
            command_text="echo hello",
            shell_type=ShellType.BASH,
        )
    )
    status = service.get_run_status(RunStatusQuery(run_id=launch.run_id))
    chunks = service.list_run_output(RunOutputQuery(run_id=launch.run_id))

    assert launch.status is RunStatus.SUCCEEDED
    assert gateway.last_command == "echo hello"
    assert gateway.last_shell_type is ShellType.BASH
    assert gateway.last_password == "super-secret"
    assert gateway.last_requires_sudo is False
    assert gateway.last_requires_tty is False
    assert status.targets[0].status is RunStatus.SUCCEEDED
    assert status.targets[0].exit_code == 0
    assert len(chunks) == 1
    assert chunks[0].stream is StreamType.STDOUT
    assert "hello" in chunks[0].chunk_text


def test_execution_service_runs_script_and_persists_outputs() -> None:
    server_repository = InMemoryServerRepository()
    script_repository = InMemoryScriptRepository()
    secret_store = MemorySecretStore()
    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )
    script_service = DefaultScriptService(repository=script_repository)

    created_server = server_service.create_server(
        ServerCreateRequest(
            name="web-01",
            host="192.0.2.10",
            username="root",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("super-secret"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )
    created_script = script_service.create_script(
        ScriptCreateRequest(
            name="Hello script",
            content="echo script-run",
            shell_type=ShellType.SH,
            timeout_sec=120,
        )
    )

    execution_repository = InMemoryExecutionRepository()
    gateway = FakeExecutionGateway(
        CommandExecutionResult(stdout="script-run\n", stderr="", exit_code=0, completed_at=utc_now())
    )
    service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=script_repository,
        secret_store=secret_store,
        ssh_gateway=gateway,
        publish_event=lambda event: None,
        task_runner=None,  # type: ignore[arg-type]
    )

    launch = service.start_run(
        RunRequest(
            run_kind=RunKind.SCRIPT,
            server_ids=(created_server.id,),
            script_id=created_script.id,
            shell_type=ShellType.BASH,
        )
    )
    status = service.get_run_status(RunStatusQuery(run_id=launch.run_id))
    chunks = service.list_run_output(RunOutputQuery(run_id=launch.run_id))

    assert launch.status is RunStatus.SUCCEEDED
    assert gateway.last_script is not None
    assert gateway.last_script.id == created_script.id
    assert gateway.last_script.shell_type is ShellType.SH
    assert gateway.last_password == "super-secret"
    assert status.targets[0].status is RunStatus.SUCCEEDED
    assert len(chunks) == 1
    assert chunks[0].stream is StreamType.STDOUT
    assert "script-run" in chunks[0].chunk_text


def test_execution_service_runs_privileged_manual_command_with_pty() -> None:
    server_repository = InMemoryServerRepository()
    secret_store = MemorySecretStore()
    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )
    created_server = server_service.create_server(
        ServerCreateRequest(
            name="root-box",
            host="192.0.2.15",
            username="admin",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("sudo-secret"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )

    execution_repository = InMemoryExecutionRepository()
    gateway = FakeExecutionGateway(
        CommandExecutionResult(stdout="", stderr="", exit_code=0, completed_at=utc_now())
    )
    service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=NullScriptReader(),
        secret_store=secret_store,
        ssh_gateway=gateway,
        publish_event=lambda event: None,
        task_runner=None,  # type: ignore[arg-type]
    )

    launch = service.start_run(
        RunRequest(
            run_kind=RunKind.COMMAND,
            server_ids=(created_server.id,),
            command_text="systemctl restart sshd",
            shell_type=ShellType.BASH,
            requires_sudo=True,
        )
    )
    stored_run = execution_repository.get_run(launch.run_id)

    assert stored_run is not None
    assert stored_run.requires_sudo is True
    assert gateway.last_requires_sudo is True
    assert gateway.last_requires_tty is True
    assert gateway.last_password == "sudo-secret"


def test_execution_service_runs_manual_command_across_multiple_hosts() -> None:
    server_repository = InMemoryServerRepository()
    secret_store = MemorySecretStore()
    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )
    first_server = server_service.create_server(
        ServerCreateRequest(
            name="web-01",
            host="192.0.2.10",
            username="root",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-1"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )
    second_server = server_service.create_server(
        ServerCreateRequest(
            name="web-02",
            host="192.0.2.11",
            username="root",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-2"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )

    execution_repository = InMemoryExecutionRepository()
    gateway = MultiHostExecutionGateway(
        {
            "web-01": CommandExecutionResult(stdout="ok-1\n", stderr="", exit_code=0, completed_at=utc_now()),
            "web-02": CommandExecutionResult(
                stdout="",
                stderr="failed-2\n",
                exit_code=2,
                completed_at=utc_now(),
                error_message="failed-2",
            ),
        }
    )
    service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=NullScriptReader(),
        secret_store=secret_store,
        ssh_gateway=gateway,
        publish_event=lambda event: None,
        task_runner=InlineTaskRunner(),  # type: ignore[arg-type]
    )

    launch = service.start_run(
        RunRequest(
            run_kind=RunKind.COMMAND,
            server_ids=(first_server.id, second_server.id),
            command_text="hostname",
            shell_type=ShellType.BASH,
        )
    )
    status = service.get_run_status(RunStatusQuery(run_id=launch.run_id))
    chunks = service.list_run_output(RunOutputQuery(run_id=launch.run_id))

    assert launch.status is RunStatus.FAILED
    assert len(status.targets) == 2
    assert {target.server_name for target in status.targets} == {"web-01", "web-02"}
    assert {target.status for target in status.targets} == {RunStatus.SUCCEEDED, RunStatus.FAILED}
    assert len(chunks) == 2
    assert {chunk.target_result_id for chunk in chunks} == {target.id for target in status.targets}


def test_execution_service_runs_script_across_multiple_hosts() -> None:
    server_repository = InMemoryServerRepository()
    script_repository = InMemoryScriptRepository()
    secret_store = MemorySecretStore()
    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )
    script_service = DefaultScriptService(repository=script_repository)

    first_server = server_service.create_server(
        ServerCreateRequest(
            name="app-01",
            host="192.0.2.20",
            username="deploy",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-1"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )
    second_server = server_service.create_server(
        ServerCreateRequest(
            name="app-02",
            host="192.0.2.21",
            username="deploy",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-2"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )
    created_script = script_service.create_script(
        ScriptCreateRequest(
            name="Deploy check",
            content="echo deploy-check",
            shell_type=ShellType.SH,
            timeout_sec=90,
        )
    )

    execution_repository = InMemoryExecutionRepository()
    gateway = MultiHostExecutionGateway(
        {
            "app-01": CommandExecutionResult(stdout="script-ok\n", stderr="", exit_code=0, completed_at=utc_now()),
            "app-02": CommandExecutionResult(stdout="script-ok-2\n", stderr="", exit_code=0, completed_at=utc_now()),
        }
    )
    service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=script_repository,
        secret_store=secret_store,
        ssh_gateway=gateway,
        publish_event=lambda event: None,
        task_runner=InlineTaskRunner(),  # type: ignore[arg-type]
    )

    launch = service.start_run(
        RunRequest(
            run_kind=RunKind.SCRIPT,
            server_ids=(first_server.id, second_server.id),
            script_id=created_script.id,
            shell_type=ShellType.BASH,
        )
    )
    status = service.get_run_status(RunStatusQuery(run_id=launch.run_id))
    chunks = service.list_run_output(RunOutputQuery(run_id=launch.run_id))

    assert launch.status is RunStatus.SUCCEEDED
    assert len(status.targets) == 2
    assert {target.server_name for target in status.targets} == {"app-01", "app-02"}
    assert all(target.status is RunStatus.SUCCEEDED for target in status.targets)
    assert len(chunks) == 2
    assert {chunk.target_result_id for chunk in chunks} == {target.id for target in status.targets}
