from __future__ import annotations

from enum import StrEnum


class ShellType(StrEnum):
    BASH = "bash"
    SH = "sh"


class RiskLevel(StrEnum):
    SAFE = "safe"
    WARNING = "warning"
    DANGER = "danger"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


class HostKeyPolicy(StrEnum):
    STRICT = "strict"
    TRUST_ON_FIRST_USE = "trust_on_first_use"
    MANUAL_APPROVE = "manual_approve"


class AuthType(StrEnum):
    PASSWORD = "password"
    KEY = "key"


class RunKind(StrEnum):
    SCRIPT = "script"
    COMMAND = "command"
    AI_ACTION = "ai_action"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionMethod(StrEnum):
    INLINE_STDIN = "inline_stdin"
    TEMP_FILE = "temp_file"
    MANUAL_COMMAND = "manual_command"


class StreamType(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"


class AIAnalysisStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisLanguage(StrEnum):
    EN = "en"
    RU = "ru"
