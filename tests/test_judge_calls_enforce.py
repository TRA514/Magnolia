import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import judge

def test_finalize_calls_post_judge(monkeypatch):
    calls = []
    monkeypatch.setattr(judge, "write_back", lambda tid, v, rv, k: True)
    monkeypatch.setattr(judge, "_post_judge", lambda tid, v: calls.append((tid, v)) or "park")
    judge._finalize("T-9", {"score": 8, "why": "ok", "dimensions": {}}, "rubric-v1", "message")
    assert calls and calls[0][0] == "T-9"

def test_finalize_swallows_enforcement_error(monkeypatch):
    monkeypatch.setattr(judge, "write_back", lambda tid, v, rv, k: True)
    def boom(tid, v): raise RuntimeError("boom")
    monkeypatch.setattr(judge, "_post_judge", boom)
    # must NOT raise — judge stays additive / exit 0
    result = judge._finalize("T-9", {"score": 8, "why": "ok", "dimensions": {}}, "rubric-v1", "message")
    # _finalize returns the write_back result even when enforcement raises
    assert result is True

def test_finalize_skips_enforcement_when_writeback_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(judge, "write_back", lambda tid, v, rv, k: False)
    monkeypatch.setattr(judge, "_post_judge", lambda tid, v: calls.append((tid, v)))
    result = judge._finalize("T-9", {"score": 8, "why": "ok", "dimensions": {}}, "rubric-v1", "message")
    # enforcement must NOT run when write-back fails, and _finalize returns False
    assert calls == []
    assert result is False

def test_post_judge_delegates_to_enforce_lib(monkeypatch):
    import enforce_lib
    seen = []
    monkeypatch.setattr(enforce_lib, "apply_post_judge", lambda tid, v: seen.append((tid, v)) or "park")
    judge._post_judge("T-1", {"score": 5, "why": "x"})
    assert seen and seen[0][0] == "T-1"
