from __future__ import annotations

import sys
from types import ModuleType

from admin_assistant.core.enums import AuthType, HostKeyPolicy, ShellType
from admin_assistant.infrastructure.ssh import paramiko_gateway
from admin_assistant.modules.servers.models import Server


class FakeChannel:
    def __init__(self, exit_code: int = 0) -> None:
        self._exit_code = exit_code

    def recv_exit_status(self) -> int:
        return self._exit_code

    def shutdown_write(self) -> None:
        return None


class FakeStdin:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self.channel = FakeChannel()

    def write(self, value: str) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class FakeReadable:
    def __init__(self, text: str, exit_code: int) -> None:
        self._text = text
        self.channel = FakeChannel(exit_code=exit_code)

    def read(self) -> bytes:
        return self._text.encode("utf-8")


class FakeSSHClient:
    def __init__(self, stdout_text: str, stderr_text: str, exit_code: int) -> None:
        self.stdout_text = stdout_text
        self.stderr_text = stderr_text
        self.exit_code = exit_code
        self.connect_kwargs: dict[str, object] | None = None
        self.exec_calls: list[dict[str, object]] = []
        self.stdin = FakeStdin()
        self.closed = False

    def connect(self, **kwargs: object) -> None:
        self.connect_kwargs = kwargs

    def exec_command(self, command: str, timeout: int | None = None, get_pty: bool = False):
        self.exec_calls.append(
            {
                "command": command,
                "timeout": timeout,
                "get_pty": get_pty,
            }
        )
        return (
            self.stdin,
            FakeReadable(self.stdout_text, exit_code=self.exit_code),
            FakeReadable(self.stderr_text, exit_code=self.exit_code),
        )

    def close(self) -> None:
        self.closed = True


def _install_fake_paramiko(monkeypatch) -> None:
    fake_paramiko = ModuleType("paramiko")
    fake_paramiko.AuthenticationException = type("AuthenticationException", (Exception,), {})
    fake_paramiko.BadHostKeyException = type("BadHostKeyException", (Exception,), {})
    fake_paramiko.SSHException = type("SSHException", (Exception,), {})
    monkeypatch.setitem(sys.modules, "paramiko", fake_paramiko)


def test_paramiko_gateway_redacts_echoed_sudo_password_from_output(monkeypatch) -> None:
    _install_fake_paramiko(monkeypatch)
    fake_client = FakeSSHClient(
        stdout_text="super-secret\ncommand output\n",
        stderr_text="sudo: super-secret\npermission denied\n",
        exit_code=1,
    )
    monkeypatch.setattr(paramiko_gateway, "_build_ssh_client", lambda server: fake_client)

    gateway = paramiko_gateway.ParamikoSSHExecutionGateway(timeout_sec=15)
    server = Server(
        id="server-1",
        name="web-01",
        host="192.0.2.10",
        port=22,
        username="admin",
        auth_type=AuthType.PASSWORD,
        host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
    )

    result = gateway.execute_manual_command(
        server=server,
        command_text="systemctl restart sshd",
        shell_type=ShellType.BASH,
        requires_sudo=True,
        requires_tty=True,
        password="super-secret",
    )

    assert fake_client.exec_calls[0]["get_pty"] is True
    assert "stty -echo" in str(fake_client.exec_calls[0]["command"])
    assert "super-secret" not in result.stdout
    assert "super-secret" not in result.stderr
    assert "super-secret" not in (result.error_message or "")
    assert "[REDACTED]" in result.stdout
    assert "[REDACTED]" in result.stderr


def test_paramiko_gateway_redacts_secret_from_exception_text(monkeypatch) -> None:
    _install_fake_paramiko(monkeypatch)
    fake_exception_type = sys.modules["paramiko"].SSHException

    class FailingSSHClient:
        def connect(self, **kwargs: object) -> None:
            raise fake_exception_type("sudo failed for super-secret")

        def close(self) -> None:
            return None

    monkeypatch.setattr(paramiko_gateway, "_build_ssh_client", lambda server: FailingSSHClient())

    gateway = paramiko_gateway.ParamikoSSHExecutionGateway(timeout_sec=15)
    server = Server(
        id="server-2",
        name="web-02",
        host="192.0.2.11",
        port=22,
        username="admin",
        auth_type=AuthType.PASSWORD,
        host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
    )

    result = gateway.execute_manual_command(
        server=server,
        command_text="systemctl restart nginx",
        shell_type=ShellType.BASH,
        requires_sudo=True,
        requires_tty=True,
        password="super-secret",
    )

    assert result.exit_code == 255
    assert "super-secret" not in result.stderr
    assert "super-secret" not in (result.error_message or "")
    assert "[REDACTED]" in result.stderr
