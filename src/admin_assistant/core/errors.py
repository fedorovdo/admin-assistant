from __future__ import annotations


class AdminAssistantError(Exception):
    """Base application error."""


class ValidationError(AdminAssistantError):
    """Raised when user or service input is invalid."""


class NotFoundError(AdminAssistantError):
    """Raised when a requested record cannot be found."""


class ConflictError(AdminAssistantError):
    """Raised when a requested operation conflicts with existing state."""


class ExternalIntegrationError(AdminAssistantError):
    """Raised when an external dependency fails."""

