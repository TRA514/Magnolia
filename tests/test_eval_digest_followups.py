import json


def _seed(task_lib, **fm):
    tid, fp = task_lib.create_task(fm.pop("title", "t"), queue=fm.pop("queue", "agent"),
                                   domain=fm.pop("domain", "product"),
                                   task_type=fm.pop("task_type", None))
    if fm:
        task_lib.update_task(tid, changes=fm)
    return tid


def _user_chat(text, post_run):
    return {"role": "user", "kind": "text", "text": text,
            "run_id": 1, "origin": "chat", "post_run": post_run}


def test_digest_surfaces_post_run_follow_ups(tasks_root, tmp_path):
    import task_lib, eval_digest, chat_transcript

    # Task A: two post-run follow-ups → counted.
    a = _seed(task_lib, title="prd needs more", task_type="prd-draft")
    chat_transcript.append_event(a, _user_chat("can you add the metrics section?", True))
    chat_transcript.append_event(a, _user_chat("also clarify the success criteria", True))

    # Task B: only a pre-run chat turn → NOT counted.
    b = _seed(task_lib, title="message", task_type="send-message")
    chat_transcript.append_event(b, _user_chat("kick this off", False))

    # Task C: no transcript at all → must not crash.
    _seed(task_lib, title="no chat", task_type="other")

    out = tmp_path / "out"
    payload = eval_digest.build_digest(all_history=True, out_dir=str(out))

    fu = payload["follow_ups"]
    assert fu["total"] == 2
    assert fu["tasks_with_follow_ups"] == 1
    assert "prd-draft" in fu["by_group"]
    assert fu["by_group"]["prd-draft"]["count"] == 2
    assert len(fu["by_group"]["prd-draft"]["samples"]) <= 3
    assert payload["totals"]["follow_ups"] == 2

    # Status is "ok" even with no judge/human negatives present.
    assert payload["status"] == "ok"

    assert "Post-run chat follow-ups" in (out / "digest.md").read_text()


def test_digest_clean_when_no_followups_and_no_flagged(tasks_root, tmp_path):
    import task_lib, eval_digest
    _seed(task_lib, title="great", judge_score=9, judge_kind="document")
    payload = eval_digest.build_digest(all_history=True, out_dir=str(tmp_path / "o"))
    assert payload["status"] == "clean"
    assert payload["follow_ups"]["total"] == 0
    assert payload["totals"]["follow_ups"] == 0
