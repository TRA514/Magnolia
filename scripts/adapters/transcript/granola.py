"""Granola transcript adapter — documented drop-in stub.

The seam is wired (select provider "granola" in integrations.yaml). To make it
real, implement sync() to pull Granola transcripts into the profile's transcript
target dir, mirroring otter.py's contract (return {"status": "ok", ...}).
"""


def sync(root=None) -> dict:
    return {"status": "unsupported", "provider": "granola",
            "note": "Granola adapter is a wired stub — implement sync()"}
