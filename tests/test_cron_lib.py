import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import cron_lib  # noqa: E402


def test_auto_dispatch_uses_headless_env(monkeypatch):
    seen = {}
    monkeypatch.setattr(cron_lib.platform_lib, "headless_claude_env",
                        lambda: {"PATH": "SENTINEL"})

    def fake_popen(cmd, **k):
        seen["env"] = k.get("env")

        class P:
            pass

        return P()

    monkeypatch.setattr(cron_lib.subprocess, "Popen", fake_popen)
    cron_lib._auto_dispatch("TASK-9999")
    assert seen["env"]["PATH"] == "SENTINEL"  # no hand-rolled colon PATH
