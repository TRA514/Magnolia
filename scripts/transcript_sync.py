"""Profile-driven transcript-feed entrypoint. Dispatches by provider.

Otter is supported now; Granola is a Phase-3 drop-in behind this same entrypoint.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402


def _run_otter(root=None):
    """Run the ported Otter sync against the LIVE profile.

    Contract note (Finding #1): otter_sync resolves its STATE_DIR/MEETINGS_DIR
    from the live profile at module-import time and does NOT honor a per-call
    ``root``. The ``root`` argument is accepted for signature symmetry with the
    rest of this module (and for test injection), but it is intentionally not
    threaded into the ported runner. This is safe under the single-install
    assumption (one install = one live profile). Re-plumbing otter_sync to
    accept ``root`` is deliberately out of scope to preserve the port.
    """
    # Lazy import: otter_sync pulls in heavy deps (otterai) at module load,
    # so we only import it when actually dispatching to the Otter provider.
    import otter_sync
    return otter_sync.main()  # ported entrypoint


def sync(root=None):
    # ``root`` selects the profile used to resolve the provider. Note that for
    # the Otter provider the ported runner operates on the LIVE profile and does
    # not thread ``root`` (single-install assumption — see _run_otter).
    provider = profile_lib.transcript_config(root)["provider"]
    if provider == "none":
        return {"status": "skipped", "provider": "none"}
    if provider == "otter":
        # Finding #3: this is a headless entrypoint (onboarding/cron). A failure
        # inside the real Otter sync must surface as a structured status rather
        # than crashing the caller.
        try:
            _run_otter(root)
        except Exception as e:  # narrow: Exception, not BaseException
            return {"status": "error", "provider": "otter", "error": str(e)}
        return {"status": "ok", "provider": "otter"}
    if provider == "granola":
        return {"status": "unsupported", "provider": "granola",
                "note": "Granola adapter lands in Phase 3"}
    return {"status": "unsupported", "provider": provider}


if __name__ == "__main__":
    print(sync())
