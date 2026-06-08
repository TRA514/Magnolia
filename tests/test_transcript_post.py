import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import transcript_post


def test_run_downstream_classifies_and_fires_hooks(tmp_path, monkeypatch):
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
