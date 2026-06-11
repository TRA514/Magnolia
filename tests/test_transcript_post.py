import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import transcript_post


def test_hook_env_delegates_to_platform_lib(monkeypatch):
    sentinel = {"PATH": "X", "FOO": "bar"}
    monkeypatch.setattr(transcript_post.platform_lib, "headless_claude_env", lambda: sentinel)
    assert transcript_post._hook_env() is sentinel


def test_qmd_skipped_when_absent(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(transcript_post.platform_lib, "resolve_tool", lambda n: None)
    monkeypatch.setattr(transcript_post.subprocess, "Popen",
                        lambda *a, **k: calls.append(a[0]))
    monkeypatch.setattr(transcript_post.profile_lib, "PM_OS_DIR", str(tmp_path))
    transcript_post._run_qmd_index(transcript_post._hook_env(),
                                   tmp_path / "logs", transcript_post._null_log())
    assert calls == []  # qmd absent -> no Popen


def test_run_downstream_classifies_and_fires_hooks(tmp_path, monkeypatch):
    monkeypatch.setattr(transcript_post.profile_lib, "PM_OS_DIR", str(tmp_path))
    txt = tmp_path / "2026-06-08_10-00_demo.txt"
    txt.write_text("hello", encoding="utf-8")
    state = {}
    calls = {"classify": 0, "popen": []}

    def fake_classify(path, speech_id=None, downloaded_state=None):
        calls["classify"] += 1
        return {"domain": "product/home", "final_path": str(txt)}

    monkeypatch.setattr(transcript_post, "_classify_fn", lambda: fake_classify)
    monkeypatch.setattr(transcript_post.subprocess, "Popen",
                        lambda *a, **k: calls["popen"].append(a[0]) or None)

    final = transcript_post.run_downstream(str(txt), "uuid-123", state, log=transcript_post._null_log())
    assert final == str(txt)
    assert state["uuid-123"]["domain"] == "product/home"
    assert calls["classify"] == 1
    assert len(calls["popen"]) == 2   # task-extract + qmd
    assert (tmp_path / "logs").is_dir()   # log dir created under tmp, not the repo


def test_run_downstream_classify_import_error_still_fires_hooks(tmp_path, monkeypatch):
    """openai missing: _classify_fn raises ImportError. Skip classification,
    fall back to str(txt_path), but STILL fire both hooks."""
    monkeypatch.setattr(transcript_post.profile_lib, "PM_OS_DIR", str(tmp_path))
    txt = tmp_path / "2026-06-08_10-00_demo.txt"
    txt.write_text("hello", encoding="utf-8")
    state = {}
    calls = {"popen": []}

    def boom():
        raise ImportError("No module named 'openai'")

    monkeypatch.setattr(transcript_post, "_classify_fn", boom)
    monkeypatch.setattr(transcript_post.subprocess, "Popen",
                        lambda *a, **k: calls["popen"].append(a[0]) or None)

    final = transcript_post.run_downstream(str(txt), "uuid-456", state, log=transcript_post._null_log())
    assert final == str(txt)
    assert "uuid-456" not in state   # never classified
    assert len(calls["popen"]) == 2   # task-extract + qmd still fire
    assert (tmp_path / "logs").is_dir()


def test_run_downstream_classify_raises_falls_back_and_fires_hooks(tmp_path, monkeypatch):
    """The classify function itself raises: final_path falls back to
    str(txt_path), exception is NOT propagated, both hooks still fire."""
    monkeypatch.setattr(transcript_post.profile_lib, "PM_OS_DIR", str(tmp_path))
    txt = tmp_path / "2026-06-08_10-00_demo.txt"
    txt.write_text("hello", encoding="utf-8")
    state = {}
    calls = {"classify": 0, "popen": []}

    def fake_classify(path, speech_id=None, downloaded_state=None):
        calls["classify"] += 1
        raise RuntimeError("classification blew up")

    monkeypatch.setattr(transcript_post, "_classify_fn", lambda: fake_classify)
    monkeypatch.setattr(transcript_post.subprocess, "Popen",
                        lambda *a, **k: calls["popen"].append(a[0]) or None)

    final = transcript_post.run_downstream(str(txt), "uuid-789", state, log=transcript_post._null_log())
    assert final == str(txt)        # fell back, no propagation
    assert calls["classify"] == 1
    assert len(calls["popen"]) == 2   # task-extract + qmd still fire
    assert (tmp_path / "logs").is_dir()
