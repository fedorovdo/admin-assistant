# Contributing

Thanks for your interest in Admin Assistant.

This project is being prepared for an open-source style first release. Contributions are welcome, especially around:

- bug fixes
- documentation improvements
- packaging polish
- usability improvements
- test coverage

## Development Setup

1. Clone the repository.
2. Create and activate a virtual environment.
3. Install dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

4. Run the app:

```powershell
$env:PYTHONPATH = "src"
python -m admin_assistant.main
```

5. Run tests:

```powershell
python -m pytest
```

## Contribution Guidelines

- Keep changes focused and easy to review.
- Prefer small, production-safe pull requests.
- Update documentation when behavior changes.
- Add or update tests where practical.
- Avoid committing secrets, private keys, or local environment files.

## Coding Notes

- The project uses a modular monolith structure.
- PySide6 is used for the desktop UI.
- SQLite stores active data and history.
- Keyring is used for secret storage references.
- AI-generated remediation must remain safety-reviewed.

## Reporting Bugs

When opening an issue, please include:

- app version
- operating system
- steps to reproduce
- expected behavior
- actual behavior
- log file if available
- System Info output if possible

## Security

If you discover a security-related issue, please avoid posting sensitive details publicly right away. Share the issue responsibly with enough detail to reproduce and assess impact.
