# Trust-ladder Passive Signal + First-Hop Tuning — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let the trust-ladder learn from clean human card-acceptance (passive signal), add a reaction-count floor to the agreement gate, drop the judge self-vote, and tune the first hop to graduate faster — so the ladder is well-balanced before beta.

**Architecture:** All changes are confined to three scripts and their tests. A pure `effective_react()` helper in `graduation_assess.py` derives an implicit "up" from a human-accepted (`status=="done"`) low-friction card; `_metrics()` is rewired to use it and to stop counting the judge's own score as an approval. `ladder_lib.py` gains a `min_reacted` threshold and a lower first-hop `min_judged`. `seed_default_crons.py` moves graduation assessment to twice-weekly. The ladder stays advisory (no autonomy is unlocked), so blast radius is zero.

**Tech Stack:** Python 3, pytest. No new dependencies. Reads existing task frontmatter (`human_react`, `status`, `judge_score`) and the sidecar chat transcript (`chat_transcript.read_events`).

**Design doc:** `docs/plans/2026-06-09-trust-ladder-passive-signal-design.md`

**Green gates (run before every commit):**
```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
```

---

### Task 1: `user_chat_turns` + `effective_react` helpers (pure, no behavior change yet)

**Files:**
- Modify: `scripts/graduation_assess.py` (add imports + two helpers near the top, after the existing imports)
- Test: `tests/test_graduation_assess.py`

**Step 1: Write the failing tests**

Add to `tests/test_graduation_assess.py`:

```python
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
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_graduation_assess.py -k "user_chat_turns or effective_react" -v`
Expected: FAIL (`AttributeError: module 'graduation_assess' has no attribute 'user_chat_turns'`)

**Step 3: Implement the helpers**

In `scripts/graduation_assess.py`, add `import chat_transcript` alongside the existing `import task_lib` / `import ladder_lib`, then add after the constants block (after `ENTRY_KEY = {...}`):

```python
FRICTION_MAX = 1  # a clean accept tolerates at most one follow-up chat turn


def user_chat_turns(task_id):
    """Count the operator's chat turns on a card (role == 'user' events)."""
    try:
        events = chat_transcript.read_events(task_id)
    except Exception:
        return 0
    return sum(1 for e in events if e.get("role") == "user")


def effective_react(t):
    """The operator's reaction to a task, explicit or passively inferred.

    Explicit 👍/👎 always wins. Otherwise a terminally *accepted* card
    (status 'done' is set only by a human action — Done / Send / Publish;
    agent:complete leaves status 'open') with at most FRICTION_MAX follow-up
    chat turns is read as an implicit 'up'. Never infers a 'down': abandonment
    and heavy iteration are too ambiguous to punish, so explicit 👎 stays the
    only hard negative. Returns 'up' | 'down' | None.
    """
    react = t.get("human_react")
    if react in ("up", "down"):
        return react
    if t.get("status") == "done" and user_chat_turns(t.get("id")) <= FRICTION_MAX:
        return "up"
    return None
```

**Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_graduation_assess.py -k "user_chat_turns or effective_react" -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add scripts/graduation_assess.py tests/test_graduation_assess.py
git commit -m "feat(trust-ladder): effective_react + user_chat_turns helpers"
```

---

### Task 2: Rewire `_metrics` to use `effective_react` (drops the judge self-vote, returns `reacted`)

**Files:**
- Modify: `scripts/graduation_assess.py` (`_metrics`, lines ~25-47, and its two call sites in `assess`)
- Test: `tests/test_graduation_assess.py`

**Step 1: Write the failing tests**

```python
def test_metrics_no_self_vote_in_approval(tasks_root):
    # A judged-good task with NO reaction and status open must NOT count as approval.
    import graduation_assess as g
    tasks = [{"id": "A", "judge_score": 9, "status": "open"},
             {"id": "B", "judge_score": 9, "status": "open"}]
    n, approval, agreement, reacted = g._metrics(tasks)
    assert n == 2
    assert approval == 0.0       # judge≥7 alone no longer approves
    assert reacted == 0

