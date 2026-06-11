import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import task_lib, otter_sync, doc_sync_watcher  # noqa: E402


def test_doc_sync_trigger_uses_sys_executable(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(task_lib.subprocess, "Popen",
                        lambda cmd, **k: seen.setdefault("cmd", cmd))
    task_lib._trigger_doc_sync(str(tmp_path / "a.md"))
    assert seen["cmd"][0] == sys.executable


def test_otter_notify_skips_without_osascript(monkeypatch):
    monkeypatch.setattr(otter_sync.shutil, "which", lambda n: None)
    called = []
    monkeypatch.setattr(otter_sync.subprocess, "run", lambda *a, **k: called.append(a))
    otter_sync.notify("t", "m")
    assert called == []


def test_otter_main_exits_cleanly_without_otterai(monkeypatch):
    import pytest
    monkeypatch.setattr(otter_sync, "OtterAI", None)
    with pytest.raises(SystemExit):
        otter_sync.main()


def test_fswatch_guard_disables_watch_without_fswatch(monkeypatch):
    monkeypatch.setattr(doc_sync_watcher.shutil, "which", lambda n: None)
    popened = []
    monkeypatch.setattr(doc_sync_watcher.subprocess, "Popen",
                        lambda *a, **k: popened.append(a))
    doc_sync_watcher.watch_local("/tmp/datasets")
    doc_sync_watcher.watch_remote("/tmp/remote")
    assert popened == []
