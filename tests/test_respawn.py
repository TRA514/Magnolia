import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import task_dispatch
import platform_lib


class _FakePopen:
    """Records the args/kwargs it was constructed with."""
    last = None

    def __init__(self, cmd, **kwargs):
        _FakePopen.last = (cmd, kwargs)
        self.cmd = cmd
        self.kwargs = kwargs


def test_respawn_builds_rerun_cmd(monkeypatch):
    monkeypatch.setattr(task_dispatch.subprocess, "Popen", _FakePopen)
    proc = task_dispatch.respawn("T-1")
    assert proc is not None
    cmd, kwargs = _FakePopen.last
    assert "--task" in cmd
    assert "T-1" in cmd
    assert "--rerun" in cmd


def test_respawn_no_rerun_flag(monkeypatch):
    monkeypatch.setattr(task_dispatch.subprocess, "Popen", _FakePopen)
    task_dispatch.respawn("T-2", rerun=False)
    cmd, _ = _FakePopen.last
    assert "--task" in cmd
    assert "T-2" in cmd
    assert "--rerun" not in cmd


def test_respawn_strips_claude_env(monkeypatch):
    captured = {}

    def _fake_popen(cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _FakePopen(cmd, **kwargs)

    monkeypatch.setenv("CLAUDE_CODE_HEADLESS", "true")
    monkeypatch.setenv("CMUX_CLAUDE_SESSION", "x")
    monkeypatch.setattr(task_dispatch.subprocess, "Popen", _fake_popen)
    task_dispatch.respawn("T-3")
    env = captured["env"]
    assert not any(k.startswith(("CLAUDE", "CMUX_CLAUDE")) for k in env)


def test_respawn_posix_path_prepended(monkeypatch):
    # OS-agnostic: only assert the POSIX bin dirs when not on Windows.
    if platform_lib.os_kind() == "windows":
        return
    captured = {}

    def _fake_popen(cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _FakePopen(cmd, **kwargs)

    monkeypatch.setattr(task_dispatch.subprocess, "Popen", _fake_popen)
    task_dispatch.respawn("T-4")
    assert "/opt/homebrew/bin" in captured["env"]["PATH"]


def test_respawn_returns_none_on_failure(monkeypatch):
    def _boom(cmd, **kwargs):
        raise OSError("nope")

    monkeypatch.setattr(task_dispatch.subprocess, "Popen", _boom)
    # Must not raise; returns None so callers can surface the failure.
    assert task_dispatch.respawn("T-5") is None
