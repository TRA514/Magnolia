"""Wiring test — the shadow judge spawn must fire on EVERY agent:complete, not
only when --output is passed.

The trust-ladder enforcement chain is judge-driven: cmd_agent_complete →
_spawn_judge → judge.py → enforce_lib.apply_post_judge. The two action types the
epic governs (send-message, publish-ticket) complete WITHOUT an --output file
(the deliverable lives in the task body), so gating the spawn on `if args.output`
meant the judge never fired for them and enforcement never ran.

These tests spy the REAL subprocess spawn inside _spawn_judge (we do NOT stub
_spawn_judge itself — the whole point is to prove it runs). The spied Popen keeps
the test hermetic: no real detached judge process is launched; we assert on argv.
"""
from types import SimpleNamespace

import pytest


@pytest.fixture
def popen_spy(monkeypatch):
    """Record subprocess.Popen calls and prevent a real judge from spawning."""
    calls = []

    class _FakePopen:
        def __init__(self, argv, *a, **k):
            calls.append(argv)

    import task_cli
    monkeypatch.setattr(task_cli.subprocess, "Popen", _FakePopen)
    return calls


def _judge_spawns_for(calls):
    """True iff a recorded Popen argv invoked judge.py for some task id."""
    return [argv for argv in calls if any("judge.py" in str(a) for a in argv)]


def _complete(tid, output=None):
    import task_cli
    task_cli.cmd_agent_complete(SimpleNamespace(task_id=tid, output=output))


# ── Test A: send-message completes without --output → judge still spawns ──────

def test_send_message_complete_spawns_judge_without_output(tasks_root, popen_spy):
    import task_lib
    tid, _ = task_lib.create_task(
        "draft a Slack message", queue="agent", domain="ops", creator="agent",
        task_type="send-message",
        description="Tell the team standup is moved to 10am.")
    _complete(tid, output=None)
    spawns = _judge_spawns_for(popen_spy)
    assert spawns, "judge subprocess was not spawned for a send-message completion"
    argv = spawns[0]
    assert tid in argv, f"judge spawn argv {argv} did not target task {tid}"


# ── Test B: JIRA_DRAFT body, no task_type → publish-ticket stamp + judge spawn ─

def test_jira_draft_complete_stamps_and_spawns_judge(tasks_root, popen_spy):
    import task_lib
    tid, _ = task_lib.create_task(
        "draft a ticket", queue="agent", domain="ops", creator="agent",
        description="<!-- JIRA_DRAFT -->\nSome ticket body that needs filing.")
    _complete(tid, output=None)
    # (1) the publish-ticket stamp landed on the (now-real) completion path
    assert task_lib.read_task(tid)["frontmatter"].get("task_type") == "publish-ticket"
    # (2) the judge subprocess was spawned for it
    spawns = _judge_spawns_for(popen_spy)
    assert spawns, "judge subprocess was not spawned for a JIRA_DRAFT completion"
    assert tid in spawns[0]


# ── Test C: plain task, no output / marker / action type → judge STILL spawns ──
# Documents the chosen design: the spawn is unconditional and the judge self-skips
# cheaply (detect_kind→None returns before any LLM call) for non-gradeable work.

def test_plain_task_complete_still_spawns_judge(tasks_root, popen_spy):
    import task_lib
    tid, _ = task_lib.create_task(
        "plain task", queue="agent", domain="ops", creator="agent",
        description="Just a normal task, no draft marker, no output.")
    _complete(tid, output=None)
    assert _judge_spawns_for(popen_spy), (
        "judge spawn is unconditional; the judge self-skips for non-gradeable work")
