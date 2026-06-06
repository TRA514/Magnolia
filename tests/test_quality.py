def test_build_quality_agreement_from_frontmatter(tasks_root):
    import task_server, task_lib, ladder_lib
    # judge says good (9), human agrees (up) -> agree
    a, _ = task_lib.create_task("a", queue="agent", task_type="prd-draft")
    task_lib.update_task(a, changes={"judge_score": 9, "judge_kind": "document",
                                     "judge_scored_at": "2026-06-01T00:00:00Z",
                                     "human_react": "up"})
    # judge says good (8), human disagrees (down) -> disagreement
    b, _ = task_lib.create_task("b", queue="agent", task_type="prd-draft")
    task_lib.update_task(b, changes={"judge_score": 8, "judge_kind": "document",
                                     "judge_scored_at": "2026-06-02T00:00:00Z",
                                     "human_react": "down", "human_react_note": "tone"})
    result = task_server.build_quality(ladder_path=None)
    grp = next(g for g in result["groups"] if g["task_type"] == "prd-draft")
    assert grp["count"] == 2
    assert grp["agreement_pct"] == 50
    assert any(d["task_id"] == b for d in result["disagreements"])


def test_build_quality_tier_label_from_ladder(tasks_root, tmp_path):
    import task_server, task_lib, ladder_lib
    p = str(tmp_path / "ladder.json")
    ladder_lib.set_tier("prd-draft", "gated", path=p)
    a, _ = task_lib.create_task("a", queue="agent", task_type="prd-draft")
    task_lib.update_task(a, changes={"judge_score": 9, "judge_kind": "document"})
    result = task_server.build_quality(ladder_path=p)
    grp = next(g for g in result["groups"] if g["task_type"] == "prd-draft")
    assert grp["phase"] == "gated"
