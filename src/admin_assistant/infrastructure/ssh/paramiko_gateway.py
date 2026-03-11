from __future__ import annotations

import shlex
import socket

from admin_assistant.core.enums import AuthType, HostKeyPolicy, ShellType
from admin_assistant.modules.execution.dto import CommandExecutionResult
from admin_assistant.modules.scripts.models import Script
from admin_assistant.modules.servers.dto import ConnectionTestResult
from admin_assistant.modules.servers.models import Server


def _build_ssh_client(server: Server):
    import paramiko

    client = paramiko.SSHClient()
    client.load_system_host_keys()

    # Temporary MVP behavior:
    # - strict: require host key to already be trusted
    # - trust_on_first_use/manual_approve: auto-add so local development is practical
    if server.host_key_policy is HostKeyPolicy.STRICT:
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    return client


def _build_connect_kwargs(
    server: Server,
    timeout_sec: int,
    password: str | None = None,
    key_passphrase: str | None = None,
) -> dict[str, object]:
    connect_kwargs: dict[str, object] = {
        "hostname": server.host,
        "port": server.port,
        "username": server.username,
        "timeout": timeout_sec,
        "banner_timeout": timeout_sec,
        "auth_timeout": timeout_sec,
        "look_for_keys": False,
        "allow_agent": False,
    }

    if server.auth_type is AuthType.PASSWORD:
        connect_kwargs["password"] = password
    else:
        connect_kwargs["key_filename"] = server.key_path
        if key_passphrase:
            connect_kwargs["passphrase"] = key_passphrase

    return connect_kwargs


