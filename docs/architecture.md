# Architecture Overview

Admin Assistant uses a modular monolith architecture. The goal is to keep the desktop application simple to ship while still separating major concerns cleanly.

## Core Stack

- Python
- PySide6
- Paramiko
- SQLite
- SQLAlchemy
- Pydantic
- httpx
- keyring
- PyInstaller

## Main Architectural Layers

### UI Layer

The PySide6 UI is responsible for:

- collecting user input
- rendering server, script, execution, AI, and history views
- forwarding actions into services
- reacting to execution and analysis events

Main UI areas:

- left sidebar: servers and scripts
- center panel: execution and history
- right panel: AI analysis and action workflow

### Application / Service Layer

Services coordinate the main workflows:

- server CRUD and connection testing
- script CRUD
- execution orchestration
- AI analysis and suggested action workflow
- history queries
- settings management
- Incident Mode orchestration

### Infrastructure Layer

Infrastructure adapters handle:

- SQLite persistence
- SSH via Paramiko
- AI provider HTTP calls
- secret storage via keyring
- platform-specific file paths

## Execution Model

Execution currently supports:

- manual commands
- saved scripts
- one or multiple servers
- background execution
- sudo and PTY where needed

Persisted execution data includes:

- run records
- per-target result records
- output chunks

The console uses:

- an `All Hosts` aggregate view
- one per-host tab

## AI Model

AI analysis is layered on top of saved execution output.

Current provider support:

- OpenAI
- Ollama
- OpenAI-compatible

AI responses can include:

- summary
- probable causes
- evidence
- next steps
- suggested actions
- fix plan

Machine-readable execution fields are intentionally kept stable and non-localized:

- `command_text`
- `target_scope`
- `risk_level`
- `requires_sudo`
- `requires_tty`

## Suggested Actions and Fix Plans

Admin Assistant separates analysis from execution:

- the AI may suggest actions
- users approve or reject them
- approved steps can be executed individually
- there is no “Execute Entire Plan” flow in the current design

This keeps remediation safer and easier to review.

## Incident Mode

Incident Mode is a lightweight orchestration layer that:

1. accepts a user symptom
2. classifies the incident
3. uses built-in safe runbook templates plus AI planning
4. filters to finite read-only diagnostics
5. runs safe investigation commands through the normal execution engine
6. sends collected evidence through the AI analysis flow

Incident sessions are currently in-memory for the MVP.

## Safety Model

Important design principles:

- secrets are not stored in plaintext in SQLite
- AI-generated commands are filtered before persistence or execution
- long-running and interactive commands are blocked for auto-generated steps
- nested SSH commands are blocked
- risky SSH configuration changes and restart/reload actions are blocked from AI auto-generated execution paths
- remediation still requires explicit approval

## Packaging

Windows packaging currently uses:

- PyInstaller for the application bundle
- Inno Setup for the installer

Writable runtime data is stored under:

```text
%LOCALAPPDATA%\AdminAssistant
```

This includes:

- the SQLite database
- application logs
