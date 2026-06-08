"""Contract every messaging adapter must satisfy (legibility only)."""
from typing import Protocol


class NotConfigured(RuntimeError):
    """Raised when publish() is called but the provider/profile isn't set up."""


class MessagingAdapter(Protocol):
    def is_configured(self, root=None) -> bool: ...
    def publish(self, draft: dict, root=None) -> tuple: ...  # -> (message_id, url|None)
