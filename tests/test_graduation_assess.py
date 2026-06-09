def _judged(task_lib, task_type, score, react=None, n=1, when="2026-06-01T00:00:00Z"):
    ids = []
    for _ in range(n):
        tid, _fp = task_lib.create_task("t", queue="agent", task_type=task_type)
        ch = {"judge_score": score, "judge_kind": "document", "judge_scored_at": when}
        if react:
            ch["human_react"] = react
        task_lib.update_task(tid, changes=ch)
        ids.append(tid)
    return ids


def test_user_chat_turns_counts_only_user_events(tasks_root):
    import task_lib, graduation_assess, chat_transcript
    tid, _ = task_lib.create_task("t", queue="agent", task_type="prd-draft")
    assert graduation_assess.user_chat_turns(tid) == 0  # no transcript yet
    chat_transcript.append_event(tid, {"role": "user", "kind": "msg", "text": "hi"})
    chat_transcript.append_event(tid, {"role": "assistant", "kind": "msg", "text": "ok"})
    chat_transcript.append_event(tid, {"role": "user", "kind": "msg", "text": "tweak it"})
    assert graduation_assess.user_chat_turns(tid) == 2


def test_effective_react_explicit_wins(tasks_root):
    import graduation_assess as g
    assert g.effective_react({"id": "X", "human_react": "down", "status": "done"}) == "down"
    assert g.effective_react({"id": "X", "human_react": "up", "status": "open"}) == "up"


def test_effective_react_implicit_up_on_clean_accept(tasks_root):
    import task_lib, graduation_assess as g
    tid, _ = task_lib.create_task("t", queue="agent", task_type="prd-draft")
    # done + zero chat turns -> implicit up
    assert g.effective_react({"id": tid, "status": "done"}) == "up"


def test_effective_react_none_when_open_or_high_friction(tasks_root):
    import task_lib, graduation_assess as g, chat_transcript
    tid, _ = task_lib.create_task("t", queue="agent", task_type="prd-draft")
    assert g.effective_react({"id": tid, "status": "open"}) is None   # not accepted
    for _ in range(2):
        chat_transcript.append_event(tid, {"role": "user", "kind": "msg", "text": "redo"})
    assert g.effective_react({"id": tid, "status": "done"}) is None    # 2 turns > FRICTION_MAX


def test_ready_type_gets_graduation_card(tasks_root, tmp_path):
    import task_lib, graduation_assess, ladder_lib
    p = str(tmp_path / "ladder.json")
    _judged(task_lib, "prd-draft", 9, react="up", n=8)  # >=6, 100% approval+agreement
    created = graduation_assess.assess(ladder_path=p, now_iso="2026-06-10T00:00:00Z")
    assert any(c["task_type"] == "prd-draft" and c["proposed_tier"] == "supervised" for c in created)
    cards = [t for t in task_lib.list_tasks() if t.get("card_type") == "graduation"]
    assert len(cards) == 1
    assert cards[0].get("grad_proposed_tier") == "supervised"


def test_not_ready_no_card(tasks_root, tmp_path):
    import task_lib, graduation_assess
    p = str(tmp_path / "ladder.json")
    _judged(task_lib, "prd-draft", 9, react="up", n=3)  # below min_judged=6
    created = graduation_assess.assess(ladder_path=p, now_iso="2026-06-10T00:00:00Z")
    assert created == []


def test_idempotent_no_duplicate_card(tasks_root, tmp_path):
    import task_lib, graduation_assess
    p = str(tmp_path / "ladder.json")
    _judged(task_lib, "prd-draft", 9, react="up", n=8)
    graduation_assess.assess(ladder_path=p, now_iso="2026-06-10T00:00:00Z")
    graduation_assess.assess(ladder_path=p, now_iso="2026-06-11T00:00:00Z")
    cards = [t for t in task_lib.list_tasks() if t.get("card_type") == "graduation"]
    assert len(cards) == 1  # not re-carded


def test_auto_demote_after_consecutive_bad_windows(tasks_root, tmp_path):
    import task_lib, graduation_assess, ladder_lib
    p = str(tmp_path / "ladder.json")
    ladder_lib.set_tier("prd-draft", "supervised", path=p)
    _judged(task_lib, "prd-draft", 3, react="down", n=8)  # approval 0% << supervised entry bar
    graduation_assess.assess(ladder_path=p, now_iso="2026-06-10T00:00:00Z")
    assert ladder_lib.tier_of("prd-draft", path=p) == "supervised"   # 1st bad window: no demote yet
    graduation_assess.assess(ladder_path=p, now_iso="2026-06-17T00:00:00Z")
    assert ladder_lib.tier_of("prd-draft", path=p) == "shadow"  # 2nd consecutive: demoted


def test_no_demote_on_insufficient_data(tasks_root, tmp_path):
    import task_lib, graduation_assess, ladder_lib
    p = str(tmp_path / "ladder.json")
    ladder_lib.set_tier("prd-draft", "supervised", path=p)
    _judged(task_lib, "prd-draft", 3, react="down", n=2)  # n=2 < min_judged 6 for the supervised entry bar
    graduation_assess.assess(ladder_path=p, now_iso="2026-06-10T00:00:00Z")
    graduation_assess.assess(ladder_path=p, now_iso="2026-06-17T00:00:00Z")
    assert ladder_lib.tier_of("prd-draft", path=p) == "supervised"  # sparse window must NOT demote
