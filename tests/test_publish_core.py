import pytest


@pytest.fixture
def srv(tasks_root, profile_root, monkeypatch):
    """task_server with task_lib pointed at the temp task tree and profile at profile_root."""
    import task_server, profile_lib

    def _wrap(orig):
        def wrapper(*a, **k):
            # Only inject root when the caller hasn't already supplied it
            # (these fns take root as the 2nd positional arg).
            if len(a) < 2 and "root" not in k:
                k = {**k, "root": profile_root}
            return orig(*a, **k)
        return wrapper

    for fn in ("provider", "integration"):
        monkeypatch.setattr(profile_lib, fn, _wrap(getattr(profile_lib, fn)))
    return task_server


def test_attempt_publish_needs_confirm_when_unconfirmed(srv, monkeypatch):
    import adapters
    monkeypatch.setattr(adapters, "publish",
                        lambda *a, **k: (_ for _ in ()).throw(adapters.NeedsConfirmation("project_management")))
    status, payload = srv._attempt_publish("TASK-0001", {"summary": "x"})
    assert status == "needs_confirm"


def test_attempt_publish_ok_records_and_returns_keypair(srv, monkeypatch):
    import adapters, task_lib
    monkeypatch.setattr(adapters, "publish", lambda *a, **k: ("ACM-9", "https://x/ACM-9"))
    tid, _ = task_lib.create_task("draft", queue="human", domain="ops", creator="agent")
    status, payload = srv._attempt_publish(tid, {"summary": "x"})
    assert status == "ok" and payload == ("ACM-9", "https://x/ACM-9")


def test_attempt_publish_skips_when_task_already_done(srv, monkeypatch):
    import adapters, task_lib
    calls = []
    monkeypatch.setattr(adapters, "publish", lambda *a, **k: calls.append(1) or ("ACM-1", "u"))
    tid, _ = task_lib.create_task("draft", queue="human", domain="ops", creator="agent")
    task_lib.complete_task(tid, actor="system")        # already published once
    status, payload = srv._attempt_publish(tid, {"summary": "x"})
    assert status == "already_published"
    assert calls == []                                 # NO duplicate external write


def test_emit_confirm_card_lands_on_collab_with_links(srv):
    import task_lib
    cid = srv._emit_confirm_card("project_management", "TASK-0042")
    card = task_lib.read_task(cid)
    fm = card["frontmatter"]
    assert fm["card_type"] == "confirm"
    assert fm["queue"] == "collab"
    assert fm["confirm_family"] == "project_management"
    assert fm["confirm_source_task"] == "TASK-0042"
