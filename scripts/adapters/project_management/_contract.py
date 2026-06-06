"""Contract every project-management adapter must satisfy (legibility only)."""
from typing import Protocol


class NotConfigured(RuntimeError):
    """Raised when publish() is called but the provider/profile isn't set up."""


class ProjectManagementAdapter(Protocol):
    def is_configured(self, root=None) -> bool: ...
    def publish(self, draft: dict, root=None) -> tuple: ...  # -> (issue_key, issue_url)
