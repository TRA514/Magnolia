import json
from pathlib import Path


def _seed(task_lib, **fm):
    tid, fp = task_lib.create_task(fm.pop("title", "t"), queue=fm.pop("queue", "agent"),
                                   domain=fm.pop("domain", "product"),
                                   task_type=fm.pop("task_type", None))
    task_lib.update_task(tid, changes=fm)
    return tid


def test_digest_flags_low_judge_score(tasks_root, tmp_path):
    import task_lib, eval_digest
    _seed(task_lib, title="bad prd", task_type="prd-draft",
          judge_score=3, judge_kind="document", judge_why="thin")
    _seed(task_lib, title="good prd", task_type="prd-draft",
          judge_score=9, judge_kind="document", judge_why="solid")
    out = tmp_path / "out"
    payload = eval_digest.build_digest(window_days=3650, out_dir=str(out))
    assert payload["totals"]["flagged_traces"] == 1
    assert "prd-draft" in payload["by_worker"]
    assert (out / "digest.json").exists() and (out / "digest.md").exists()


def test_digest_flags_human_down(tasks_root, tmp_path):
    import task_lib, eval_digest
    _seed(task_lib, title="ok score but disliked", task_type="message",
          judge_score=8, judge_kind="message", human_react="down",
          human_react_note="wrong tone")
    payload = eval_digest.build_digest(window_days=3650, out_dir=str(tmp_path / "o"))
    assert payload["totals"]["flagged_traces"] == 1
    assert "wrong tone" in json.dumps(payload["by_step"])


def test_digest_clean_when_no_negative(tasks_root, tmp_path):
    import task_lib, eval_digest
    _seed(task_lib, title="great", judge_score=9, judge_kind="document")
    payload = eval_digest.build_digest(window_days=3650, out_dir=str(tmp_path / "o"))
    assert payload["status"] == "clean"


def test_digest_clusters_by_step_kind(tasks_root, tmp_path):
    import task_lib, eval_digest
    _seed(task_lib, title="d", task_type="prd-draft", judge_score=4, judge_kind="document")
    _seed(task_lib, title="m", task_type="send-message", judge_score=4, judge_kind="message")
    payload = eval_digest.build_digest(window_days=3650, out_dir=str(tmp_path / "o"))
    assert set(payload["by_step"]) == {"document", "message"}
