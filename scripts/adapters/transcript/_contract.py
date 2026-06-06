"""Contract every transcript adapter must satisfy (legibility only)."""
from typing import Protocol


class TranscriptAdapter(Protocol):
    # status in {ok, skipped, error, unsupported}
    def sync(self, root=None) -> dict: ...
