# Phase 4 — Eval Substrate off Docker + In-Box Crons — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Each task: @superpowers:test-driven-development (RED → GREEN → commit) and @superpowers:verification-before-completion before any "done" claim.

**Goal:** Move LangFuse's four jobs to native zero-install homes (prompts→files+git, traces→Claude Code session JSONL, scores→task frontmatter, UI→Quality tab) and wire the two load-bearing in-box crons (weekly self-improvement, graduation ladder), lighting up the recommendation/receipt/graduation card types as minimal-functional.

**Architecture:** Rewire data sources from LangFuse → task frontmatter; fill in handlers/renderers stubbed inert in Phase 3. `judge.py` already writes `judge_*` to frontmatter; this plan adds `human_react`, a per-task-type trust-ladder state machine (`ladder_lib` + `datasets/evals/ladder.json`), a deterministic graduation assessor, a frontmatter-sourced `eval_digest`, accept→apply→receipt→undo card handlers, and two default crons. LangFuse stays a silent opt-in mirror — when `LANGFUSE_SECRET_KEY` is set the existing dual-write paths still fire; they are never the board's data source.

**Tech Stack:** Python 3 (bare Homebrew, PEP-668 → `pip install --break-system-packages`), `python3 -m pytest`, vanilla HTML/CSS/JS board served by `task_server.py`, git for apply/revert.

**Companion design:** `docs/plans/2026-06-06-phase-4-eval-substrate-design.md`. Read it first.

**Conventions:**
- End every commit message with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Git author is already set locally to `Jay Jenkins <11728296+jayhjenkins@users.noreply.github.com>`.
- Run tests with `python3 -m pytest` from repo root. Baseline at Phase 3 close: **104 passing**.
- Branch: `feat/phase-4-eval-substrate-crons` (already created off merged `main`).
- Never read/write `/Users/jayjenkins/pm-os` (separate production system).

---

## Task 0: Shared `tasks_root` test fixture

No existing test isolates `task_lib`'s on-disk dirs. Tasks 3–6 all create tasks in a temp dir, so add one reusable fixture first.

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Add the fixture**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def tasks_root(tmp_path, monkeypatch):
    """Redirect task_lib's on-disk dirs to a temp tree and seed the counter.

    Returns the temp PM-OS root. Use task_lib.create_task / update_task against it.
    """
    import task_lib
    tasks_dir = tmp_path / "datasets" / "tasks"
    archive_dir = tasks_dir / "_archive"
    for q in ("human", "agent", "collab", "waiting"):
        (tasks_dir / q).mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "_counter").write_text("0")
    monkeypatch.setattr(task_lib, "TASKS_DIR", str(tasks_dir))
    monkeypatch.setattr(task_lib, "ARCHIVE_DIR", str(archive_dir))
    # _queue_dir / _next_id derive from TASKS_DIR at call time; confirm in step 2.
    return str(tmp_path)
```

**Step 2: Verify the fixture works**

Add a temporary smoke test `tests/test_tasks_root_smoke.py`:

```python
def test_tasks_root_create_and_read(tasks_root):
    import task_lib
    tid, _ = task_lib.create_task("smoke", queue="agent", domain="ops")
    t = task_lib.read_task(tid)
    assert t["frontmatter"]["title"] == "smoke"
```

Run: `python3 -m pytest tests/test_tasks_root_smoke.py -v`
Expected: PASS. **If `_next_id` or `_queue_dir` reads a cached/module-time path** (FAIL), inspect `scripts/task_lib.py:196` (`_next_id`) and `:60` (`_queue_dir`) and adjust the fixture (they read `TASKS_DIR` at call time per the source, so this should pass).

**Step 3: Delete the smoke test, commit**

```bash
rm tests/test_tasks_root_smoke.py
git add tests/conftest.py
git commit -m "test(phase-4): reusable tasks_root fixture isolating task_lib dirs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 1: `ladder_lib` — per-task-type trust-tier store