class ParamikoConnectivityProbe:
    def __init__(self, timeout_sec: int = 10) -> None:
        self._timeout_sec = timeout_sec

    def test_connection(
        self,
        server: Server,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> ConnectionTestResult:
        import paramiko

        client = _build_ssh_client(server)
        connect_kwargs = _build_connect_kwargs(
            server=server,
            timeout_sec=self._timeout_sec,
            password=password,
            key_passphrase=key_passphrase,
        )

        try:
            client.connect(**connect_kwargs)
            return ConnectionTestResult(success=True, message="SSH connection succeeded.")
        except FileNotFoundError:
            return ConnectionTestResult(success=False, message="Private key file was not found.")
        except paramiko.AuthenticationException:
            return ConnectionTestResult(success=False, message="Authentication failed.")
        except paramiko.BadHostKeyException:
            return ConnectionTestResult(success=False, message="Host key verification failed.")
        except (paramiko.SSHException, OSError, socket.error) as exc:
            return ConnectionTestResult(success=False, message=str(exc))
        finally:
            client.close()


class ParamikoSSHExecutionGateway:
    def __init__(self, timeout_sec: int = 30) -> None:
        self._timeout_sec = timeout_sec

    def _sanitize_secret_text(
        self,
        text: str,
        secret_values: tuple[str, ...],
    ) -> str:
        sanitized = text
        for secret_value in secret_values:
            if secret_value:
                sanitized = sanitized.replace(secret_value, "[REDACTED]")
        return sanitized

    def _build_manual_command(
        self,
        command_text: str,
        requires_sudo: bool,
        requires_tty: bool,
        password: str | None,
    ) -> str:
        normalized_command = command_text.strip()
        if not requires_sudo:
            return normalized_command

        if normalized_command.startswith("sudo "):
            normalized_command = normalized_command[5:].strip()

        sudo_command = f'sudo -S -p "" {normalized_command}'
        if requires_tty and password:
            # Turn terminal echo off before sending the sudo password so it is not
            # reflected back into the PTY stream. The trap restores echo when the shell exits.
            return f"stty -echo; trap 'stty echo' EXIT; {sudo_command}"
        return sudo_command

    def _friendly_manual_error(
        self,
        stderr_text: str,
        requires_sudo: bool,
        requires_tty: bool,
    ) -> str | None:
        normalized = stderr_text.strip().lower()
        if not normalized:
            return None
        if "a terminal is required" in normalized or "you must have a tty" in normalized:
            return "sudo requires a PTY on the remote host."
        if "password is required" in normalized:
            return "sudo password is required for this command."
        if requires_sudo and "permission denied" in normalized:
            return "sudo permission denied."
        if requires_tty and "pty" in normalized:
            return "PTY allocation failed on the remote host."
        return None

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
        import paramiko

        client = _build_ssh_client(server)
        resolved_timeout = timeout_sec or self._timeout_sec
        connect_kwargs = _build_connect_kwargs(
            server=server,
            timeout_sec=resolved_timeout,
            password=password,
            key_passphrase=key_passphrase,
        )
        secret_values = tuple(value for value in (password, key_passphrase) if value)
        command_to_run = self._build_manual_command(
            command_text=command_text,
            requires_sudo=requires_sudo,
            requires_tty=requires_tty,
            password=password,
        )
        remote_command = f"{shell_type.value} -lc {shlex.quote(command_to_run)}"

        try:
            client.connect(**connect_kwargs)
            stdin, stdout, stderr = client.exec_command(
                remote_command,
                timeout=resolved_timeout,
                get_pty=requires_tty,
            )
            if requires_sudo and password:
                stdin.write(f"{password}\n")
                stdin.flush()
            try:
                stdin.channel.shutdown_write()
            except Exception:
                pass
            stdin.close()
            stdout_text = self._sanitize_secret_text(
                stdout.read().decode("utf-8", errors="replace"),
                secret_values=secret_values,
            )
            stderr_text = self._sanitize_secret_text(
                stderr.read().decode("utf-8", errors="replace"),
                secret_values=secret_values,
            )
            exit_code = stdout.channel.recv_exit_status()
            error_message = None
            if exit_code != 0:
                error_message = self._friendly_manual_error(
                    stderr_text=stderr_text,
                    requires_sudo=requires_sudo,
                    requires_tty=requires_tty,
                ) or stderr_text.strip() or "Remote command failed."
            return CommandExecutionResult(
                stdout=stdout_text,
                stderr=stderr_text,
                exit_code=exit_code,
                error_message=error_message,
            )
        except FileNotFoundError:
            return CommandExecutionResult(
                stderr="Private key file was not found.",
                exit_code=255,
                error_message="Private key file was not found.",
            )
        except paramiko.AuthenticationException:
            return CommandExecutionResult(
                stderr="Authentication failed.",
                exit_code=255,
                error_message="Authentication failed.",
            )
        except paramiko.BadHostKeyException:
            return CommandExecutionResult(
                stderr="Host key verification failed.",
                exit_code=255,
                error_message="Host key verification failed.",
            )
        except (paramiko.SSHException, OSError, socket.error) as exc:
            message = str(exc)
            if requires_tty and "pty" in message.lower():
                message = "PTY allocation failed on the remote host."
            return CommandExecutionResult(
                stderr=self._sanitize_secret_text(str(exc), secret_values=secret_values),
                exit_code=255,
                error_message=self._sanitize_secret_text(message, secret_values=secret_values),
            )
        finally:
            client.close()

    def execute_script(
        self,
        server: Server,
        script: Script,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> CommandExecutionResult:
        import paramiko

        client = _build_ssh_client(server)
        resolved_timeout = script.timeout_sec or self._timeout_sec
        connect_kwargs = _build_connect_kwargs(
            server=server,
            timeout_sec=resolved_timeout,
            password=password,
            key_passphrase=key_passphrase,
        )
        remote_command = f"{script.shell_type.value} -s"

        try:
            client.connect(**connect_kwargs)
            stdin, stdout, stderr = client.exec_command(remote_command, timeout=resolved_timeout)
            payload = script.content if script.content.endswith("\n") else f"{script.content}\n"
            stdin.write(payload)
            stdin.flush()
            try:
                stdin.channel.shutdown_write()
            except Exception:
                pass
            stdin.close()
            stdout_text = stdout.read().decode("utf-8", errors="replace")
            stderr_text = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
            return CommandExecutionResult(
                stdout=stdout_text,
                stderr=stderr_text,
                exit_code=exit_code,
            )
        except FileNotFoundError:
            return CommandExecutionResult(
                stderr="Private key file was not found.",
                exit_code=255,
                error_message="Private key file was not found.",
            )
        except paramiko.AuthenticationException:
            return CommandExecutionResult(
                stderr="Authentication failed.",
                exit_code=255,
                error_message="Authentication failed.",
            )
        except paramiko.BadHostKeyException:
            return CommandExecutionResult(
                stderr="Host key verification failed.",
                exit_code=255,
                error_message="Host key verification failed.",
            )
        except (paramiko.SSHException, OSError, socket.error) as exc:
            return CommandExecutionResult(
                stderr=str(exc),
                exit_code=255,
                error_message=str(exc),
            )
        finally:
            client.close()
