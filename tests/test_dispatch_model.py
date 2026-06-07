import task_dispatch


def test_resolve_task_model_uses_worker_tier(monkeypatch):
    monkeypatch.setattr("profile_lib.cost_posture", lambda root=None: "balanced")
    worker = {"name": "researcher", "tier": "deep"}
    assert task_dispatch._resolve_task_model({"id": "TASK-1"}, worker) == "claude-opus-4-8"


def test_resolve_task_model_task_override_wins(monkeypatch):
    monkeypatch.setattr("profile_lib.cost_posture", lambda root=None: "balanced")
    worker = {"name": "scheduler", "tier": "light"}
    task = {"id": "TASK-2", "model": "claude-opus-4-8"}
    assert task_dispatch._resolve_task_model(task, worker) == "claude-opus-4-8"


def test_resolve_task_model_tier_override_wins(monkeypatch):
    monkeypatch.setattr("profile_lib.cost_posture", lambda root=None: "balanced")
    worker = {"name": "scheduler", "tier": "light"}
    task = {"id": "TASK-3", "tier": "deep"}
    assert task_dispatch._resolve_task_model(task, worker) == "claude-opus-4-8"


def test_resolve_task_model_defaults_when_no_tier(monkeypatch):
    monkeypatch.setattr("profile_lib.cost_posture", lambda root=None: "balanced")
    assert task_dispatch._resolve_task_model({"id": "T"}, {"name": "x"}) == "claude-sonnet-4-6"


def test_resolve_task_model_handles_none_worker(monkeypatch):
    monkeypatch.setattr("profile_lib.cost_posture", lambda root=None: "balanced")
    assert task_dispatch._resolve_task_model({"id": "T"}, None) == "claude-sonnet-4-6"