The trust-ladder state machine: `shadow → gated → autonomous` per task-type, plus tunable thresholds. Runtime state in `datasets/evals/ladder.json` (gitignored, like `cron/jobs.json`). Functions take an optional `path=` override for clean testing (mirrors `profile_lib`'s `root=`).

**Files:**
- Create: `scripts/ladder_lib.py`
- Test: `tests/test_ladder_lib.py`

**Step 1: Write failing tests**

```python
import json
import ladder_lib


def _ladder(tmp_path):
    return str(tmp_path / "ladder.json")


def test_tier_of_defaults_to_shadow(tmp_path):
    assert ladder_lib.tier_of("prd-draft", path=_ladder(tmp_path)) == "shadow"


def test_advance_climbs_one_rung(tmp_path):
    p = _ladder(tmp_path)
    assert ladder_lib.advance("prd-draft", path=p) == "gated"
    assert ladder_lib.tier_of("prd-draft", path=p) == "gated"
    assert ladder_lib.advance("prd-draft", path=p) == "autonomous"
    # cannot climb past the top
    assert ladder_lib.advance("prd-draft", path=p) == "autonomous"


def test_demote_drops_one_rung(tmp_path):
    p = _ladder(tmp_path)
    ladder_lib.set_tier("x", "autonomous", path=p)
    assert ladder_lib.demote("x", path=p) == "gated"
    assert ladder_lib.demote("x", path=p) == "shadow"
    assert ladder_lib.demote("x", path=p) == "shadow"  # floor


def test_all_tiers_roundtrips(tmp_path):
    p = _ladder(tmp_path)
    ladder_lib.set_tier("a", "gated", path=p)
    assert ladder_lib.all_tiers(path=p)["a"] == "gated"


def test_thresholds_have_moderate_defaults(tmp_path):
    th = ladder_lib.thresholds(path=_ladder(tmp_path))
    assert th["shadow_to_gated"]["min_judged"] == 6
    assert th["shadow_to_gated"]["min_approval"] == 0.75
    assert th["shadow_to_gated"]["min_agreement"] == 0.70
    assert th["gated_to_autonomous"]["min_judged"] == 12
    assert th["gated_to_autonomous"]["min_approval"] == 0.85
    assert th["gated_to_autonomous"]["min_agreement"] == 0.80


def test_thresholds_overridable_in_file(tmp_path):
    p = _ladder(tmp_path)
    with open(p, "w") as f:
        json.dump({"tiers": {}, "thresholds": {"shadow_to_gated": {"min_judged": 99}}}, f)
    th = ladder_lib.thresholds(path=p)
    assert th["shadow_to_gated"]["min_judged"] == 99           # override wins
    assert th["shadow_to_gated"]["min_approval"] == 0.75        # default fills the rest


def test_demote_record_tracks_consecutive(tmp_path):
    p = _ladder(tmp_path)
    assert ladder_lib.note_demotion_signal("a", below=True, path=p) == 1
    assert ladder_lib.note_demotion_signal("a", below=True, path=p) == 2
    assert ladder_lib.note_demotion_signal("a", below=False, path=p) == 0  # resets
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_ladder_lib.py -v`
Expected: FAIL (`ModuleNotFoundError: ladder_lib`).

**Step 3: Implement `scripts/ladder_lib.py`**

```python
#!/usr/bin/env python3
"""ladder_lib — per-task-type trust-tier store for the graduation ladder.

Tiers climb shadow -> gated -> autonomous. State lives in datasets/evals/ladder.json
(runtime, gitignored). Tiers are ADVISORY in Phase 4: displayed and managed, but they
do not yet change dispatch/review behavior (that enforcement is deferred to the Review
surface work). Thresholds are config in the same file with moderate defaults here.

All public functions take an optional `path=` (defaults to the repo ladder.json) so
tests can point at a temp file without monkeypatching.
"""
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PM_OS_DIR = os.path.dirname(SCRIPT_DIR)
LADDER_FILE = os.path.join(PM_OS_DIR, "datasets", "evals", "ladder.json")

TIERS = ["shadow", "gated", "autonomous"]

DEFAULT_THRESHOLDS = {
    "window_days": 60,
    "shadow_to_gated": {"min_judged": 6, "min_approval": 0.75, "min_agreement": 0.70},
    "gated_to_autonomous": {"min_judged": 12, "min_approval": 0.85, "min_agreement": 0.80},
    "demote_consecutive": 2,
}


def _path(path):
    return path or LADDER_FILE


def _load(path):
    p = _path(path)
    if not os.path.exists(p):
        return {"tiers": {}, "thresholds": {}, "demote_signals": {}}
    try:
        with open(p) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {"tiers": {}, "thresholds": {}, "demote_signals": {}}
    d.setdefault("tiers", {})
    d.setdefault("thresholds", {})
    d.setdefault("demote_signals", {})
    return d


def _save(d, path):
    p = _path(path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, p)


def tier_of(task_type, path=None):
    return _load(path)["tiers"].get(task_type, "shadow")


def set_tier(task_type, tier, path=None):
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}")
    d = _load(path)
    d["tiers"][task_type] = tier
    _save(d, path)
    return tier


def advance(task_type, path=None):
    cur = tier_of(task_type, path=path)
    i = min(TIERS.index(cur) + 1, len(TIERS) - 1)
    return set_tier(task_type, TIERS[i], path=path)


def demote(task_type, path=None):
    cur = tier_of(task_type, path=path)
    i = max(TIERS.index(cur) - 1, 0)
    return set_tier(task_type, TIERS[i], path=path)


def all_tiers(path=None):
    return dict(_load(path)["tiers"])


def thresholds(path=None):
    """Deep-merge file overrides onto DEFAULT_THRESHOLDS."""
    over = _load(path)["thresholds"]
    out = json.loads(json.dumps(DEFAULT_THRESHOLDS))  # deep copy
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def note_demotion_signal(task_type, below, path=None):
    """Track consecutive 'below entry bar' assessments. Returns the running count.

    below=True increments; below=False resets to 0. Used by graduation_assess to
    auto-demote only after `demote_consecutive` consecutive bad windows.
    """
    d = _load(path)
    n = d["demote_signals"].get(task_type, 0)
    n = n + 1 if below else 0
    d["demote_signals"][task_type] = n
    _save(d, path)
    return n
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_ladder_lib.py -v`
Expected: PASS (all 7).

**Step 5: Confirm gitignore covers ladder.json**

Run: `git check-ignore datasets/evals/ladder.json`
Expected: prints the path (it matches `datasets/evals/*`). If not ignored, add `datasets/evals/ladder.json` to `.gitignore`.

**Step 6: Commit**

```bash
git add scripts/ladder_lib.py tests/test_ladder_lib.py
git commit -m "feat(ladder): per-task-type trust-tier store + tunable thresholds

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `card_type` + `patch_path` as first-class task fields

Cards are tasks; `card-registry.js` already routes on `task.card_type` (read-only until now). Let creation set it, plus a `patch_path` for recommendation cards. Add CLI flags so the (shell-based) eval-analyst worker can create them.

**Files:**
- Modify: `scripts/task_lib.py:218` (`create_task` signature + frontmatter)
- Modify: `scripts/task_cli.py` (the `add` subparser + its handler)
- Test: `tests/test_card_fields.py`

**Step 1: Write failing tests**

```python
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
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_card_fields.py -v`
Expected: FAIL (`create_task() got an unexpected keyword argument 'card_type'`).

**Step 3: Implement**

In `scripts/task_lib.py`, add params to `create_task` (end of signature, line 225):
```python
                message_to=None, message_subject=None, message_body=None,
                card_type=None, patch_path=None):
```
After the frontmatter dict is built (after line 270), add:
```python
    if card_type:
        frontmatter["card_type"] = card_type
    if patch_path:
        frontmatter["patch_path"] = patch_path
```

In `scripts/task_cli.py`, add to the `add` subparser (after line 402):
```python
    p_add.add_argument("--card-type", default=None,
                       help="Card type for the board renderer (recommendation|graduation|receipt)")
    p_add.add_argument("--patch-path", default=None,
                       help="Path to a .patch file (recommendation cards)")
```
Then thread `card_type=args.card_type, patch_path=args.patch_path` into the `create_task(...)` call in the add handler (find where `cmd_add` / the add branch calls `task_lib.create_task`).

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_card_fields.py -v`
Expected: PASS. Also run `python3 -m pytest` — full suite still green (regression check on create_task).

**Step 5: Manual CLI check**

Run: `./scripts/task.sh add "manual card test" -q collab -d ops --card-type recommendation && ./scripts/task.sh list --queue collab --json | python3 -c "import sys,json; print([t.get('card_type') for t in json.load(sys.stdin)])"`
Expected: list includes `recommendation`. Then delete that test task (`./scripts/task.sh` has a complete/delete path; or remove the file).

**Step 6: Commit**