def test_metrics_counts_implicit_up(tasks_root):
    import graduation_assess as g
    tasks = [{"id": "A", "judge_score": 9, "status": "done"}]   # clean accept -> implicit up
    n, approval, agreement, reacted = g._metrics(tasks)
    assert approval == 1.0
    assert reacted == 1
    assert agreement == 1.0      # judge_pos == implicit up
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_graduation_assess.py -k "metrics" -v`
Expected: FAIL (`_metrics` returns a 3-tuple / approval counts self-vote)

**Step 3: Rewrite `_metrics` and its call sites**

Replace `_metrics` body with:

```python
def _metrics(tasks):
    """Return (n, approval_rate, agreement_rate, reacted) for judged tasks.

    Uses effective_react (explicit 👍/👎, else inferred from a clean accept).
    Approval = effective_react == 'up' (no judge self-vote). Agreement is over
    tasks with any (explicit or implicit) reaction. reacted is the denominator
    for the min_reacted floor.
    """
    n = len(tasks)
    if n == 0:
        return 0, 0.0, 0.0, 0
    approvals = 0
    agree = reacted = 0
    for t in tasks:
        try:
            score = float(t.get("judge_score"))
        except (TypeError, ValueError):
            score = None
        judge_pos = score is not None and score >= JUDGE_GOOD_THRESHOLD
        react = effective_react(t)
        if react == "up":
            approvals += 1
        if react in ("up", "down"):
            reacted += 1
            if (react == "up") == judge_pos:
                agree += 1
    approval_rate = approvals / n
    agreement_rate = (agree / reacted) if reacted else 0.0
    return n, approval_rate, agreement_rate, reacted
```

In `assess`, update both unpack sites (promotion uses it directly; demotion path) from
`n, approval, agreement = _metrics(tasks)` to `n, approval, agreement, reacted = _metrics(tasks)`.
(`reacted` is unused until Task 3 — that's fine, name it now to avoid a second edit.)

**Step 4: Run the FULL graduation suite (existing tests may rely on old semantics)**

Run: `python3 -m pytest tests/test_graduation_assess.py -v`
Expected: PASS. **If any pre-existing test fails**, it relied on the judge self-vote or the
3-tuple — inspect it: tests that asserted a no-reaction good-judge type graduates must add an
explicit `react="up"` or set `status="done"` to express real acceptance. Fix the test to match
the new (correct) semantics; do not revert the code. Re-run until green.

**Step 5: Commit**

```bash
git add scripts/graduation_assess.py tests/test_graduation_assess.py
git commit -m "feat(trust-ladder): metrics use effective_react, drop judge self-vote"
```

---

### Task 3: `min_reacted` threshold + promotion gate

**Files:**
- Modify: `scripts/ladder_lib.py` (`DEFAULT_THRESHOLDS`, lines ~21-26)
- Modify: `scripts/graduation_assess.py` (promotion `ready` check, ~line 82)
- Test: `tests/test_ladder_lib.py`, `tests/test_graduation_assess.py`

**Step 1: Write the failing tests**

In `tests/test_ladder_lib.py`:
```python
def test_thresholds_include_min_reacted(tmp_path):
    th = ladder_lib.thresholds(path=_ladder(tmp_path))
    assert th["shadow_to_supervised"]["min_reacted"] == 3
    assert th["supervised_to_autonomous"]["min_reacted"] == 6
```

In `tests/test_graduation_assess.py` — too few reactions blocks promotion even when judged
count is met (use the `_judged` helper, which sets `human_react`):
```python
def test_min_reacted_floor_blocks_promotion(tasks_root, tmp_path):
    import task_lib, graduation_assess
    p = str(tmp_path / "ladder.json")
    # 6 judged, but only 2 explicit reactions -> reacted(2) < min_reacted(3) -> no card.
    _judged(task_lib, "prd-draft", 9, react="up", n=2)
    _judged(task_lib, "prd-draft", 9, react=None, n=4)   # no reaction, status open -> not reacted
    created = graduation_assess.assess(ladder_path=p, now_iso="2026-06-10T00:00:00Z")
    assert created == []
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_ladder_lib.py -k min_reacted tests/test_graduation_assess.py -k min_reacted -v`
Expected: FAIL (KeyError / card still created)

**Step 3: Implement**

In `scripts/ladder_lib.py` `DEFAULT_THRESHOLDS`:
```python
    "shadow_to_supervised": {"min_judged": 4, "min_approval": 0.75, "min_agreement": 0.70, "min_reacted": 3},
    "supervised_to_autonomous": {"min_judged": 12, "min_approval": 0.85, "min_agreement": 0.80, "min_reacted": 6},
