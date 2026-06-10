"""Task 5 — stamp publish-ticket task_type on Jira drafts at completion.

A Jira draft is title-pattern-routed and carries no task_type. At agent
completion we stamp task_type="publish-ticket" so the trust ladder, judge,
and Quality tab all key on a single clean action type — but only when the
task has no explicit type already (never overwrite an explicit one)."""
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _no_judge(monkeypatch):
    """Keep completion hermetic — never spawn the real judge subprocess."""
    import task_cli
    monkeypatch.setattr(task_cli, "_spawn_judge", lambda *a, **k: None)


def _complete(tid):
    import task_cli
    task_cli.cmd_agent_complete(SimpleNamespace(task_id=tid, output=None))


def test_jira_draft_gets_publish_ticket_stamp(tasks_root):
    import task_lib
    tid, _ = task_lib.create_task(
        "draft a ticket", queue="agent", domain="ops", creator="agent",
        description="<!-- JIRA_DRAFT -->\nSome ticket body.")
    _complete(tid)
    assert task_lib.read_task(tid)["frontmatter"].get("task_type") == "publish-ticket"


def test_existing_task_type_is_not_overwritten(tasks_root):
    import task_lib
    tid, _ = task_lib.create_task(
        "send a draft", queue="agent", domain="ops", creator="agent",
        task_type="send-message",
        description="<!-- JIRA_DRAFT -->\nSome ticket body.")
    _complete(tid)
    assert task_lib.read_task(tid)["frontmatter"].get("task_type") == "send-message"


def test_no_marker_leaves_task_type_unset(tasks_root):
    import task_lib
    tid, _ = task_lib.create_task(
        "plain task", queue="agent", domain="ops", creator="agent",
        description="Just a normal task, no draft marker.")
    _complete(tid)
    assert task_lib.read_task(tid)["frontmatter"].get("task_type") in (None, "")
