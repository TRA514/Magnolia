import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import judge

def test_finalize_calls_post_judge(monkeypatch):
    calls = []
    monkeypatch.setattr(judge, "write_back", lambda tid, v, rv, k: True)
    monkeypatch.setattr(judge, "_post_judge", lambda tid, v: calls.append((tid, v)))
    judge._finalize("T-9", {"score": 8, "why": "ok", "dimensions": {}}, "rubric-v1", "message")
    assert calls and calls[0][0] == "T-9"

def test_finalize_swallows_enforcement_error(monkeypatch):
    monkeypatch.setattr(judge, "write_back", lambda tid, v, rv, k: True)
    def boom(tid, v): raise RuntimeError("boom")
    monkeypatch.setattr(judge, "_post_judge", boom)
    # must NOT raise — judge stays additive / exit 0
    judge._finalize("T-9", {"score": 8, "why": "ok", "dimensions": {}}, "rubric-v1", "message")

def test_post_judge_delegates_to_enforce_lib(monkeypatch):
    import enforce_lib
    seen = []
    monkeypatch.setattr(enforce_lib, "apply_post_judge", lambda tid, v: seen.append((tid, v)) or "park")
    judge._post_judge("T-1", {"score": 5, "why": "x"})
    assert seen and seen[0][0] == "T-1"