```
(Note: this also sets `min_judged: 4` for the first hop — Task 4 covers its test.)

In `scripts/graduation_assess.py`, the promotion `ready` check becomes:
```python
            ready = (n >= bar["min_judged"] and reacted >= bar["min_reacted"]
                     and approval >= bar["min_approval"] and agreement >= bar["min_agreement"])
```

**Step 4: Run to verify they pass**

Run: `python3 -m pytest tests/test_ladder_lib.py tests/test_graduation_assess.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/ladder_lib.py scripts/graduation_assess.py tests/test_ladder_lib.py tests/test_graduation_assess.py
git commit -m "feat(trust-ladder): min_reacted floor on the agreement gate"
```

---

### Task 4: First-hop `min_judged` 6 → 4

**Files:**
- Modify: `tests/test_ladder_lib.py` (update the existing `test_thresholds_have_moderate_defaults` assertion — the constant itself already changed in Task 3)

**Step 1: Update the existing threshold test**

In `test_thresholds_have_moderate_defaults`, change:
```python
    assert th["shadow_to_supervised"]["min_judged"] == 6
```
to:
```python
    assert th["shadow_to_supervised"]["min_judged"] == 4
```
(Leave the `supervised_to_autonomous`...`min_judged"] == 12` assertion as-is.)

**Step 2: Add a test that the first hop fires at 4**

In `tests/test_graduation_assess.py`:
```python
def test_first_hop_fires_at_four_judged(tasks_root, tmp_path):
    import task_lib, graduation_assess
    p = str(tmp_path / "ladder.json")
    _judged(task_lib, "prd-draft", 9, react="up", n=4)   # exactly min_judged=4, reacted=4>=3
    created = graduation_assess.assess(ladder_path=p, now_iso="2026-06-10T00:00:00Z")
    assert any(c["task_type"] == "prd-draft" for c in created)
```

**Step 3: Run to verify**

Run: `python3 -m pytest tests/test_ladder_lib.py tests/test_graduation_assess.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add tests/test_ladder_lib.py tests/test_graduation_assess.py
git commit -m "feat(trust-ladder): lower first-hop min_judged 6->4"
```

---

### Task 5: Twice-weekly graduation assessment

**Files:**
- Modify: `scripts/seed_default_crons.py` (the "Graduation ladder" default, ~lines 60-74)
- Test: `tests/test_seed_default_crons.py`

**Step 1: Write the failing test**

```python
def test_graduation_cron_is_twice_weekly(monkeypatch):
    import cron_lib as cl
    monkeypatch.setattr(cl, "list_jobs", lambda: [])
    monkeypatch.setattr(cl, "create_job", lambda **kw: kw)
    grad = next(d for d in seed_default_crons.DEFAULTS if d["name"] == "Graduation ladder")
    assert grad["cron_expr"] == "30 9 * * 1,4"   # Mon + Thu 09:30
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_seed_default_crons.py -k twice_weekly -v`
Expected: FAIL (`"30 9 * * 1" != "30 9 * * 1,4"`)

**Step 3: Implement**

In `scripts/seed_default_crons.py`, the "Graduation ladder" entry:
```python
        "cron_expr": "30 9 * * 1,4",  # Mon + Thu 09:30 (twice-weekly so the ladder shows up fast)
        "cron_human": "Every Monday and Thursday at 9:30am",
```

**Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_seed_default_crons.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/seed_default_crons.py tests/test_seed_default_crons.py
git commit -m "feat(trust-ladder): graduation assessment twice-weekly (Mon+Thu)"
```

---

### Task 6: Full green-gate sweep + e2e sanity

**Step 1: Run all gates**

```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
```
Expected: all pass; `card_schema.py` prints `registry.json OK`.

**Step 2: e2e sanity — run the real assessor against the live task store**

```bash
python3 scripts/graduation_assess.py --now 2026-06-09T00:00:00Z
```
Expected: exits 0, prints `[graduation_assess] created N graduation card(s): [...]` with no traceback. (N may be 0 — that is fine; we are checking it runs end-to-end against real data with the new logic.)

**Step 3: Confirm the cron seed is idempotent and shows the new schedule**

```bash
python3 -c "import sys; sys.path.insert(0,'scripts'); import seed_default_crons as s; print([(d['name'], d['cron_expr']) for d in s.DEFAULTS])"
```
Expected: `Graduation ladder` paired with `30 9 * * 1,4`.

No commit (verification only).
```
