def test_create_task_sets_card_type(tasks_root):
    import task_lib
    tid, _ = task_lib.create_task("rec", queue="collab", domain="ops",
                                  card_type="recommendation", patch_path="datasets/evals/x.patch")
    fm = task_lib.read_task(tid)["frontmatter"]
    assert fm["card_type"] == "recommendation"
    assert fm["patch_path"] == "datasets/evals/x.patch"


def test_create_task_defaults_card_type_none(tasks_root):
    import task_lib
    tid, _ = task_lib.create_task("plain", queue="human")
    fm = task_lib.read_task(tid)["frontmatter"]
    assert fm.get("card_type") in (None, "task")
