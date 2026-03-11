from __future__ import annotations

from admin_assistant.app.bootstrap import AppConfig
from admin_assistant.core.enums import AuthType, HostKeyPolicy, RunKind, ShellType
from admin_assistant.modules.execution.dto import RunRequest
from admin_assistant.modules.servers.dto import ServerCreateRequest
from admin_assistant.version import ABOUT_TEXT, APP_NAME, APP_TITLE, __version__


def test_smoke_can_construct_core_dtos() -> None:
    server_request = ServerCreateRequest(
        name="web-01",
        host="192.0.2.10",
        username="root",
        auth_type=AuthType.PASSWORD,
        host_key_policy=HostKeyPolicy.MANUAL_APPROVE,
    )
    run_request = RunRequest(
        run_kind=RunKind.COMMAND,
        server_ids=("server-1",),
        command_text="uname -a",
        shell_type=ShellType.BASH,
    )
    config = AppConfig(database_url="sqlite+pysqlite:///:memory:")

    assert server_request.host == "192.0.2.10"
    assert run_request.command_text == "uname -a"
    assert config.database_url == "sqlite+pysqlite:///:memory:"
    assert APP_NAME == "Admin Assistant"
    assert APP_TITLE.endswith(__version__)
    assert "Author\nDmitrii Fedorov" in ABOUT_TEXT
    assert "Contact\nfedorovkingisepp@gmail.com" in ABOUT_TEXT
