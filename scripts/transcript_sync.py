"""Profile-driven transcript-feed entrypoint. Dispatches by provider.

Otter is supported now; Granola is a Phase-3 drop-in behind this same entrypoint.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402


def _run_otter(root=None):
    # Lazy import: otter_sync pulls in heavy deps (otterai) at module load,
    # so we only import it when actually dispatching to the Otter provider.
    import otter_sync
    return otter_sync.main()  # ported entrypoint


def sync(root=None):
    provider = profile_lib.transcript_config(root)["provider"]
    if provider == "none":
        return {"status": "skipped", "provider": "none"}
    if provider == "otter":
        _run_otter(root)
        return {"status": "ok", "provider": "otter"}
    if provider == "granola":
        return {"status": "unsupported", "provider": "granola",
                "note": "Granola adapter lands in Phase 3"}
    return {"status": "unsupported", "provider": provider}


if __name__ == "__main__":
    print(sync())
