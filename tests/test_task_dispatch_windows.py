import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import task_dispatch  # noqa: E402


def test_actionable_query_uses_python_not_bash(monkeypatch):
    captured = {}

    class R:
        returncode = 0
        stdout = "[]"

    def fake_run(cmd, **k):
        captured["cmd"] = cmd
        return R()

    monkeypatch.setattr(task_dispatch.subprocess, "run", fake_run)
    task_dispatch.get_actionable_tasks()
    assert captured["cmd"][0] == sys.executable
    assert captured["cmd"][1].endswith("task_cli.py")
    assert not any(str(c).endswith("task.sh") for c in captured["cmd"])
