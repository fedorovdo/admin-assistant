from __future__ import annotations

from admin_assistant.modules.incident.runbooks import IncidentCategory, get_runbook_template, infer_incident_category


def test_infer_incident_category_prefers_specific_keyword_matches() -> None:
    assert infer_incident_category("SSH login fails with auth errors") is IncidentCategory.SSH
    assert infer_incident_category("Disk is full and no space left on device") is IncidentCategory.DISK
    assert infer_incident_category("Memory pressure and OOM killer events") is IncidentCategory.MEMORY
    assert infer_incident_category("CPU load is very high") is IncidentCategory.CPU
    assert infer_incident_category("Packet loss and DNS timeout") is IncidentCategory.NETWORK


def test_infer_incident_category_falls_back_to_generic() -> None:
    assert infer_incident_category("Something looks strange but details are unclear") is IncidentCategory.GENERIC


def test_runbook_templates_expose_safe_step_baselines() -> None:
    ssh_template = get_runbook_template(IncidentCategory.SSH)
    assert ssh_template.category is IncidentCategory.SSH
    assert ssh_template.steps
    assert ssh_template.steps[0].command_text == "systemctl status sshd --no-pager"