```bash
git add scripts/task_lib.py scripts/task_cli.py tests/test_card_fields.py
git commit -m "feat(tasks): card_type + patch_path as first-class creation fields + CLI flags

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `human_react` write path (frontmatter + endpoint + modal)

Per-task 👍/👎 + optional note, written to frontmatter. The task modal is the surface. Dual-write the LangFuse trace score when enabled (silent mirror).

**Files:**
- Modify: `scripts/task_lib.py` (add `react_to_task` helper)
- Modify: `scripts/task_server.py` (new handler + route)
- Modify: `ui/task-board/js/board.js` (modal affordance) and/or the modal renderer in `index.html`
- Test: `tests/test_human_react.py`

**Step 1: Write failing tests (Python core)**

```python
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
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_human_react.py -v`
Expected: FAIL (`module 'task_lib' has no attribute 'react_to_task'`).

**Step 3: Implement the helper**

In `scripts/task_lib.py`:
```python
def react_to_task(task_id, react, note=None, actor="human"):
    """Record the operator's per-task reaction. react is 'up' or 'down'.

    Writes human_react / human_react_note / human_reacted_at to frontmatter and
    logs an activity comment. Archive-aware via update_task.
    """
    if react not in ("up", "down"):
        raise ValueError("react must be 'up' or 'down'")
    changes = {
        "human_react": react,
        "human_react_note": (note or None),
        "human_reacted_at": _now_iso(),
    }
    icon = "👍" if react == "up" else "👎"
    comment = f"Human react: {icon}" + (f" — {note}" if note else "")
    update_task(task_id, changes=changes, comment=comment, actor=actor)
    return changes
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_human_react.py -v`
Expected: PASS.

**Step 5: Add the server endpoint + route**

In `scripts/task_server.py`, add a handler near the other task handlers:
```python
def handle_react(handler, task_id):
    """POST /api/tasks/{id}/react — record human 👍/👎 + optional note to frontmatter."""
    body = _read_request_body(handler)
    react = body.get("react")
    note = body.get("note") or None
    if react not in ("up", "down"):
        _error_response(handler, "react must be 'up' or 'down'")
        return
    try:
        task_lib.react_to_task(task_id, react, note=note)
    except Exception as e:
        _error_response(handler, f"React failed: {e}", status=500)
        return
    # Silent LangFuse mirror (opt-in): score the worker-execution trace if enabled.
    try:
        from langfuse_client import get_langfuse, score_trace
        lf = get_langfuse()
        if lf is not None:
            result = lf.api.trace.list(session_id=task_id, order_by="timestamp.desc")
            traces = result.data if hasattr(result, "data") else []
            for t in traces:
                if str(getattr(t, "name", "")).startswith("worker-execution"):
                    score_trace(getattr(t, "id", None), "human-feedback",
                                1.0 if react == "up" else 0.0, comment=note or "", data_type="NUMERIC")
                    break
    except Exception:
        pass
    _json_response(handler, {"ok": True, "task_id": task_id, "react": react})
```
Register the route in `_route_request` (mirror the `/dispatch` regex block, ~line 1373):
```python
        match = re.match(r"^/api/tasks/([^/]+)/react$", path)
        if match and method == "POST":
            task_id = _parse_task_id(match.group(1))
            if task_id is None:
                _error_response(self, "Invalid task ID format", status=400)
            else:
                handle_react(self, task_id)
            return True
```

**Step 6: Add the modal affordance (JS)**

In the task-detail modal (find where agent_output / activity is rendered in `ui/task-board/js/board.js`), add two buttons + an optional note input for agent-completed tasks:
```javascript
// In the modal render for completed agent tasks:
`<div class="react-row">
   <button class="react-btn" data-react="up" onclick="reactTask('${task.id}','up')">👍</button>
   <button class="react-btn" data-react="down" onclick="reactTask('${task.id}','down')">👎</button>
   <input id="react-note-${task.id}" class="react-note" placeholder="optional note"/>
 </div>`
