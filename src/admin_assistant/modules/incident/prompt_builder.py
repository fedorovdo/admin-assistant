from __future__ import annotations

from admin_assistant.core.enums import AnalysisLanguage
from admin_assistant.modules.incident.runbooks import IncidentCategory, IncidentRunbookTemplate


class IncidentPromptBuilder:
    def build_investigation_plan(
        self,
        *,
        title: str,
        symptom: str,
        server_count: int,
        category: IncidentCategory,
        template: IncidentRunbookTemplate,
        analysis_language: AnalysisLanguage,
    ) -> str:
        raise NotImplementedError


class DefaultIncidentPromptBuilder(IncidentPromptBuilder):
    def build_investigation_plan(
        self,
        *,
        title: str,
        symptom: str,
        server_count: int,
        category: IncidentCategory,
        template: IncidentRunbookTemplate,
        analysis_language: AnalysisLanguage,
    ) -> str:
        language_instruction = self._language_instruction(analysis_language)
        template_lines = "\n".join(
            (
                f"- {step.title} | command_text={step.command_text} | "
                f"risk_level={step.risk_level.value} | requires_sudo={str(step.requires_sudo).lower()} | "
                f"requires_tty={str(step.requires_tty).lower()}"
            )
            for step in template.steps
        )
        return (
            "You are helping investigate a live Linux incident for a system administrator.\n"
            "Return structured JSON only.\n"
            "Create a short, safe diagnostic investigation plan that can be auto-run non-interactively over SSH.\n"
            "This is Incident Mode. Auto-runnable steps must be diagnostic, finite, and read-only.\n"
            f"{language_instruction}\n"
            "Use these response fields:\n"
            "- summary: short explanation of the investigation goal\n"
            "- probable_causes: short initial hypotheses, or [] if too early\n"
            "- evidence: [] for the planning stage\n"
            "- next_steps: [] for the planning stage unless a human should check something manually\n"
            "- suggested_actions: [] for the planning stage\n"
            "- fix_plan_title: a short title for the investigation plan\n"
            "- fix_plan_summary: a short explanation of what the plan will check\n"
            "- fix_steps: ordered diagnostic steps with title, command_text, target_scope, risk_level, requires_sudo, requires_tty\n"
            "- Always include evidence, suggested_actions, fix_plan_title, fix_plan_summary, and fix_steps in the JSON output.\n"
            "- fix_steps are the only commands that Incident Mode may auto-run.\n"
            "- target_scope is a machine-readable internal field and must be exactly 'all' for every fix step in this Incident Mode plan.\n"
            "- command_text must remain in shell form and must not be translated.\n"
            "- risk_level must stay as the machine-readable enum values safe, warning, or danger.\n"
            "- requires_sudo and requires_tty must stay as machine-readable booleans.\n"
            "- Do not include remediation commands or configuration-changing commands in fix_steps.\n"
            "- Do not include commands that edit files, restart services, reload services, remove files, install packages, or change permissions.\n"
            "- Do not include interactive, continuous, or long-running commands.\n"
            "- Do not include nested ssh, scp, or sftp commands.\n"
            "- Do not include shell pipelines, command chains, redirects, subshells, or shell prompts.\n"
            "- Prefer finite read-only diagnostics such as: uptime, free -h, df -h, ps aux, ss -tulpn, hostname, uname -a, ip addr, journalctl -n 50 --no-pager, systemctl status <service> --no-pager, cat /etc/ssh/sshd_config, grep -E '^(PasswordAuthentication|PermitRootLogin|PubkeyAuthentication)' /etc/ssh/sshd_config, sshd -t.\n"
            "- If remediation is needed, put it in next_steps as manual human-reviewed guidance, not as auto-runnable fix_steps.\n\n"
            f"Incident title: {title}\n"
            f"Incident symptom: {symptom}\n"
            f"Selected target count: {server_count}\n"
            f"Likely incident category: {category.value}\n"
            f"Preferred baseline runbook: {template.title}\n"
            f"Baseline summary: {template.summary}\n"
            "Use the following built-in safe runbook as the preferred baseline unless the symptom strongly requires a different safe diagnostic sequence:\n"
            f"{template_lines}\n"
            "Stay close to this baseline when possible. You may reorder or slightly refine the baseline, but keep the plan finite, read-only, and concrete.\n"
        )

    def _language_instruction(self, analysis_language: AnalysisLanguage) -> str:
        if analysis_language is AnalysisLanguage.RU:
            return (
                "Human-readable text such as summary, probable_causes, next_steps, fix_plan_title, fix_plan_summary, and fix_step titles should be in Russian with simple beginner-friendly explanations. "
                "Machine-readable fields such as command_text, target_scope, risk_level, requires_sudo, and requires_tty must not be translated."
            )
        return (
            "Human-readable text such as summary, probable_causes, next_steps, fix_plan_title, fix_plan_summary, and fix_step titles should be in English with simple beginner-friendly explanations. "
            "Machine-readable fields such as command_text, target_scope, risk_level, requires_sudo, and requires_tty must not be translated."
        )
