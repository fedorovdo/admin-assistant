from __future__ import annotations

from pydantic import SecretStr

from admin_assistant.core.enums import AuthType, HostKeyPolicy, RunKind, RunStatus, ShellType, StreamType
from admin_assistant.core.time import utc_now
from admin_assistant.infrastructure.db.repositories.execution_repository_sqlalchemy import (
    SqlAlchemyExecutionRepository,
)
from admin_assistant.infrastructure.db.repositories.script_repository_sqlalchemy import (
    SqlAlchemyScriptRepository,
)
from admin_assistant.infrastructure.db.repositories.server_repository_sqlalchemy import (
    SqlAlchemyServerRepository,
)
from admin_assistant.infrastructure.db.session import create_session_factory
from admin_assistant.modules.execution.dto import (
    CommandExecutionResult,
    RunOutputQuery,
    RunRequest,
    RunStatusQuery,
)
from admin_assistant.modules.execution.service import DefaultExecutionService
from admin_assistant.modules.scripts.dto import ScriptCreateRequest
from admin_assistant.modules.scripts.service import DefaultScriptService
from admin_assistant.modules.servers.dto import ServerCreateRequest
from admin_assistant.modules.servers.models import Server
from admin_assistant.modules.servers.service import DefaultServerService


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
        del server, shell_type, requires_sudo, requires_tty, timeout_sec, password, key_passphrase
        return CommandExecutionResult(
            stdout=f"ran: {command_text}\n",
            stderr="warning line\n",
            exit_code=1,
            completed_at=utc_now(),
            error_message="Remote command failed.",
        )

    def execute_script(
        self,
        server: Server,
        script,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> CommandExecutionResult:
        del server, password, key_passphrase
        return CommandExecutionResult(
            stdout=f"script: {script.name}\n",
            stderr="",
            exit_code=0,
            completed_at=utc_now(),
        )


def test_manual_command_execution_persists_run_target_and_output(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'execution.db').as_posix()}"
    session_factory = create_session_factory(database_url=database_url, create_schema=True)

    server_repository = SqlAlchemyServerRepository(session_factory=session_factory)
    script_repository = SqlAlchemyScriptRepository(session_factory=session_factory)
    execution_repository = SqlAlchemyExecutionRepository(session_factory=session_factory)
    secret_store = MemorySecretStore()

    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )
    created_server = server_service.create_server(
        ServerCreateRequest(
            name="db-01",
            host="198.51.100.50",
            username="admin",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-123"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )

    execution_service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=script_repository,
        secret_store=secret_store,
        ssh_gateway=FakeExecutionGateway(),
        publish_event=lambda event: None,
        task_runner=None,  # type: ignore[arg-type]
    )

    launch = execution_service.start_run(
        RunRequest(
            run_kind=RunKind.COMMAND,
            server_ids=(created_server.id,),
            command_text="uname -a",
            shell_type=ShellType.SH,
        )
    )
    status = execution_service.get_run_status(RunStatusQuery(run_id=launch.run_id))
    chunks = execution_service.list_run_output(RunOutputQuery(run_id=launch.run_id))

    assert launch.status is RunStatus.FAILED
    assert status.targets[0].status is RunStatus.FAILED
    assert status.targets[0].exit_code == 1
    assert len(chunks) == 2
    assert chunks[0].stream is StreamType.STDOUT
    assert chunks[1].stream is StreamType.STDERR
    assert "uname -a" in chunks[0].chunk_text


def test_privileged_manual_command_persists_requires_sudo_on_run(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'execution-sudo.db').as_posix()}"
    session_factory = create_session_factory(database_url=database_url, create_schema=True)

    server_repository = SqlAlchemyServerRepository(session_factory=session_factory)
    script_repository = SqlAlchemyScriptRepository(session_factory=session_factory)
    execution_repository = SqlAlchemyExecutionRepository(session_factory=session_factory)
    secret_store = MemorySecretStore()

    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )
    created_server = server_service.create_server(
        ServerCreateRequest(
            name="db-sudo",
            host="198.51.100.51",
            username="admin",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-sudo"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )

    execution_service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=script_repository,
        secret_store=secret_store,
        ssh_gateway=FakeExecutionGateway(),
        publish_event=lambda event: None,
        task_runner=None,  # type: ignore[arg-type]
    )

    launch = execution_service.start_run(
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


def test_script_execution_persists_run_target_and_output(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'execution-script.db').as_posix()}"
    session_factory = create_session_factory(database_url=database_url, create_schema=True)

    server_repository = SqlAlchemyServerRepository(session_factory=session_factory)
    script_repository = SqlAlchemyScriptRepository(session_factory=session_factory)
    execution_repository = SqlAlchemyExecutionRepository(session_factory=session_factory)
    secret_store = MemorySecretStore()

    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )
    script_service = DefaultScriptService(repository=script_repository)

    created_server = server_service.create_server(
        ServerCreateRequest(
            name="app-01",
            host="203.0.113.10",
            username="deploy",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-456"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )
    created_script = script_service.create_script(
        ScriptCreateRequest(
            name="Nginx status",
            description="Check nginx status",
            content="systemctl status nginx --no-pager",
            shell_type=ShellType.BASH,
            timeout_sec=120,
        )
    )

    execution_service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=script_repository,
        secret_store=secret_store,
        ssh_gateway=FakeExecutionGateway(),
        publish_event=lambda event: None,
        task_runner=None,  # type: ignore[arg-type]
    )

    launch = execution_service.start_run(
        RunRequest(
            run_kind=RunKind.SCRIPT,
            server_ids=(created_server.id,),
            script_id=created_script.id,
            shell_type=ShellType.SH,
        )
    )
    status = execution_service.get_run_status(RunStatusQuery(run_id=launch.run_id))
    chunks = execution_service.list_run_output(RunOutputQuery(run_id=launch.run_id))

    assert launch.status is RunStatus.SUCCEEDED
    assert status.targets[0].status is RunStatus.SUCCEEDED
    assert status.targets[0].exit_code == 0
    assert len(chunks) == 1
    assert chunks[0].stream is StreamType.STDOUT
    assert "Nginx status" in chunks[0].chunk_text


def test_multi_target_manual_command_persists_multiple_target_results(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'execution-multi.db').as_posix()}"
    session_factory = create_session_factory(database_url=database_url, create_schema=True)

    server_repository = SqlAlchemyServerRepository(session_factory=session_factory)
    script_repository = SqlAlchemyScriptRepository(session_factory=session_factory)
    execution_repository = SqlAlchemyExecutionRepository(session_factory=session_factory)
    secret_store = MemorySecretStore()

    server_service = DefaultServerService(
        repository=server_repository,
        secret_store=secret_store,
        connectivity_probe=StubConnectivityProbe(),
    )
    first_server = server_service.create_server(
        ServerCreateRequest(
            name="web-01",
            host="203.0.113.10",
            username="deploy",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-1"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )
    second_server = server_service.create_server(
        ServerCreateRequest(
            name="web-02",
            host="203.0.113.11",
            username="deploy",
            auth_type=AuthType.PASSWORD,
            password=SecretStr("pw-2"),
            host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
        )
    )

    class MultiHostGateway:
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
            del shell_type, requires_sudo, requires_tty, timeout_sec, password, key_passphrase
            if server.name == "web-01":
                return CommandExecutionResult(stdout=f"{server.name}: {command_text}\n", stderr="", exit_code=0)
            return CommandExecutionResult(
                stdout="",
                stderr=f"{server.name}: failure\n",
                exit_code=3,
                error_message="failure",
            )

        def execute_script(self, server: Server, script, password: str | None = None, key_passphrase: str | None = None):
            raise NotImplementedError

    execution_service = DefaultExecutionService(
        repository=execution_repository,
        output_repository=execution_repository,
        server_reader=server_repository,
        script_reader=script_repository,
        secret_store=secret_store,
        ssh_gateway=MultiHostGateway(),
        publish_event=lambda event: None,
        task_runner=None,  # type: ignore[arg-type]
    )

    launch = execution_service.start_run(
        RunRequest(
            run_kind=RunKind.COMMAND,
            server_ids=(first_server.id, second_server.id),
            command_text="hostname",
            shell_type=ShellType.BASH,
        )
    )
    status = execution_service.get_run_status(RunStatusQuery(run_id=launch.run_id))
    chunks = execution_service.list_run_output(RunOutputQuery(run_id=launch.run_id))

    assert launch.status is RunStatus.FAILED
    assert len(status.targets) == 2
    assert {target.server_name for target in status.targets} == {"web-01", "web-02"}
    assert len(chunks) == 2
    assert {chunk.stream for chunk in chunks} == {StreamType.STDOUT, StreamType.STDERR}