```
And the handler (near other API calls in board.js):
```javascript
async function reactTask(id, react) {
  const note = (document.getElementById(`react-note-${id}`) || {}).value || '';
  try {
    const res = await fetch(`${API}/tasks/${id}/react`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({react, note}),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    toast(react === 'up' ? 'Marked 👍' : 'Marked 👎');
  } catch (e) { toast(`React failed: ${e.message}`); }
}
```
(Match the existing fetch/toast idiom in board.js — `API`, `toast`, `escapeHtml` are already defined.)

**Step 7: Manual end-to-end check**

Start the dev board on **8743** (never 8742): `PORT=8743 python3 scripts/task_server.py` (confirm the port flag/env the server uses; design notes the dev board runs on 8743). Open a completed agent task, click 👍 with a note, confirm the activity log shows the react and the task file frontmatter has `human_react`. Stop the server.

**Step 8: Commit**

```bash
git add scripts/task_lib.py scripts/task_server.py ui/task-board/js/board.js tests/test_human_react.py
git commit -m "feat(eval): per-task human_react to frontmatter + modal affordance + LangFuse mirror

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `eval_digest.py` — frontmatter as the data source

Rewrite the digest to read negative signal from task frontmatter (not LangFuse `/scores`). Keep the output shape (`digest.json` / `digest.md` keys) so the eval-analyst contract holds.

**Files:**
- Modify: `scripts/eval_digest.py` (replace the LangFuse fetch/join with a frontmatter scan)
- Test: `tests/test_eval_digest.py`

**Step 1: Write failing tests**

```python
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
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_eval_digest.py -v`
Expected: FAIL (`build_digest` does not exist; current `eval_digest` is LangFuse-only).

**Step 3: Rewrite `eval_digest.py`**

Replace the LangFuse fetch/join machinery with a frontmatter scan. Keep `write_stub`, `_write_markdown`, the `--days/--all/--out` CLI, and exit-0 semantics. Core new function:

```python
import task_lib  # add near the other imports

JUDGE_GOOD_THRESHOLD = 7  # mirror task_server.JUDGE_GOOD_THRESHOLD


def _is_negative(t):
    s = t.get("judge_score")
    if s is not None:
        try:
            if float(s) < JUDGE_GOOD_THRESHOLD:
                return True
        except (TypeError, ValueError):
            pass
    return t.get("human_react") == "down"


def _within_window(t, cutoff_iso):
    if cutoff_iso is None:
        return True
    stamp = t.get("judge_scored_at") or t.get("human_reacted_at") or t.get("updated") or ""
    return stamp >= cutoff_iso


def build_digest(window_days=7, all_history=False, out_dir=None):
    """Scan judged task frontmatter, cluster negative signal by step + worker.

    Returns the payload dict and writes digest.json + digest.md to out_dir.
    """
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    if all_history:
        cutoff_iso, window_label = None, "all history"
    else:
        cutoff = now - timedelta(days=window_days)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        window_label = f"last {window_days} days (since {cutoff.strftime('%Y-%m-%d')})"

    out = Path(out_dir) if out_dir else (FEEDBACK_DIR / now.strftime("%Y-%m-%d"))

    active = task_lib.list_tasks()
    archived = task_lib.list_archived(limit=2000)
    judged = [t for t in (active + archived)
              if (t.get("judge_score") is not None or t.get("human_react"))]
    judged = [t for t in judged if _within_window(t, cutoff_iso)]
    flagged = [t for t in judged if _is_negative(t)]

    by_step = defaultdict(lambda: {"flagged": 0, "comments": []})
    by_worker = defaultdict(lambda: {"flagged": 0})
    flagged_out = []
    for t in flagged:
        step = t.get("judge_kind") or "unknown"
        group = t.get("task_type") or t.get("domain") or "uncategorized"
        by_step[step]["flagged"] += 1
        note = (t.get("human_react_note") or "").strip()
        why = (t.get("judge_why") or "").strip()
        for c in (note, why):
            if c:
                by_step[step]["comments"].append(c)
        by_worker[group]["flagged"] += 1
        flagged_out.append({
            "trace_id": t["id"], "step": step, "session_id": t["id"],
            "task": {"task_id": t["id"], "title": t.get("title", ""),
                     "domain": t.get("domain", ""), "queue": t.get("queue", "")},
            "worker": group, "timestamp": t.get("judge_scored_at", ""),
            "negative_scores": [
                {"name": "judge", "value": t.get("judge_score"), "comment": why},
            ] + ([{"name": "human", "value": 0, "comment": note}] if t.get("human_react") == "down" else []),
            "output_summary": (t.get("agent_output") or "")[:240],
        })

    flagged_out.sort(key=lambda r: r["timestamp"], reverse=True)
    payload = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": window_label,
        "status": "ok" if flagged_out else "clean",
        "totals": {"negative_scores": sum(len(r["negative_scores"]) for r in flagged_out),
                   "flagged_traces": len(flagged_out)},
        "by_step": dict(by_step), "by_worker": dict(by_worker), "flagged": flagged_out,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "digest.json").write_text(json.dumps(payload, indent=2, default=str))
    _write_markdown(out / "digest.md", payload)
    return payload
```
Rewire `main()` to call `build_digest(window_days=args.days, all_history=args.all, out_dir=args.out)` and print the same summary lines. Remove `load_env`, `_auth_header`, `rest_get`, `fetch_scores`, `fetch_trace`, `find_task`, `is_negative`, `_TASK_INDEX`, `_TRACE_CACHE` (now dead). Keep `write_stub` for the (now rare) exception path and `summarize` if still referenced.

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_eval_digest.py -v`
Expected: PASS (4).

**Step 5: Smoke the CLI against the real (empty dev) tasks**

Run: `python3 scripts/eval_digest.py --all --out /tmp/digest-smoke`
Expected: exit 0; writes a `clean`/`no-data` digest (dev repo has no judged tasks). Confirm `digest.md` reads sensibly.

**Step 6: Commit**

```bash
git add scripts/eval_digest.py tests/test_eval_digest.py
git commit -m "feat(eval): eval_digest reads negative signal from task frontmatter, not LangFuse

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `handle_quality` — agreement % from frontmatter + real tier label

Drop LangFuse as the agreement data source; compute it from `human_react`. Replace the hardcoded `phase: "Shadow"` with `ladder_lib.tier_of()`. Factor the aggregation into a pure, testable function.

**Files:**
- Modify: `scripts/task_server.py:217-334` (`handle_quality`, `_human_feedback_for_task`)
- Test: `tests/test_quality.py`

**Step 1: Write failing tests against a pure function**

```python
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
    result = task_server.build_quality(ladder_path=None)  # see step 3 for signature
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
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_quality.py -v`
Expected: FAIL (`build_quality` not defined).

**Step 3: Refactor `handle_quality` → `build_quality` + thin handler**

Extract a pure function (no `handler` arg). It reuses the existing aggregation logic but:
- reads `human_react` from each task instead of LangFuse `hf_by_trace`;
- `human_positive = (t.get("human_react") == "up")`, counted only when `human_react` is set;
- `phase = ladder_lib.tier_of(gkey, path=ladder_path)`;
- drops the `lf`/`hf_by_trace`/`_human_feedback_for_task` LangFuse pull entirely.

```python
import ladder_lib  # near the top imports

def build_quality(ladder_path=None):
    active = task_lib.list_tasks()
    archived = task_lib.list_archived(limit=1000)
    judged = [t for t in (active + archived) if t.get("judge_score") is not None]
    groups, disagreements = {}, []
    for t in judged:
        gkey = _task_type_of(t)
        g = groups.setdefault(gkey, {"task_type": gkey, "count": 0, "scores": [],
                                     "scored_at": [], "dimensions": {},
                                     "agree": 0, "disagree": 0})
        try:
            score = float(t["judge_score"])
        except (TypeError, ValueError):
            continue
        g["count"] += 1
        g["scores"].append(score)
        g["scored_at"].append(t.get("judge_scored_at") or "")
        dims = t.get("judge_dimensions") or {}
        if isinstance(dims, dict):
            for k, v in dims.items():
                if v is not None:
                    try:
                        g["dimensions"].setdefault(k, []).append(float(v))
                    except (TypeError, ValueError):
                        pass
        react = t.get("human_react")
        if react in ("up", "down"):
            human_positive = react == "up"
            judge_positive = score >= JUDGE_GOOD_THRESHOLD
            if human_positive == judge_positive:
                g["agree"] += 1
            else:
                g["disagree"] += 1
                disagreements.append({
                    "task_id": t["id"], "title": t.get("title", ""), "task_type": gkey,
                    "judge_score": score, "judge_why": t.get("judge_why", ""),
                    "human_value": 1 if human_positive else 0,
                    "human_comment": t.get("human_react_note", "")})

    def avg(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    rows = []
    for g in groups.values():
        scores = g["scores"]
        order = sorted(range(len(scores)), key=lambda i: g["scored_at"][i])
        ordered = [scores[i] for i in order]
        trend = None
        if len(ordered) >= 2:
            mid = len(ordered) // 2
            older, newer = ordered[:mid], ordered[mid:]
            if older and newer:
                trend = round((sum(newer) / len(newer)) - (sum(older) / len(older)), 1)
        reacted = g["agree"] + g["disagree"]
        rows.append({
            "task_type": g["task_type"], "count": g["count"], "avg_score": avg(scores),
            "trend": trend, "history": [round(v, 1) for v in ordered[-8:]],
            "phase": ladder_lib.tier_of(g["task_type"], path=ladder_path),
            "dimensions": {k: avg(v) for k, v in g["dimensions"].items()},
            "agreement_pct": round(100 * g["agree"] / reacted) if reacted else None,
            "reacted": reacted})
    rows.sort(key=lambda r: r["count"], reverse=True)
    disagreements.sort(key=lambda d: d["judge_score"])
    return {"groups": rows, "disagreements": disagreements,
            "total_judged": len(judged), "langfuse": _get_langfuse() is not None}


def handle_quality(handler):
    """GET /api/quality — read-only shadow-judge scoreboard, frontmatter-sourced."""
    try:
        _json_response(handler, build_quality())
    except Exception as e:
        _error_response(handler, f"Failed to gather tasks: {e}", status=500)
```
Keep `langfuse` in the payload (the UI's `_qAgreement` reads it) — see Task 8 for the small UI tweak so agreement no longer *requires* LangFuse.

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_quality.py -v`
Expected: PASS (2). Run full suite — green.

**Step 5: Commit**

```bash
git add scripts/task_server.py tests/test_quality.py
git commit -m "feat(quality): agreement % from human_react frontmatter + ladder tier label

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `graduation_assess.py` — deterministic readiness + auto-demote

Reads frontmatter scores per task-type over the rolling window, computes approval + agreement, creates `graduation` cards when a type is ready to climb, and auto-demotes when a graduated type's metrics fall below its tier's entry bar for `demote_consecutive` windows.

**Files:**
- Create: `scripts/graduation_assess.py`
- Test: `tests/test_graduation_assess.py`

**Step 1: Write failing tests**

```python
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


def test_ready_type_gets_graduation_card(tasks_root, tmp_path):
    import task_lib, graduation_assess, ladder_lib
    p = str(tmp_path / "ladder.json")
    _judged(task_lib, "prd-draft", 9, react="up", n=8)  # >=6, 100% approval+agreement
    created = graduation_assess.assess(ladder_path=p, now_iso="2026-06-10T00:00:00Z")
    assert any(c["task_type"] == "prd-draft" and c["proposed_tier"] == "gated" for c in created)
    # a graduation card task now exists
    cards = [t for t in task_lib.list_tasks() if t.get("card_type") == "graduation"]
    assert len(cards) == 1
    assert cards[0].get("grad_proposed_tier") == "gated"


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
    ladder_lib.set_tier("prd-draft", "gated", path=p)
    _judged(task_lib, "prd-draft", 3, react="down", n=8)  # well below gated entry bar
    graduation_assess.assess(ladder_path=p, now_iso="2026-06-10T00:00:00Z")
    assert ladder_lib.tier_of("prd-draft", path=p) == "gated"   # 1st bad window: no demote yet
    graduation_assess.assess(ladder_path=p, now_iso="2026-06-17T00:00:00Z")
    assert ladder_lib.tier_of("prd-draft", path=p) == "shadow"  # 2nd consecutive: demoted
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_graduation_assess.py -v`
Expected: FAIL (`graduation_assess` not found).

**Step 3: Implement `scripts/graduation_assess.py`**

```python
#!/usr/bin/env python3
"""graduation_assess.py — deterministic trust-ladder assessor (no LLM).

Per task-type over a rolling window, computes human-approval rate and judge<->human
agreement. Creates a `graduation` card when a type clears its next tier's thresholds;
auto-demotes a graduated type whose metrics fall below its current tier's entry bar for
`demote_consecutive` consecutive assessments. Reversible by construction. Exit 0 always.

Run weekly by the graduation cron. `now_iso` is injectable for tests (Date.now()-free).
"""
import argparse
import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import task_lib       # noqa: E402
import ladder_lib     # noqa: E402

JUDGE_GOOD_THRESHOLD = 7
NEXT = {"shadow": "gated", "gated": "autonomous"}
ENTRY_KEY = {"gated": "shadow_to_gated", "autonomous": "gated_to_autonomous"}


def _metrics(tasks):
    """Return (n, approval_rate, agreement_rate) for a list of judged tasks."""
    n = len(tasks)
    if n == 0:
        return 0, 0.0, 0.0
    approvals = 0
    agree = reacted = 0
    for t in tasks:
        try:
            score = float(t.get("judge_score"))
        except (TypeError, ValueError):
            score = None
        react = t.get("human_react")
        judge_pos = score is not None and score >= JUDGE_GOOD_THRESHOLD
        # approval: human up, else judge-positive when no react
        if react == "up" or (react is None and judge_pos):
            approvals += 1
        if react in ("up", "down"):
            reacted += 1
            if (react == "up") == judge_pos:
                agree += 1
    approval_rate = approvals / n
    agreement_rate = (agree / reacted) if reacted else 0.0
    return n, approval_rate, agreement_rate


def _within(t, cutoff_iso):
    stamp = t.get("judge_scored_at") or t.get("human_reacted_at") or t.get("updated") or ""
    return stamp >= cutoff_iso


def assess(ladder_path=None, now_iso=None):
    """Assess every judged task-type. Returns a list of {task_type, proposed_tier} carded."""
    th = ladder_lib.thresholds(path=ladder_path)
    now = datetime.strptime(now_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) \
        if now_iso else datetime.now(timezone.utc)
    cutoff_iso = (now - timedelta(days=th["window_days"])).strftime("%Y-%m-%dT%H:%M:%SZ")

    active = task_lib.list_tasks()
    archived = task_lib.list_archived(limit=2000)
    judged = [t for t in (active + archived)
              if t.get("judge_score") is not None and _within(t, cutoff_iso)]

    by_type = {}
    for t in judged:
        by_type.setdefault(t.get("task_type") or t.get("domain") or "uncategorized", []).append(t)

    existing_grad = {t.get("task_type") for t in active
                     if t.get("card_type") == "graduation" and t.get("status") == "open"}
    created = []
    for task_type, tasks in by_type.items():
        cur = ladder_lib.tier_of(task_type, path=ladder_path)
        n, approval, agreement = _metrics(tasks)

        # --- promotion check ---
        nxt = NEXT.get(cur)
        if nxt:
            bar = th[ENTRY_KEY[nxt]]
            ready = (n >= bar["min_judged"] and approval >= bar["min_approval"]
                     and agreement >= bar["min_agreement"])
            if ready and task_type not in existing_grad:
                _create_graduation_card(task_type, cur, nxt, n, approval, agreement,
                                        [t["id"] for t in tasks[:5]])
                created.append({"task_type": task_type, "proposed_tier": nxt})

        # --- demotion check (only for already-climbed types) ---
        if cur != "shadow":
            entry = th[ENTRY_KEY[cur]]
            below = (agreement < entry["min_agreement"] or approval < entry["min_approval"])
            streak = ladder_lib.note_demotion_signal(task_type, below, path=ladder_path)
            if below and streak >= th["demote_consecutive"]:
                ladder_lib.demote(task_type, path=ladder_path)
                ladder_lib.note_demotion_signal(task_type, False, path=ladder_path)  # reset
    return created


def _create_graduation_card(task_type, cur, nxt, n, approval, agreement, example_ids):
    title = f"Graduate '{task_type}': {cur} → {nxt}?"
    desc = (f"**{task_type}** is ready to climb the trust ladder.\n\n"
            f"- Current tier: **{cur}** → proposed: **{nxt}**\n"
            f"- Judged tasks (window): **{n}**\n"
            f"- Your approval rate: **{round(approval*100)}%**\n"
            f"- Judge↔you agreement: **{round(agreement*100)}%**\n\n"
            f"Example tasks: {', '.join(example_ids)}\n\n"
            f"Graduating is reversible — it auto-demotes if scores later drop.")
    tid, _ = task_lib.create_task(title, queue="collab", priority="medium", domain="ops",
                                  creator="agent", description=desc, tags=["graduation"],
                                  card_type="graduation")
    task_lib.update_task(tid, changes={
        "grad_task_type": task_type, "grad_current_tier": cur, "grad_proposed_tier": nxt,
        "grad_n": n, "grad_approval_pct": round(approval * 100),
        "grad_agreement_pct": round(agreement * 100), "grad_examples": example_ids,
    })
    return tid


def main():
    ap = argparse.ArgumentParser(description="Deterministic trust-ladder assessor")
    ap.add_argument("--now", default=None, help="ISO now (testing/cron determinism)")
    args = ap.parse_args()
    try:
        created = assess(now_iso=args.now)
        print(f"[graduation_assess] created {len(created)} graduation card(s): "
              f"{[c['task_type'] for c in created]}")
    except Exception as e:
        print(f"[graduation_assess] error (non-fatal): {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_graduation_assess.py -v`
Expected: PASS (4). Adjust `grad_*` field names if a test asserts a different key — keep them consistent with the graduation card renderer in Task 8.

**Step 5: Smoke**

Run: `python3 scripts/graduation_assess.py` (against empty dev tasks) → exit 0, "created 0 graduation card(s)".

**Step 6: Commit**

```bash
git add scripts/graduation_assess.py tests/test_graduation_assess.py
git commit -m "feat(graduation): deterministic ladder assessor — promote cards + auto-demote

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: eval-analyst worker — emit real .patch + recommendation cards

Update the worker so it reads the frontmatter-based digest and produces **one `.patch` + one `recommendation` card per clustered change** (capped ~3/week), instead of one plain collab card off LangFuse annotations.

**Files:**
- Modify: `scripts/workers/eval-analyst.md`

**Step 1: Update the frontmatter description + prose**

- Change the `description:` line: drop "reads LangFuse human annotations"; replace with "reads the frontmatter-sourced feedback digest".
- Remove the `langfuse_prompt:` dependency note from the body's step 4 ("LangFuse was down") → reframe as "no negative signal".
- Step 3: still runs `python3 scripts/eval_digest.py --days 7` (now frontmatter-sourced).
- Step 5/6 (cluster + altitude): unchanged guidance.
- Step 7/8 rewrite: instead of one collab card with prose, for each of the **top ≤3 clusters by flagged count**, the worker:
  1. Inspects the real target file.
  2. Writes a unified-diff `.patch` to `datasets/evals/feedback-loop/<dir>/<slug>.patch` (the worker has `Bash`, `Read`, `Write`, `Edit` — it can craft and `git diff`-validate the patch, e.g. apply to a scratch copy or `git apply --check`).
  3. Creates a recommendation card:
     ```
     ./scripts/task.sh add "<short title>" \
       -q collab -p high -d ops --creator agent --tags "eval,self-improvement" \
       --card-type recommendation \
       --patch-path "datasets/evals/feedback-loop/<dir>/<slug>.patch" \
       --description "<human preview: what/why/evidence/risk>"
     ```
  4. Remaining clusters beyond the cap are noted in `recommendations.md`, not carded (calm).
- Keep: read-only on the outside world; never apply changes; clean-week → no card.
- Add an explicit instruction: **every `.patch` must pass `git apply --check`** before its card is created (so accept can't fail on a malformed patch). If a cluster can't be expressed as a clean patch, fall back to a prose-only recommendation card with no `--patch-path` (accept will then open the files; see Task 8 accept fallback).

**Step 2: Validate the worker file parses**

Workers are markdown with YAML frontmatter consumed by `task_dispatch.py`'s matcher. Run the existing worker-loading test if present:
Run: `python3 -m pytest -k worker -v` (and `python3 -m pytest tests/test_adapters.py -v` is unrelated; look for a worker/dispatch test).
Expected: PASS / no parse error. If no test loads workers, add a minimal `tests/test_eval_analyst_worker.py` that loads the frontmatter and asserts `card-type` guidance is present:
```python
def test_eval_analyst_worker_frontmatter_parses():
    import yaml, pathlib
    txt = pathlib.Path("scripts/workers/eval-analyst.md").read_text()
    fm = txt.split("---", 2)[1]
    data = yaml.safe_load(fm)
    assert data["name"] == "eval-analyst"
    assert "recommendation" in txt and "--patch-path" in txt
```

**Step 3: Commit**

```bash
git add scripts/workers/eval-analyst.md tests/test_eval_analyst_worker.py
git commit -m "feat(eval-analyst): emit machine-applicable .patch + per-change recommendation cards

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Card handlers + minimal renderers (accept→apply→receipt→undo, graduate)

Fill the three empty body renderers with minimal content and add the five action branches + their server endpoints. Deliberately plain — Phase 6 restyles. Git stays invisible in the UI.

**Files:**
- Modify: `scripts/task_server.py` (handlers + routes: `/accept`, `/reject`, `/graduate`, `/keep`, `/undo`)
- Modify: `ui/task-board/js/card-registry.js` (`bodyRenderers`, `_renderActions`)
- Modify: `ui/task-board/js/board.js` (action fetch helpers)
- Modify: `ui/task-board/js/quality.js:82` (`_qAgreement` — stop requiring LangFuse)
- Test: `tests/test_card_actions.py`

**Step 1: Write failing tests for the backend semantics (git apply/revert in a tmp repo)**

```python
import subprocess
import os


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def test_accept_applies_patch_and_spawns_receipt(tasks_root, tmp_path, monkeypatch):
    import task_server, task_lib
    # a tiny git repo with a file to patch
    repo = tmp_path
    _git(str(repo), "init")
    _git(str(repo), "config", "user.email", "t@e.com")
    _git(str(repo), "config", "user.name", "t")
    target = repo / "hello.txt"
    target.write_text("hello\n")
    _git(str(repo), "add", "."); _git(str(repo), "commit", "-m", "init")
    patch = repo / "p.patch"
    patch.write_text(
        "--- a/hello.txt\n+++ b/hello.txt\n@@ -1 +1 @@\n-hello\n+hello world\n")
    monkeypatch.setattr(task_server, "PM_OS_DIR", str(repo))  # accept runs git here
    tid, _ = task_lib.create_task("rec", queue="collab", card_type="recommendation",
                                  patch_path="p.patch")
    receipt_id = task_server.apply_recommendation(tid)
    assert (repo / "hello.txt").read_text() == "hello world\n"
    rc = task_lib.read_task(receipt_id)["frontmatter"]
    assert rc["card_type"] == "receipt"
    assert rc.get("revert_commit")  # records the commit to undo


def test_graduate_advances_tier(tasks_root, tmp_path):
    import task_server, task_lib, ladder_lib
    p = str(tmp_path / "ladder.json")
    tid, _ = task_lib.create_task("grad", queue="collab", card_type="graduation")
    task_lib.update_task(tid, changes={"grad_task_type": "prd-draft", "grad_proposed_tier": "gated"})
    task_server.graduate_card(tid, ladder_path=p)
    assert ladder_lib.tier_of("prd-draft", path=p) == "gated"
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_card_actions.py -v`
Expected: FAIL (`apply_recommendation` / `graduate_card` not defined).

**Step 3: Implement backend functions + handlers + routes**

In `task_server.py`, add pure-ish functions (testable) + thin handlers:

```python
def apply_recommendation(task_id):
    """Accept a recommendation: git apply its patch, commit, spawn a receipt card.

    Returns the receipt task id. Raises on a patch that won't apply (handler maps to 409).
    """
    t = task_lib.read_task(task_id)["frontmatter"]
    patch_path = t.get("patch_path")
    if not patch_path:
        # prose-only recommendation: no patch to apply (worker fallback). Caller opens files.
        raise ValueError("no patch_path on this recommendation")
    abspath = patch_path if os.path.isabs(patch_path) else os.path.join(PM_OS_DIR, patch_path)
    chk = subprocess.run(["git", "-C", PM_OS_DIR, "apply", "--check", abspath],
                         capture_output=True, text=True)
    if chk.returncode != 0:
        raise RuntimeError(f"patch does not apply cleanly: {chk.stderr.strip()[:300]}")
    subprocess.run(["git", "-C", PM_OS_DIR, "apply", abspath], check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "-C", PM_OS_DIR, "add", "-A"], check=True, capture_output=True, text=True)
    msg = f"apply recommendation {task_id}: {t.get('title', '')}"
    subprocess.run(["git", "-C", PM_OS_DIR, "commit", "-m", msg], check=True,
                   capture_output=True, text=True)
    rev = subprocess.run(["git", "-C", PM_OS_DIR, "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    task_lib.update_task(task_id, changes={"status": "done"}, comment="Accepted — applied", actor="human")
    receipt_id, _ = task_lib.create_task(
        f"Applied: {t.get('title', '')}", queue="human", domain="ops", creator="agent",
        description=f"Applied recommendation {task_id}. One-tap Undo reverts it.",
        card_type="receipt")
    task_lib.update_task(receipt_id, changes={"revert_commit": rev, "source_recommendation": task_id})
    return receipt_id


def undo_receipt(task_id):
    t = task_lib.read_task(task_id)["frontmatter"]
    rev = t.get("revert_commit")
    if not rev:
        raise ValueError("no revert_commit on this receipt")
    subprocess.run(["git", "-C", PM_OS_DIR, "revert", "--no-edit", rev], check=True,
                   capture_output=True, text=True)
    task_lib.update_task(task_id, changes={"status": "done"}, comment="Undone — reverted", actor="human")


def graduate_card(task_id, ladder_path=None):
    t = task_lib.read_task(task_id)["frontmatter"]
    task_type = t.get("grad_task_type")
    proposed = t.get("grad_proposed_tier")
    if not task_type or not proposed:
        raise ValueError("graduation card missing grad_task_type / grad_proposed_tier")
    ladder_lib.set_tier(task_type, proposed, path=ladder_path)
    task_lib.update_task(task_id, changes={"status": "done"},
                         comment=f"Graduated {task_type} → {proposed}", actor="human")
```
Add `import subprocess` if not present. Add thin handlers (`handle_accept`, `handle_reject`, `handle_graduate`, `handle_keep`, `handle_undo`) that call these, map `RuntimeError`→409 with the plain-language message, and `_json_response` ok. `reject`/`keep` just set `status: done` + archive with a comment. Register five routes mirroring the `/react` regex block.

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_card_actions.py -v`
Expected: PASS (2).

**Step 5: Minimal JS renderers**

In `ui/task-board/js/card-registry.js`, replace the empty `bodyRenderers`:
```javascript
const bodyRenderers = {
  diff(task) {
    const preview = (task.body || '').trim();
    return `<div class="card-body card-body-diff" data-card-body="diff">
      ${preview ? `<pre class="rec-diff">${escapeHtml(preview)}</pre>` : ''}
      ${task.patch_path ? `<div class="rec-patch-note">patch: ${escapeHtml(task.patch_path)}</div>` : ''}
    </div>`;
  },
  preview(task) {
    return `<div class="card-body card-body-preview" data-card-body="preview">
      <div class="receipt-line">Applied. <span class="receipt-undo-hint">Undo reverts this change.</span></div>
    </div>`;
  },
  agreement(task) {
    return `<div class="card-body card-body-agreement" data-card-body="agreement">
      <div class="grad-stat"><b>${escapeHtml(task.grad_task_type || '')}</b>: ${escapeHtml(task.grad_current_tier || 'shadow')} → ${escapeHtml(task.grad_proposed_tier || '')}</div>
      <div class="grad-stat">approval ${task.grad_approval_pct ?? '—'}% · agreement ${task.grad_agreement_pct ?? '—'}% · n=${task.grad_n ?? '—'}</div>
    </div>`;
  },
};
```
Add the action branches in `_renderActions` (after the `open_output` branch):
```javascript
    } else if (id === 'accept') {
      btns.push(`<button class="card-action act-accept" onclick="cardAction('${task.id}','accept',event)">Accept</button>`);
    } else if (id === 'reject') {
      btns.push(`<button class="card-action act-reject" onclick="cardAction('${task.id}','reject',event)">Reject</button>`);
    } else if (id === 'graduate') {
      btns.push(`<button class="card-action act-graduate" onclick="cardAction('${task.id}','graduate',event)">Graduate this</button>`);
    } else if (id === 'keep') {
      btns.push(`<button class="card-action act-keep" onclick="cardAction('${task.id}','keep',event)">Keep</button>`);
    } else if (id === 'undo') {
      btns.push(`<button class="card-action act-undo" onclick="cardAction('${task.id}','undo',event)">Undo</button>`);
    }
```
In `board.js`, add the generic action helper:
```javascript
async function cardAction(id, action, ev) {
  if (ev) ev.stopPropagation();
  try {
    const res = await fetch(`${API}/tasks/${id}/${action}`, {method: 'POST'});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    toast({accept: 'Accepted', reject: 'Rejected', graduate: 'Graduated',
           keep: 'Kept', undo: 'Undone'}[action] || 'Done');
    loadBoard();  // re-render (match the board's existing refresh fn name)
  } catch (e) { toast(`${action} failed: ${e.message}`); }
}
```
(Confirm the board's refresh function name — `loadBoard`/`renderBoard`/`refresh` — and the `escapeHtml`/`toast`/`API` globals; reuse them.)

**Step 6: Fix `_qAgreement` so agreement no longer requires LangFuse**

In `ui/task-board/js/quality.js:82-86`, agreement now comes from frontmatter regardless of LangFuse:
```javascript
function _qAgreement(g) {
  if (g.agreement_pct == null || !g.reacted) return 'no ratings from you yet';
  return `you agree ${g.agreement_pct}%`;
}
```
Update its call site (line 137) to `_qAgreement(g)`.

**Step 7: Validate the registry still passes its schema**

Run: `python3 scripts/card_schema.py`
Expected: `registry.json OK` (we didn't change the registry data, only renderers — but confirm).
Run full suite: `python3 -m pytest` — green.

**Step 8: Manual visual pass (owed)**

Start the dev board on **8743**. Manually seed one recommendation card (with a tiny real patch), one graduation card (via `graduation_assess.py` after seeding judged tasks, or hand-create with `--card-type graduation` + the `grad_*` fields), and verify: diff renders in a `<pre>`; Accept applies + a receipt card appears; Undo on the receipt reverts; Graduate flips the tier shown in the Quality tab. Note this as the human visual pass owed from Phase 3 too.

**Step 9: Commit**

```bash
git add scripts/task_server.py ui/task-board/js/card-registry.js ui/task-board/js/board.js ui/task-board/js/quality.js tests/test_card_actions.py
git commit -m "feat(cards): accept→apply→receipt→undo + graduate handlers + minimal renderers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Two default crons + minimal graduation worker

Seed the weekly self-improvement and graduation crons. Self-improvement routes to the existing eval-analyst worker; graduation is deterministic, run by a minimal worker that shells `graduation_assess.py`.

**Files:**
- Modify: `scripts/seed_default_crons.py` (`DEFAULTS`)
- Create: `scripts/workers/grad-assessor.md` (minimal worker)
- Test: `tests/test_seed_default_crons.py`

**Step 1: Write failing test**

```python
def test_seed_includes_both_phase4_crons(tmp_path, monkeypatch):
    import cron_lib, seed_default_crons
    monkeypatch.setattr(cron_lib, "CRON_DIR", str(tmp_path / "cron"))
    monkeypatch.setattr(cron_lib, "JOBS_FILE", str(tmp_path / "cron" / "jobs.json"))
    monkeypatch.setattr(cron_lib, "COUNTER_FILE", str(tmp_path / "cron" / "_counter"))
    seed_default_crons.seed()
    names = {j["name"] for j in cron_lib.list_jobs()}
    assert "Weekly self-improvement" in names
    assert "Graduation ladder" in names
    # idempotent
    added = seed_default_crons.seed()
    assert added == 0
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_seed_default_crons.py -v`
Expected: FAIL (names absent).

**Step 3: Add the two DEFAULTS**

In `scripts/seed_default_crons.py`, append to `DEFAULTS`:
```python
    {
        "name": "Weekly self-improvement",
        "cron_expr": "0 9 * * 1",  # Monday 09:00 (with the Doctor cron)
        "cron_human": "Every Monday at 9:00am",
        "task_template": {
            "title": "Feedback-loop self-improvement pass {date}",
            "queue": "agent", "priority": "medium", "domain": "ops",
            "description": (
                "Weekly self-improvement. Run `python3 scripts/eval_digest.py --days 7`, "
                "cluster failures by step, and for the top clusters draft a machine-applicable "
                ".patch + a recommendation card each (eval-analyst worker). Propose only; nothing "
                "auto-applies."
            ),
        },
    },
    {
        "name": "Graduation ladder",
        "cron_expr": "30 9 * * 1",  # Monday 09:30, after the digest pass
        "cron_human": "Every Monday at 9:30am",
        "task_template": {
            "title": "Trust-ladder graduation assessment {date}",
            "queue": "agent", "priority": "low", "domain": "ops",
            "description": (
                "Run `python3 scripts/graduation_assess.py`. Deterministic: assess each task-type's "
                "approval + judge↔human agreement over the rolling window, create graduation cards "
                "for types ready to climb, and auto-demote types whose scores dropped. No analysis "
                "needed beyond running the script and reporting what it created."
            ),
        },
    },
```

**Step 4: Create the minimal `grad-assessor` worker**

`scripts/workers/grad-assessor.md` — matches the graduation task, runs the script, reports:
```markdown
---
name: grad-assessor
description: Runs the deterministic trust-ladder graduation assessor and reports what it created. No analysis, no external writes.
priority: 7
match:
  task_type: []
  domains: [ops]
  title_patterns:
    - "(?i)graduation assessment"
    - "(?i)trust.?ladder"
  description_patterns:
    - "(?i)graduation_assess"
allowed_tools:
  - "Bash(python3 scripts/graduation_assess.py*)"
  - "Bash(./scripts/task.sh*)"
  - "Read(*)"
timeout: 180
max_turns: 6
---

You run the deterministic graduation assessor. Steps:

0. Read CLAUDE.md.
1. `./scripts/task.sh agent:start {task_id}`
2. `python3 scripts/graduation_assess.py` — this is deterministic; it creates any graduation
   cards and performs any auto-demotions itself. Do not assess readiness yourself.
3. Read its stdout. `./scripts/task.sh agent:complete {task_id}` with a one-line note of how many
   graduation cards it created (and any demotions). No output artifact needed.

Do not edit the ladder, skills, or any file. Do not create cards yourself — the script does that.
```
Note: this worker's `priority: 7` must not mis-match other tasks; verify the matcher picks it for the graduation task and `eval-analyst` for the self-improvement task. If the dispatcher has a worker-match test, extend it; otherwise add a quick assertion in `tests/test_seed_default_crons.py` that the graduation template title matches `grad-assessor`'s patterns (import the matcher from `task_dispatch`).

**Step 5: Run tests + full suite**

Run: `python3 -m pytest tests/test_seed_default_crons.py -v` → PASS.
Run: `python3 -m pytest` → all green (target ~125+).

**Step 6: Commit**

```bash
git add scripts/seed_default_crons.py scripts/workers/grad-assessor.md tests/test_seed_default_crons.py
git commit -m "feat(cron): seed weekly self-improvement + graduation crons (+ grad-assessor worker)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Correct the master design's execution-trace claim

**Files:**
- Modify: `docs/plans/2026-06-05-pm-os-portability-design.md:93` (the §5 table row)

**Step 1: Edit the row**

Change the "Execution traces" row from "Local JSONL (already written today)" to reflect reality:
`**Claude Code session JSONL** (~/.claude/projects/<slug>/, written for free per invocation; not yet task-joined — capturing the dispatch session_id is a future enhancement)`.

**Step 2: Commit**

```bash
git add docs/plans/2026-06-05-pm-os-portability-design.md
git commit -m "docs(design): correct §5 execution-trace claim to Claude Code session JSONL

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Definition of Done (Phase 4)

- [ ] `python3 -m pytest` green (≈125+; was 104 at Phase 3 close).
- [ ] `python3 scripts/card_schema.py` → `registry.json OK`.
- [ ] `human_react` written to frontmatter from the task modal; dual-writes LangFuse when enabled.
- [ ] `eval_digest.py` sources negative signal from frontmatter; LangFuse not required.
- [ ] Quality tab agreement % + tier label come from frontmatter / `ladder.json` with no LangFuse.
- [ ] `graduation_assess.py` creates graduation cards + auto-demotes; deterministic, idempotent.
- [ ] Recommendation accept → git apply + commit → receipt; Undo → git revert. Graduate → tier advance.
- [ ] eval-analyst emits machine-applicable `.patch` + per-change recommendation cards (capped).
- [ ] Two default crons seeded idempotently; graduation routes to `grad-assessor`.
- [ ] LangFuse remains a silent opt-in mirror — Jay's `LANGFUSE_SECRET_KEY` path still lights up.
- [ ] Owed: on-screen human visual pass of the live board (dev board on **8743**) for all new card variants + actions.

## Residual / deferred (named, not Phase 4)

- Dispatch-behavior enforcement of tiers (gated hold-for-review, autonomous auto-complete) → Phase 6 Review surface.
- Polished card rendering (the diff/agreement/preview bodies are intentionally plain) → Phase 6 Designer.
- Task→transcript join (capture dispatch `session_id`) so eval-analyst can read the actual tool-call trace → future enhancement.
- LangFuse annotation enrichment of the digest → deferred; frontmatter is the source.
