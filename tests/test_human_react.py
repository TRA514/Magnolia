def test_react_writes_frontmatter(tasks_root):
    import task_lib
    tid, _ = task_lib.create_task("r", queue="agent", domain="ops")
    task_lib.react_to_task(tid, "up", note="looks great")
    fm = task_lib.read_task(tid)["frontmatter"]
    assert fm["human_react"] == "up"
    assert fm["human_react_note"] == "looks great"
    assert fm["human_reacted_at"]


def test_react_rejects_bad_value(tasks_root):
    import task_lib, pytest
    tid, _ = task_lib.create_task("r", queue="agent")
    with pytest.raises(ValueError):
        task_lib.react_to_task(tid, "sideways")


def test_react_overwrites(tasks_root):
    import task_lib
    tid, _ = task_lib.create_task("r", queue="agent")
    task_lib.react_to_task(tid, "down", note="off")
    task_lib.react_to_task(tid, "up")
    fm = task_lib.read_task(tid)["frontmatter"]
    assert fm["human_react"] == "up"
    assert fm.get("human_react_note") in (None, "")  # cleared on re-react without note


def test_react_on_archived_task(tasks_root):
    import task_lib
    tid, _ = task_lib.create_task("done one", queue="agent", domain="ops")
    task_lib.complete_task(tid)  # moves the task into _archive/
    task_lib.react_to_task(tid, "up", note="good after archive")
    fm = task_lib.read_task(tid)["frontmatter"]   # read_task is archive-aware
    assert fm["human_react"] == "up"
    assert fm["human_react_note"] == "good after archive"


def test_react_visible_in_list_projection(tasks_root):
    import task_lib
    tid, _ = task_lib.create_task("r", queue="agent")
    task_lib.react_to_task(tid, "up", note="ok")
    row = next(t for t in task_lib.list_tasks() if t["id"] == tid)
    assert row["human_react"] == "up"
    assert row["human_react_note"] == "ok"
