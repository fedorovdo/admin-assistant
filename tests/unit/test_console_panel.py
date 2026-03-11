from __future__ import annotations

import time
from concurrent.futures import Future
from threading import Event, Thread

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from admin_assistant.app.events import RunCompletedEvent, RunCreatedEvent
from admin_assistant.core.enums import RunStatus
from admin_assistant.modules.execution.dto import RunLaunchResult
from admin_assistant.ui.panels.console_panel import ConsolePanel


class DummyQtBridge(QObject):
    event_published = Signal(object)


class ThreadedTaskRunner:
    def submit(self, func, *args, **kwargs):
        future = Future()

        def runner() -> None:
            try:
                future.set_result(func(*args, **kwargs))
            except Exception as exc:  # pragma: no cover - helper path
                future.set_exception(exc)

        Thread(target=runner, daemon=True).start()
        return future


class BlockingExecutionService:
    def __init__(self, started: Event, release: Event) -> None:
        self.started = started
        self.release = release
        self.requests = []

    def start_run(self, request):
        self.requests.append(request)
        self.started.set()
        self.release.wait(timeout=2)
        return RunLaunchResult(run_id="run-1", status=RunStatus.SUCCEEDED)


def _get_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_console_panel_submits_run_in_background() -> None:
    app = _get_app()
    started = Event()
    release = Event()
    execution_service = BlockingExecutionService(started=started, release=release)
    bridge = DummyQtBridge()
    panel = ConsolePanel(
        execution_service=execution_service,
        history_service=object(),
        task_runner=ThreadedTaskRunner(),
        qt_bridge=bridge,
    )
    panel.set_selected_server_ids(("server-1",))
    panel.command_input.setText("sleep 5")
    app.processEvents()

    started_at = time.perf_counter()
    panel.run_button.click()
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.5
    assert started.wait(timeout=0.5)
    assert not panel.run_button.isEnabled()
    assert len(execution_service.requests) == 1

    release.set()
    bridge.event_published.emit(
        RunCreatedEvent(
            correlation_id="run-1",
            run_id="run-1",
            run_kind="command",
            server_ids=("server-1",),
            shell_type="bash",
            initiator="user",
        )
    )
    bridge.event_published.emit(
        RunCompletedEvent(
            correlation_id="run-1",
            run_id="run-1",
            status=RunStatus.SUCCEEDED.value,
            target_count=1,
            success_count=1,
            failure_count=0,
        )
    )
    app.processEvents()
    assert panel.run_button.isEnabled()


def test_console_panel_clarifies_external_ai_action_execution() -> None:
    app = _get_app()
    panel = ConsolePanel(
        execution_service=BlockingExecutionService(started=Event(), release=Event()),
        history_service=object(),
        task_runner=ThreadedTaskRunner(),
        qt_bridge=DummyQtBridge(),
    )

    panel.prepare_for_external_run()
    app.processEvents()

    console_text = panel.all_hosts_console.toPlainText()
    assert "[ACTION] Executing approved AI action via Execution panel" in console_text
    assert "This run is now managed by the main Execution panel." in console_text
    assert "[run][status] Starting approved AI action..." in console_text
    assert not panel.run_button.isEnabled()


def test_console_panel_holds_controls_for_incident_flow_until_explicit_completion() -> None:
    app = _get_app()
    bridge = DummyQtBridge()
    panel = ConsolePanel(
        execution_service=BlockingExecutionService(started=Event(), release=Event()),
        history_service=object(),
        task_runner=ThreadedTaskRunner(),
        qt_bridge=bridge,
    )
    panel.set_selected_server_ids(("server-1",))
    panel.prepare_for_external_run(
        "[incident][status] Starting Incident Mode...",
        action_line="[ACTION] Starting Incident Mode via Execution panel",
        info_line="[INFO] Incident Mode runs safe diagnostic commands through the main Execution panel.",
        hold_controls_until_complete=True,
    )

    bridge.event_published.emit(
        RunCreatedEvent(
            correlation_id="run-incident-1",
            run_id="run-incident-1",
            run_kind="command",
            server_ids=("server-1",),
            shell_type="bash",
            initiator="user",
        )
    )
    bridge.event_published.emit(
        RunCompletedEvent(
            correlation_id="run-incident-1",
            run_id="run-incident-1",
            status=RunStatus.SUCCEEDED.value,
            target_count=1,
            success_count=1,
            failure_count=0,
        )
    )
    app.processEvents()

    assert not panel.run_button.isEnabled()
    assert not panel.investigate_button.isEnabled()

    panel.complete_external_flow()
    app.processEvents()

    assert panel.investigate_button.isEnabled()
