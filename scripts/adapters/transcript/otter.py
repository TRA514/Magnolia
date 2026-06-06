"""Otter transcript adapter.

NOTE (single-install): the ported otter_sync resolves STATE_DIR/MEETINGS_DIR from
the LIVE profile at import time and does not thread `root`. `root` is accepted for
signature symmetry / test injection only. Re-plumbing otter_sync is out of scope.

This adapter delegates to transcript_sync._run_otter so the existing
test_transcript_sync monkeypatch contract (which patches _run_otter) still holds.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def sync(root=None) -> dict:
    import transcript_sync  # late import to avoid cycle at module load
    try:
        transcript_sync._run_otter(root)
    except Exception as e:  # narrow: Exception, not BaseException
        return {"status": "error", "provider": "otter", "error": str(e)}
    return {"status": "ok", "provider": "otter"}
