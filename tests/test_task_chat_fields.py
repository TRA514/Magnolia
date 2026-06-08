import task_lib


def test_new_task_has_session_fields(tasks_root):
    tid, _ = task_lib.create_task("chat field probe", queue="agent")
    fm = task_lib.read_task(tid)["frontmatter"]
    assert fm["claude_session_id"] is None
    assert fm["session_origin"] is None
    assert fm["chat_last_active"] is None


def test_update_roundtrips_session_id(tasks_root):
    tid, _ = task_lib.create_task("rt", queue="agent")
    task_lib.update_task(tid, {"claude_session_id": "abc-123", "session_origin": "background_agent"})
    fm = task_lib.read_task(tid)["frontmatter"]
    assert fm["claude_session_id"] == "abc-123"
    assert fm["session_origin"] == "background_agent"
