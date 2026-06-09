import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import enforce_lib


def _setup(monkeypatch, *, tier, flag, action="send-message", revs=0):
    fm = {"task_type": action, "revision_count": revs, "id": "T-1", "status": "open"}
    state = {"revised": [], "shipped": []}
    monkeypatch.setattr(enforce_lib, "tier_of", lambda k, path=None: tier)
    monkeypatch.setattr(enforce_lib, "autonomy_enabled", lambda root=None: flag)
    monkeypatch.setattr(enforce_lib, "_read_fm", lambda tid: fm)
    monkeypatch.setattr(enforce_lib, "_trigger_revision", lambda tid, why, n: state["revised"].append(tid))
    monkeypatch.setattr(enforce_lib, "_autoship", lambda tid, at: (state["shipped"].append(tid), "shipped")[1])
    return state


def V(score):
    return {"score": score, "why": "because"}


def test_shadow_parks(monkeypatch):
    _setup(monkeypatch, tier="shadow", flag=True)
    assert enforce_lib.apply_post_judge("T-1", V(3)) == "park"


def test_supervised_below_bar_revises(monkeypatch):
    s = _setup(monkeypatch, tier="supervised", flag=True)
    assert enforce_lib.apply_post_judge("T-1", V(4)) == "revise"
    assert s["revised"] == ["T-1"]


def test_supervised_below_bar_exhausted_parks(monkeypatch):
    _setup(monkeypatch, tier="supervised", flag=True, revs=99)
    assert enforce_lib.apply_post_judge("T-1", V(4)) == "park"


def test_supervised_pass_parks_for_human(monkeypatch):
    _setup(monkeypatch, tier="supervised", flag=True)
    assert enforce_lib.apply_post_judge("T-1", V(9)) == "park"


def test_autonomous_pass_action_flag_on_ships(monkeypatch):
    s = _setup(monkeypatch, tier="autonomous", flag=True)
    assert enforce_lib.apply_post_judge("T-1", V(9)) == "shipped"
    assert s["shipped"] == ["T-1"]


def test_autonomous_pass_flag_off_parks(monkeypatch):
    _setup(monkeypatch, tier="autonomous", flag=False)
    assert enforce_lib.apply_post_judge("T-1", V(9)) == "park"


def test_autonomous_pass_artifact_hard_stop_parks(monkeypatch):
    _setup(monkeypatch, tier="autonomous", flag=True, action="prd")
    assert enforce_lib.apply_post_judge("T-1", V(9)) == "park"


def test_autonomous_below_bar_revises(monkeypatch):
    s = _setup(monkeypatch, tier="autonomous", flag=True)
    assert enforce_lib.apply_post_judge("T-1", V(4)) == "revise"
    assert s["revised"] == ["T-1"]


def test_no_score_parks(monkeypatch):
    _setup(monkeypatch, tier="autonomous", flag=True)
    assert enforce_lib.apply_post_judge("T-1", {"score": None, "why": ""}) == "park"
