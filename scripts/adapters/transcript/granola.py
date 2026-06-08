"""Granola transcript adapter.

Delegates to transcript_sync._run_granola so the headless structured-error
contract and its test monkeypatch hold (mirrors otter.py)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def sync(root=None) -> dict:
    import transcript_sync
    try:
        transcript_sync._run_granola(root)
    except Exception as e:
        return {"status": "error", "provider": "granola", "error": str(e)}
    return {"status": "ok", "provider": "granola"}
