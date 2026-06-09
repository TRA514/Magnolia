"""Task 10 — the receipt Undo must be honest for an auto-shipped action.

An autoship receipt (shipper._emit_autoship_receipt) reuses the `receipt` card
type, whose Undo would normally git-revert a local patch. But an auto-shipped
email/ticket cannot be reverted. So for a receipt with receipt_kind=="autoship",
undo_receipt must instead demote the action type to supervised (stop
auto-shipping) and mark the card done — NOT attempt a git revert.

State isolation mirrors test_enforcement_routes: ladder_lib helpers are
monkeypatched to a temp ladder.json (the undo branch calls kill_to_supervised
with NO path arg), and the tasks tree is the conftest `tasks_root` temp tree —
so the real repo ladder.json / tasks are never touched. The git-revert helper
(subprocess.run) is spied to prove the autoship branch returns before it.
"""
import pytest


@pytest.fixture
def srv(tasks_root, tmp_path, monkeypatch):
    """task_server with ladder_lib helpers pinned to a temp ladder.json (undo's
    autoship branch calls kill_to_supervised with no path), and a spy on
    subprocess.run inside task_server so we can assert git is / isn't invoked."""
    import task_server, ladder_lib, task_lib

    ladder_path = str(tmp_path / "ladder.json")

    def _wrap_path(orig):
        def wrapper(*a, **k):
            if "path" not in k:
                k = {**k, "path": ladder_path}
            return orig(*a, **k)
        return wrapper

    for fn in ("set_tier", "tier_of", "kill_to_supervised", "note_demotion_signal"):
        monkeypatch.setattr(ladder_lib, fn, _wrap_path(getattr(ladder_lib, fn)))

    git_calls = []
    real_run = task_server.subprocess.run

    def _spy_run(cmd, *a, **k):
        git_calls.append(cmd)
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(task_server.subprocess, "run", _spy_run)

    return task_server, ladder_lib, task_lib, ladder_path, git_calls


def _make_autoship_receipt(task_lib):
    cid, _ = task_lib.create_task(
        "Auto-shipped: send the renewal nudge", queue="collab", domain="ops",
        creator="agent", description="autoship receipt", card_type="receipt")
    task_lib.update_task(cid, changes={
        "receipt_kind": "autoship",
        "autoship_task_type": "send-message",
        "receipt_summary": "send the renewal nudge",
    })
    return cid


def test_undo_autoship_demotes_to_supervised(srv):
    task_server, ladder_lib, task_lib, _, git_calls = srv
    cid = _make_autoship_receipt(task_lib)
    ladder_lib.set_tier("send-message", "autonomous")

    task_server.undo_receipt(cid)

    # Demoted to supervised in the isolated ladder.
    assert ladder_lib.tier_of("send-message") == "supervised"
    # No git revert attempted.
    assert all("revert" not in c for c in git_calls), git_calls
    # Receipt archived/flagged done with an explanatory comment.
    fm = task_lib.read_task(cid)["frontmatter"]
    assert fm["status"] == "done"


def test_undo_autoship_no_git_revert(srv):
    task_server, ladder_lib, task_lib, _, git_calls = srv
    cid = _make_autoship_receipt(task_lib)
    ladder_lib.set_tier("send-message", "autonomous")

    task_server.undo_receipt(cid)

    # Specifically: the git-revert subprocess path was never reached.
    assert not any(
        isinstance(c, (list, tuple)) and "git" in c and "revert" in c
        for c in git_calls
    ), git_calls


def test_undo_non_autoship_takes_revert_path(srv):
    """A plain receipt (no receipt_kind) still hits the original revert path —
    proven by reaching the `revert_commit` ValueError when none is recorded."""
    task_server, ladder_lib, task_lib, _, git_calls = srv
    cid, _ = task_lib.create_task(
        "Applied: rename the thing", queue="human", domain="ops",
        creator="agent", description="plain receipt", card_type="receipt")
    # No receipt_kind, no revert_commit → original path raises before any git call.
    with pytest.raises(ValueError):
        task_server.undo_receipt(cid)
    assert all("revert" not in c for c in git_calls), git_calls
