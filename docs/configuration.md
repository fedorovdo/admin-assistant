# Configuration

This guide explains the main configuration tasks in Admin Assistant.

## AI Providers

Admin Assistant supports three provider types:

- OpenAI
- Ollama
- OpenAI-compatible

Only one provider configuration needs to be active as the default for typical use.

## OpenAI Configuration

Recommended values:

- Provider: `OpenAI`
- Base URL: `https://api.openai.com/v1`
- Model: `gpt-4o-mini`
- API key: required

Steps:

1. Open the AI panel.
2. Click `Configure AI Provider`.
3. Choose `OpenAI`.
4. Enter base URL, model, and API key.
5. Click `Test Connection`.
6. Save.

## Ollama Configuration

Recommended values:

- Provider: `Ollama`
- Base URL: `http://127.0.0.1:11434`
- Model: `qwen2.5:7b` or another installed local model
- API key: not required

Steps:

1. Start Ollama:

```powershell
ollama serve
```

2. Pull a model if needed:

```powershell
ollama pull qwen2.5:7b
```

3. In Admin Assistant, choose `Ollama`.
4. Enter the base URL and model.
5. Click `Test Connection`.
6. Save.

If the app reports an Ollama timeout, check:

- that Ollama is running locally
- that the base URL is correct
- that the selected model exists
- the app log file under `%LOCALAPPDATA%\AdminAssistant`

## OpenAI-Compatible Configuration

Use this option for providers that expose an OpenAI-style API.

Typical values:

- Provider: `OpenAI-compatible`
- Base URL: your provider base URL
- Model: provider-specific model name
- API key: usually required

Use `Test Connection` before saving.

## AI Explanation Language

The AI panel includes a language selector.

Currently supported:

- `English`
- `Russian`

This affects human-readable explanation fields such as:

- summary
- probable causes
- next steps
- suggested action titles

Machine-readable execution fields remain stable and are not localized.

## Server Configuration

When adding a server, you can configure:

- name
- host
- port
- username
- authentication type
- host key policy
- notes

Authentication options:

- password
- private key

Secrets are stored in the OS credential manager via `keyring`.

## Script Configuration

For the current MVP, scripts include:

- name
- description
- content
- shell type
- requires TTY
- timeout

Supported shell types:

- `bash`
- `sh`

## Privileged Execution

In the Execution area:

- `Run with sudo` runs the command through `sudo -S`
- `Allocate PTY` requests a terminal

Guidance:

- use `Run with sudo` only when needed
- for password-based SSH auth, the SSH password may also be used for sudo
- the password is not stored in plaintext in SQLite and is not supposed to appear in console output

## Logs and Diagnostics

Use:

- `Help -> System Info`
- `Copy Info`
- `Open Log Folder`

Important runtime locations:

- DB: `%LOCALAPPDATA%\AdminAssistant\admin_assistant.db`
- Log: `%LOCALAPPDATA%\AdminAssistant\admin_assistant.log`
