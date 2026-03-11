from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from admin_assistant.core.enums import RiskLevel


class IncidentCategory(StrEnum):
    SSH = "ssh"
    DISK = "disk"
    MEMORY = "memory"
    CPU = "cpu"
    SERVICE = "service"
    NETWORK = "network"
    GENERIC = "generic"


@dataclass(frozen=True, slots=True)
class IncidentRunbookStepTemplate:
    title: str
    command_text: str
    risk_level: RiskLevel = RiskLevel.SAFE
    requires_sudo: bool = False
    requires_tty: bool = False


@dataclass(frozen=True, slots=True)
class IncidentRunbookTemplate:
    category: IncidentCategory
    title: str
    summary: str
    keywords: tuple[str, ...]
    steps: tuple[IncidentRunbookStepTemplate, ...]


RUNBOOK_TEMPLATES: dict[IncidentCategory, IncidentRunbookTemplate] = {
    IncidentCategory.SSH: IncidentRunbookTemplate(
        category=IncidentCategory.SSH,
        title="SSH access diagnostics",
        summary="Focus on sshd health, SSH logs, and safe sshd configuration checks.",
        keywords=("ssh", "sshd", "login", "auth", "authorized_keys", "passwordauthentication", "pubkey", "port 22"),
        steps=(
            IncidentRunbookStepTemplate("Check sshd service status", "systemctl status sshd --no-pager"),
            IncidentRunbookStepTemplate("Review recent SSH logs", "journalctl -u sshd -n 50 --no-pager"),
            IncidentRunbookStepTemplate("Validate sshd configuration", "sshd -t", requires_sudo=True),
            IncidentRunbookStepTemplate(
                "Inspect sshd configuration file",
                "cat /etc/ssh/sshd_config",
            ),
        ),
    ),
    IncidentCategory.DISK: IncidentRunbookTemplate(
        category=IncidentCategory.DISK,
        title="Disk pressure diagnostics",
        summary="Check filesystem, inode pressure, and large common directories.",
        keywords=("disk", "storage", "filesystem", "full", "no space", "inode", "capacity", "out of space"),
        steps=(
            IncidentRunbookStepTemplate("Check filesystem usage", "df -h"),
            IncidentRunbookStepTemplate("Check inode usage", "df -i"),
            IncidentRunbookStepTemplate("Inspect large common temp and log directories", "du -sh /var/log /tmp /var/tmp"),
            IncidentRunbookStepTemplate("Review recent system errors", "journalctl -n 50 --no-pager"),
        ),
    ),
    IncidentCategory.MEMORY: IncidentRunbookTemplate(
        category=IncidentCategory.MEMORY,
        title="Memory pressure diagnostics",
        summary="Check memory pressure, top processes, and recent kernel/service errors.",
        keywords=("memory", "oom", "out of memory", "killed process", "swap", "ram"),
        steps=(
            IncidentRunbookStepTemplate("Check memory usage", "free -h"),
            IncidentRunbookStepTemplate("Review running processes", "ps aux"),
            IncidentRunbookStepTemplate("Inspect kernel memory info", "cat /proc/meminfo"),
            IncidentRunbookStepTemplate("Review recent system errors", "journalctl -n 50 --no-pager"),
        ),
    ),
    IncidentCategory.CPU: IncidentRunbookTemplate(
        category=IncidentCategory.CPU,
        title="CPU and load diagnostics",
        summary="Check load averages, top processes, and recent system errors.",
        keywords=("cpu", "load", "load average", "high load", "utilization", "usage spike"),
        steps=(
            IncidentRunbookStepTemplate("Check load average", "uptime"),
            IncidentRunbookStepTemplate("Review running processes", "ps aux"),
            IncidentRunbookStepTemplate("Inspect load metrics", "cat /proc/loadavg"),
            IncidentRunbookStepTemplate("Review recent system errors", "journalctl -n 50 --no-pager"),
        ),
    ),
    IncidentCategory.SERVICE: IncidentRunbookTemplate(
        category=IncidentCategory.SERVICE,
        title="Generic service diagnostics",
        summary="Inspect recent logs, running processes, ports, and general host state.",
        keywords=("service", "daemon", "unit", "failed to start", "crash", "nginx", "apache", "mysql", "postgres", "redis"),
        steps=(
            IncidentRunbookStepTemplate("Review recent system errors", "journalctl -n 50 --no-pager"),
            IncidentRunbookStepTemplate("Review running processes", "ps aux"),
            IncidentRunbookStepTemplate("Inspect listening ports", "ss -tulpn"),
            IncidentRunbookStepTemplate("Check host load", "uptime"),
        ),
    ),
    IncidentCategory.NETWORK: IncidentRunbookTemplate(
        category=IncidentCategory.NETWORK,
        title="Network diagnostics",
        summary="Inspect addresses, listening sockets, and recent system errors.",
        keywords=("network", "dns", "latency", "timeout", "unreachable", "packet", "connection refused", "port"),
        steps=(
            IncidentRunbookStepTemplate("Inspect network addresses", "ip addr"),
            IncidentRunbookStepTemplate("Inspect listening ports", "ss -tulpn"),
            IncidentRunbookStepTemplate("Review recent system errors", "journalctl -n 50 --no-pager"),
            IncidentRunbookStepTemplate("Check host identity", "hostname"),
        ),
    ),
    IncidentCategory.GENERIC: IncidentRunbookTemplate(
        category=IncidentCategory.GENERIC,
        title="Generic host diagnostics",
        summary="Capture general system health across CPU, memory, disk, and sockets.",
        keywords=(),
        steps=(
            IncidentRunbookStepTemplate("Check host load", "uptime"),
            IncidentRunbookStepTemplate("Check memory usage", "free -h"),
            IncidentRunbookStepTemplate("Check filesystem usage", "df -h"),
            IncidentRunbookStepTemplate("Review running processes", "ps aux"),
            IncidentRunbookStepTemplate("Inspect listening ports", "ss -tulpn"),
            IncidentRunbookStepTemplate("Review recent system errors", "journalctl -n 50 --no-pager"),
        ),
    ),
}

_CATEGORY_PRIORITY: tuple[IncidentCategory, ...] = (
    IncidentCategory.SSH,
    IncidentCategory.DISK,
    IncidentCategory.MEMORY,
    IncidentCategory.CPU,
    IncidentCategory.SERVICE,
    IncidentCategory.NETWORK,
    IncidentCategory.GENERIC,
)


def infer_incident_category(symptom: str) -> IncidentCategory:
    normalized = symptom.lower()
    best_category = IncidentCategory.GENERIC
    best_score = 0
    for category in _CATEGORY_PRIORITY:
        template = RUNBOOK_TEMPLATES[category]
        score = sum(1 for keyword in template.keywords if keyword in normalized)
        if score > best_score:
            best_category = category
            best_score = score
    return best_category


def get_runbook_template(category: IncidentCategory) -> IncidentRunbookTemplate:
    return RUNBOOK_TEMPLATES[category]
