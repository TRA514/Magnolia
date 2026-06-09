# Trust-ladder ENFORCING Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the trust ladder *enforce* — an autonomous action-type auto-ships its terminal action (judge-gated, Tier-2-gated), supervised types get a judge-driven revision loop, behind a default-OFF global Autonomous Mode flag, with an instant Quality-tab kill switch.

**Architecture:** The judge (already fires detached after `agent:complete`) becomes the enforcement seam: after it scores, it calls `enforce_lib.apply_post_judge`, which runs a tier×score policy (revise / park / ship). Auto-ship reuses the existing Tier-2-gated send/publish cores, extracted into `shipper.py` so they're importable without the HTTP server. The headless LLM agent never ships — only trusted backend processes do.

**Tech Stack:** Python 3 (stdlib + ruamel.yaml), vanilla HTML/CSS/JS board served by `task_server.py`, pytest.

**Design doc:** `docs/plans/2026-06-09-trust-ladder-enforcement-design.md`

**Green gates — run before EVERY commit (invariant #2):**
```bash
python3 -m pytest -q
python3 scripts/card_schema.py          # must print: registry.json OK
python3 -m pytest tests/test_engine_no_jay.py -q
```

**Branch:** `feat/trust-ladder-enforcement` (already created; never commit to `main`).
**Commit trailer:** end every commit with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## Task 1: Autonomy posture flag (`profile_lib` + `config.yaml`)

The global default-OFF flag that gates auto-ship. Mirrors `set_cost_posture`.

**Files:**
- Modify: `profile/config.yaml`
- Modify: `scripts/profile_lib.py` (add getter + setter near `set_cost_posture:299`)
- Test: `tests/test_autonomy_flag.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_autonomy_flag.py
import os, sys, shutil, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import profile_lib

def _tmp_profile(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "profile"))
    with open(os.path.join(root, "profile", "config.yaml"), "w") as f:
        f.write("models:\n  cost_posture: low\nserver:\n  port: 8743\n")
    return root

def test_autonomy_defaults_false_when_absent(tmp_path):
    root = _tmp_profile(tmp_path)
    assert profile_lib.autonomy_enforcement(root) is False

def test_set_autonomy_roundtrips_and_preserves_siblings(tmp_path):
    root = _tmp_profile(tmp_path)
    profile_lib.set_autonomy_enforcement(True, root=root)
    assert profile_lib.autonomy_enforcement(root) is True
    # sibling key preserved
    assert (profile_lib.config(root).get("models") or {}).get("cost_posture") == "low"
    profile_lib.set_autonomy_enforcement(False, root=root)
    assert profile_lib.autonomy_enforcement(root) is False
```

**Step 2: Run — expect FAIL** (`AttributeError: module 'profile_lib' has no attribute 'autonomy_enforcement'`)

```bash
python3 -m pytest tests/test_autonomy_flag.py -q
```

**Step 3: Implement** — add to `scripts/profile_lib.py` (after `set_cost_posture`):

```python
def autonomy_enforcement(root=None):
    """Global posture flag: may an autonomous action-type auto-ship without a
    per-instance human approve? Default False (auto-ship is opt-in per install)."""
    return bool(config(root).get("autonomy_enforcement", False))


def set_autonomy_enforcement(enabled, root=None):
    """Set config.yaml['autonomy_enforcement'] (preserves siblings + comments)."""
    def mutate(doc):
        doc["autonomy_enforcement"] = bool(enabled)
    _update_yaml("config.yaml", mutate, root)
```

And add the default to `profile/config.yaml` (after `active_skill_packs` block):
```yaml
# Autonomous Mode: when true, action-types graduated to the 'autonomous' tier
# auto-ship their terminal action (send / publish) without a per-instance approve.
# Default off — opt-in via the top-bar settings cog.
autonomy_enforcement: false
```

**Step 4: Run — expect PASS.** Then the full gates.

**Step 5: Commit**
```bash
git add scripts/profile_lib.py profile/config.yaml tests/test_autonomy_flag.py
git commit -m "feat(trust-ladder): autonomy_enforcement posture flag (default off)"
```

---

## Task 2: `enforce_lib` foundations (pure helpers)

Action-type registry + the cheap pure reads. No decision logic yet (Task 7).

**Files:**
- Create: `scripts/enforce_lib.py`
- Test: `tests/test_enforce_lib.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_enforce_lib.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import enforce_lib

def test_action_type_send_message():
    assert enforce_lib.action_type_of({"task_type": "send-message"}) == "send-message"

def test_action_type_publish_ticket():
    assert enforce_lib.action_type_of({"task_type": "publish-ticket"}) == "publish-ticket"

def test_action_type_jira_body_marker_when_unstamped():
    # Belt-and-suspenders: a draft not yet stamped still reads as publish-ticket.
    fm = {"task_type": None, "body": "x\n<!-- JIRA_DRAFT -->\n...\n<!-- /JIRA_DRAFT -->"}
    assert enforce_lib.action_type_of(fm) == "publish-ticket"

def test_action_type_artifact_is_none():
    assert enforce_lib.action_type_of({"task_type": "prd"}) is None
    assert enforce_lib.action_type_of({"task_type": None, "domain": "product"}) is None

def test_grouping_key_prefers_action_type_then_domain():
    assert enforce_lib.grouping_key({"task_type": "send-message"}) == "send-message"
    assert enforce_lib.grouping_key({"task_type": None, "domain": "eng"}) == "eng"
    assert enforce_lib.grouping_key({}) == "uncategorized"
```

**Step 2: Run — expect FAIL** (no module).

**Step 3: Implement** `scripts/enforce_lib.py`:

```python
#!/usr/bin/env python3
"""enforce_lib — the trust-ladder enforcement policy.

The judge (which already fires after agent:complete) calls apply_post_judge after
scoring; this module decides revise / park / ship by tier × score. Auto-ship runs
ONLY in a trusted backend process (the judge), never the headless LLM agent — and
always through the Tier-2-gated shipper, so the per-integration first-write confirm
still fires. Artifact types are hard-stopped from ever auto-shipping.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402
import ladder_lib    # noqa: E402

# Only ACTION types can auto-ship. Artifacts (PRDs, research, memos) never can —
# autonomy can't transfer the accountability of signing a document.
ACTION_TYPES = {"send-message", "publish-ticket"}

DEFAULT_MAX_REVISIONS = 1
JUDGE_GOOD_THRESHOLD = 7  # mirrors judge.JUDGE_GOOD_THRESHOLD; the quality bar.


def action_type_of(fm):
    """The canonical action type for a task, or None for an artifact.

    Keys off the stamped task_type; falls back to the JIRA_DRAFT body marker so an
    as-yet-unstamped Jira draft still reads as publish-ticket."""
    tt = fm.get("task_type")
    if tt in ACTION_TYPES:
        return tt
    if "<!-- JIRA_DRAFT -->" in (fm.get("body") or ""):
        return "publish-ticket"
    return None


def grouping_key(fm):
    """The ladder/judge grouping key — mirrors graduation_assess/build_quality."""
    return action_type_of(fm) or fm.get("task_type") or fm.get("domain") or "uncategorized"


def revision_bar(path=None):
    """The judge score at/above which work passes (ship/park) vs revises."""
    th = ladder_lib.thresholds(path=path)
    return int(th.get("revision_bar", JUDGE_GOOD_THRESHOLD))


def max_revisions(path=None):
    th = ladder_lib.thresholds(path=path)
    return int(th.get("max_revisions", DEFAULT_MAX_REVISIONS))


def autonomy_enabled(root=None):
    return profile_lib.autonomy_enforcement(root)
```

**Step 4: Run — expect PASS.** Then full gates.

**Step 5: Commit**
```bash
git add scripts/enforce_lib.py tests/test_enforce_lib.py
git commit -m "feat(trust-ladder): enforce_lib foundations — action-type registry + pure reads"
```

---

## Task 3: `ladder_lib.kill_to_supervised` (the kill-switch primitive)

**Files:**
- Modify: `scripts/ladder_lib.py` (after `demote:103`)
- Test: `tests/test_ladder_lib.py` (append)

**Step 1: Write the failing test** (append to `tests/test_ladder_lib.py`):

```python
def test_kill_to_supervised_sets_tier_and_resets_streak(tmp_path):
    p = str(tmp_path / "ladder.json")
    import ladder_lib
    ladder_lib.set_tier("send-message", "autonomous", path=p)
    ladder_lib.note_demotion_signal("send-message", True, path=p)  # streak = 1
    ladder_lib.kill_to_supervised("send-message", path=p)
    assert ladder_lib.tier_of("send-message", path=p) == "supervised"
    # streak reset so the assessor doesn't double-count
    import json
    d = json.load(open(p))
    assert d["demote_signals"].get("send-message", 0) == 0

def test_kill_to_supervised_idempotent(tmp_path):
    p = str(tmp_path / "ladder.json")
    import ladder_lib
    ladder_lib.kill_to_supervised("send-message", path=p)
    ladder_lib.kill_to_supervised("send-message", path=p)
    assert ladder_lib.tier_of("send-message", path=p) == "supervised"
```

(Match the import/fixture style already used in `tests/test_ladder_lib.py`.)

**Step 2: Run — expect FAIL.**

**Step 3: Implement** in `scripts/ladder_lib.py`:

```python
def kill_to_supervised(task_type, path=None):
    """Instant kill switch: drop a type to supervised and reset its demotion streak.

    The manual, immediate counterpart to graduation_assess's twice-weekly
    auto-demote — the brake that makes shipping autonomy safe. Resetting the streak
    avoids the assessor double-counting this manual action."""
    set_tier(task_type, "supervised", path=path)
    note_demotion_signal(task_type, False, path=path)
    return "supervised"
```

**Step 4: Run — expect PASS.** Then full gates.

**Step 5: Commit**
```bash
git add scripts/ladder_lib.py tests/test_ladder_lib.py
git commit -m "feat(trust-ladder): ladder_lib.kill_to_supervised kill-switch primitive"
```

---

## Task 4: Extract send/publish cores into `shipper.py` (behavior-preserving)

The terminal-action cores currently live in `task_server.py`. Extract them so they're
importable without the HTTP server (the judge/enforce backend will call them). This is a
**refactor with zero behavior change** — the existing send/publish/Tier-2 tests are the
spec and must stay green untouched.

**Files:**
- Create: `scripts/shipper.py`
- Modify: `scripts/task_server.py` (the send/publish/confirm cores + helpers)
- Tests (must stay green, do not edit): `tests/test_send_message_route.py`, `tests/test_publish_core.py`, `tests/test_messaging_tier2.py`, `tests/test_send_message_graph.py`

**Step 1: Move these from `task_server.py` into `scripts/shipper.py`** (cut, paste, keep bodies identical):
- `_message_draft_from_task` (`task_server.py:794`)
- `_attempt_send_message` (`task_server.py:821`)
- `_record_manual_send` (`task_server.py:879`)
- `_attempt_publish` (`task_server.py:1528`)
- `_emit_confirm_card` (`task_server.py:1584`)
- `_note` (`task_server.py:~1522`) and `_load_email_cache` (`task_server.py:1706`) — move to shipper (server re-imports them).

`shipper.py` imports: `task_lib`, `profile_lib`, `adapters`, `jira_publish`,
`NeedsConfirmation`, `NotConfigured`, `MessagingNotConfigured` (same imports
`task_server` uses for these). Keep the `(status, payload)` contracts exactly.

**Step 2: In `task_server.py`, replace the moved bodies with imports/wrappers:**
```python
import shipper
from shipper import (
    _message_draft_from_task, _attempt_send_message, _record_manual_send,
    _attempt_publish, _emit_confirm_card, _note, _load_email_cache,
)
```
The `handle_send_message`, `handle_publish_jira`, and `handle_confirm` HANDLER functions
stay in `task_server.py` (they own HTTP response shaping) and now call the imported cores.

**Step 3: Run the existing suites — expect PASS, unchanged:**
```bash
python3 -m pytest tests/test_send_message_route.py tests/test_publish_core.py tests/test_messaging_tier2.py tests/test_send_message_graph.py -q
```
If any import path in those tests references `task_server._attempt_*`, keep the
re-export above so the symbol still resolves from `task_server` (back-compat). Verify:
```bash
python3 -c "import sys; sys.path.insert(0,'scripts'); import task_server, shipper; print('ok')"
```

**Step 4: Full gates — expect PASS.**

**Step 5: Commit**
```bash
git add scripts/shipper.py scripts/task_server.py
git commit -m "refactor(trust-ladder): extract send/publish cores into shipper.py (no behavior change)"
```

---

## Task 5: Stamp `publish-ticket` on Jira drafts at completion

So the ladder/judge/Quality tab/enforcement all key consistently on a clean action type.

**Files:**
- Modify: `scripts/task_cli.py` (`cmd_agent_complete:220`)
- Test: `tests/test_publish_ticket_stamp.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_publish_ticket_stamp.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import task_cli, task_lib
from types import SimpleNamespace

def test_stamps_publish_ticket_when_jira_draft_present(tmp_path, monkeypatch):
    # Use task_lib's tmp infra the way other task_cli tests do; create a task whose
    # body contains the JIRA_DRAFT marker, run cmd_agent_complete, assert task_type.
    # (Mirror the fixture pattern in tests/test_send_message_route.py for task dirs.)
    tid = _make_task(tmp_path, body="Do it\n<!-- JIRA_DRAFT -->\n...\n<!-- /JIRA_DRAFT -->")
    task_cli.cmd_agent_complete(SimpleNamespace(task_id=tid, output=None))
    assert task_lib.read_task(tid)["frontmatter"].get("task_type") == "publish-ticket"

def test_does_not_overwrite_existing_task_type(tmp_path):
    tid = _make_task(tmp_path, body="x", task_type="send-message")
    task_cli.cmd_agent_complete(SimpleNamespace(task_id=tid, output=None))
    assert task_lib.read_task(tid)["frontmatter"].get("task_type") == "send-message"
```

> Implementation note for the executor: factor `_make_task`/dir fixture from an
> existing task_cli/route test rather than reinventing it.

**Step 2: Run — expect FAIL.**

**Step 3: Implement** — in `cmd_agent_complete`, before the `update_task` call, add:

```python
    # Stamp the canonical action task_type for a Jira draft so the trust ladder,
    # judge, and Quality tab all key on 'publish-ticket' (the draft is otherwise
    # title-pattern-routed with no task_type). Never overwrite an explicit type.
    try:
        existing = task_lib.read_task(args.task_id)["frontmatter"] or {}
        body = task_lib.read_task(args.task_id).get("body", "") or ""
        if not existing.get("task_type") and "<!-- JIRA_DRAFT -->" in body:
            changes["task_type"] = "publish-ticket"
    except Exception:
        pass
```

**Step 4: Run — expect PASS.** Then full gates.

**Step 5: Commit**
```bash
git add scripts/task_cli.py tests/test_publish_ticket_stamp.py
git commit -m "feat(trust-ladder): stamp publish-ticket task_type on Jira drafts at completion"
```

---

## Task 6: Judge `ticket` kind (so Jira drafts get scored)

Without a kind, `detect_kind` returns None for a draft → never scored → never passes the
auto-ship gate. Add a ticket kind + rubric + evidence.

**Files:**
- Modify: `scripts/judge.py` (`detect_kind:259`, `RUBRICS:140`, `DIMENSIONS_BY_KIND:147`, `gather_evidence:~286`, `KIND_EVIDENCE_LABEL:~324`)
- Test: `tests/test_judge_ticket_kind.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_judge_ticket_kind.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import judge

def test_detect_kind_ticket():
    assert judge.detect_kind({"task_type": "publish-ticket"}) == "ticket"

def test_ticket_rubric_registered():
    assert "ticket" in judge.RUBRICS
    assert "ticket" in judge.DIMENSIONS_BY_KIND

def test_gather_evidence_ticket_parses_draft():
    body = ("<!-- JIRA_DRAFT -->\n### Summary\nFix the thing\n"
            "### Description\nWhen X then Y.\n<!-- /JIRA_DRAFT -->")
    ev, note = judge.gather_evidence("ticket", {"task_type": "publish-ticket"}, body, "T-1")
    assert ev and "Fix the thing" in ev
```

**Step 2: Run — expect FAIL.**

**Step 3: Implement** in `scripts/judge.py`:

- `detect_kind` — add near the top of the function, before the document fallback:
```python
    if task_type == "publish-ticket":
        return "ticket"
```
- `DEFAULT_RUBRIC_TICKET` (new constant near the other rubrics):
```python
DEFAULT_RUBRIC_TICKET = """You are the PM-OS shadow judge. You score a DRAFTED TICKET a worker agent \
prepared to file in the team's issue tracker. Judge ONLY the drafted ticket below.
Score these dimensions (1-10): completeness (has a clear summary + enough description \
to act on, with acceptance/repro where relevant), clarity (unambiguous, well-scoped — \
one issue, not many), actionability (an engineer could pick it up without a follow-up), \
format (correct fields/type for the tracker; no placeholders).
Then give an overall score (1-10): would you, as a demanding PM lead, let this ticket be \
filed as-is? For each weak dimension, point to the concrete gap and what would raise it.
Return only JSON: {"score": <1-10 int>, "dimensions": {"completeness": <1-10>, \
"clarity": <1-10>, "actionability": <1-10>, "format": <1-10>}, "why": "<one paragraph>"}"""
```
- `RUBRICS["ticket"] = ("judge-rubric-ticket", DEFAULT_RUBRIC_TICKET)`
- `DIMENSIONS_BY_KIND["ticket"] = ["completeness", "clarity", "actionability", "format"]`
- `KIND_EVIDENCE_LABEL["ticket"] = "DRAFTED TICKET (score this)"`
- `gather_evidence` — add a branch (import `jira_publish` at top if not already):
```python
    if kind == "ticket":
        import jira_publish
        d = jira_publish.parse_jira_draft(body) or {}
        if not d:
            return None, "no JIRA_DRAFT block found"
        lines = [f"- Type: {d.get('type','?')}",
                 f"- Summary: {d.get('summary','')}",
                 f"- Description: {(d.get('description') or '').strip() or '(none)'}"]
        fields = d.get("fields") or {}
        for k, v in fields.items():
            lines.append(f"- {k}: {v}")
        return "\n".join(lines), "ticket draft fields"
```
> Confirm the actual key names returned by `parse_jira_draft` (`jira_publish.py:65`)
> and adjust `d.get(...)` accordingly.

**Step 4: Run — expect PASS.** Then full gates.

**Step 5: Commit**
```bash
git add scripts/judge.py tests/test_judge_ticket_kind.py
git commit -m "feat(trust-ladder): judge ticket kind + rubric so Jira drafts are scored"
```

---

## Task 7: `enforce_lib.apply_post_judge` (the policy brain) + shipper auto-ship entry

The core decision: revise / park / ship, by tier × score. Plus `shipper.autoship` (ship
by family, emit confirm card on Tier-2, emit receipt on success).

**Files:**
- Modify: `scripts/shipper.py` (add `autoship` + `_emit_autoship_receipt`)
- Modify: `scripts/enforce_lib.py` (add `apply_post_judge` + `_trigger_revision`)
- Test: `tests/test_enforce_apply.py` (create)

**Step 1: Write the failing test** (drives the matrix with fakes):

```python
# tests/test_enforce_apply.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import enforce_lib

class FakeLadder:
    def __init__(self, tier): self._t = tier
    def tier_of(self, k, path=None): return self._t

def _patch(monkeypatch, *, tier, flag, score, revs=0, action="send-message",
           reset=None, ship=None):
    fm = {"task_type": action, "revision_count": revs, "id": "T-1", "status": "open"}
    monkeypatch.setattr(enforce_lib, "tier_of", lambda k, path=None: tier)
    monkeypatch.setattr(enforce_lib, "autonomy_enabled", lambda root=None: flag)
    monkeypatch.setattr(enforce_lib, "_read_fm", lambda tid: fm)
    monkeypatch.setattr(enforce_lib, "_trigger_revision", lambda tid, why, n: reset.append(tid) if reset is not None else None)
    monkeypatch.setattr(enforce_lib, "_autoship", lambda tid, at: (ship.append(tid), "shipped")[1] if ship is not None else "shipped")
    return fm

def V(score): return {"score": score, "why": "because"}

def test_shadow_parks(monkeypatch):
    _patch(monkeypatch, tier="shadow", flag=True, score=3)
    assert enforce_lib.apply_post_judge("T-1", V(3)) == "park"

def test_supervised_below_bar_revises(monkeypatch):
    reset = []
    _patch(monkeypatch, tier="supervised", flag=True, score=4, reset=reset)
    assert enforce_lib.apply_post_judge("T-1", V(4)) == "revise"
    assert reset == ["T-1"]

def test_supervised_below_bar_exhausted_parks(monkeypatch):
    _patch(monkeypatch, tier="supervised", flag=True, score=4, revs=99)
    assert enforce_lib.apply_post_judge("T-1", V(4)) == "park"

def test_supervised_pass_parks_for_human(monkeypatch):
    _patch(monkeypatch, tier="supervised", flag=True, score=9)
    assert enforce_lib.apply_post_judge("T-1", V(9)) == "park"

def test_autonomous_pass_action_flag_on_ships(monkeypatch):
    ship = []
    _patch(monkeypatch, tier="autonomous", flag=True, score=9, ship=ship)
    assert enforce_lib.apply_post_judge("T-1", V(9)) == "shipped"
    assert ship == ["T-1"]

def test_autonomous_pass_flag_off_parks(monkeypatch):
    _patch(monkeypatch, tier="autonomous", flag=False, score=9)
    assert enforce_lib.apply_post_judge("T-1", V(9)) == "park"

def test_autonomous_pass_artifact_hard_stop_parks(monkeypatch):
    _patch(monkeypatch, tier="autonomous", flag=True, score=9, action="prd")
    assert enforce_lib.apply_post_judge("T-1", V(9)) == "park"

def test_autonomous_below_bar_revises(monkeypatch):
    reset = []
    _patch(monkeypatch, tier="autonomous", flag=True, score=4, reset=reset)
    assert enforce_lib.apply_post_judge("T-1", V(4)) == "revise"

def test_no_score_parks(monkeypatch):
    _patch(monkeypatch, tier="autonomous", flag=True, score=None)
    assert enforce_lib.apply_post_judge("T-1", {"score": None, "why": ""}) == "park"
```

**Step 2: Run — expect FAIL.**

**Step 3: Implement.**

In `scripts/enforce_lib.py` add (note the thin seams `tier_of`, `_read_fm`,
`_trigger_revision`, `_autoship` are module-level so tests can patch them):

```python
import subprocess

def tier_of(key, path=None):
    return ladder_lib.tier_of(key, path=path)


def _read_fm(task_id):
    import task_lib
    return task_lib.read_task(task_id).get("frontmatter") or {}


def _trigger_revision(task_id, judge_why, revision_count):
    """Bounce a below-bar task back to the agent, carrying the judge's feedback.

    Reuses the rerun path: reset agent fields + status open, append the judge's
    'why' as a revision comment, bump revision_count, then re-dispatch --rerun
    (detached, Claude env stripped — mirrors task_server.handle_rerun_task)."""
    import task_lib
    task_lib.update_task(task_id, changes={
        "status": "open", "agent_status": "", "agent_error": "",
        "agent_output": "", "agent_started": "", "agent_completed": "",
        "revision_count": revision_count + 1,
    }, comment=f"[revision] Judge sent this back for revision: {judge_why}", actor="judge")
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "task_dispatch.py")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "CMUX_CLAUDE"))}
    env["PATH"] = (os.path.join(os.path.expanduser("~"), ".local", "bin")
                   + ":/opt/homebrew/bin:" + env.get("PATH", "/usr/bin:/bin"))
    subprocess.Popen([sys.executable, script, "--task", task_id, "--rerun"],
                     cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     env=env, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _autoship(task_id, action_type):
    import shipper
    return shipper.autoship(task_id, action_type)


def apply_post_judge(task_id, verdict, *, root=None, ladder_path=None):
    """Run the tier × score policy after the judge scores. Returns one of:
    'park' | 'revise' | 'shipped' | 'needs_confirm' | 'error'. Never raises into
    the judge — any failure returns 'park' (the safe default: human reviews)."""
    try:
        fm = _read_fm(task_id)
        score = verdict.get("score")
        if score is None:
            return "park"  # unscored → never ship; human reviews
        key = grouping_key(fm)
        tier = tier_of(key, path=ladder_path)
        if tier == "shadow":
            return "park"
        # supervised + autonomous: quality gate first.
        if score < revision_bar(path=ladder_path):
            if int(fm.get("revision_count") or 0) < max_revisions(path=ladder_path):
                _trigger_revision(task_id, verdict.get("why", ""), int(fm.get("revision_count") or 0))
                return "revise"
            return "park"  # revisions exhausted → human reviews
        # passing score.
        action = action_type_of(fm)
        if tier == "autonomous" and action in ACTION_TYPES and autonomy_enabled(root):
            return _autoship(task_id, action)
        return "park"  # supervised pass, artifact, or flag off
    except Exception:
        return "park"
```

In `scripts/shipper.py` add `autoship` + receipt:

```python
def autoship(task_id, action_type):
    """Auto-ship an autonomous action-type's terminal action (Tier-2 gated).

    Returns 'shipped' | 'needs_confirm' | 'error'. On needs_confirm, emits the
    one-time Tier-2 confirm card (autonomy never bypasses the first-write confirm)
    and leaves the task parked. On success, emits a Keep/Undo receipt."""
    if action_type == "send-message":
        draft = _message_draft_from_task(task_id)
        status, payload = _attempt_send_message(task_id, draft)
        family, what = "messaging", f"Sent {draft.get('channel')} to {draft.get('to_display')}"
    elif action_type == "publish-ticket":
        import jira_publish
        body = task_lib.read_task(task_id).get("body", "")
        draft = jira_publish.parse_jira_draft(body)
        status, payload = _attempt_publish(task_id, draft)
        what = f"Published {payload[0]}" if status == "ok" and payload else "Published ticket"
        family = "project_management"
    else:
        return "error"
    if status == "needs_confirm":
        _emit_confirm_card(family, task_id)
        return "needs_confirm"
    if status in ("ok",):
        _emit_autoship_receipt(task_id, action_type, what)
        return "shipped"
    if status in ("already_sent", "already_published"):
        return "shipped"
    return "error"


def _emit_autoship_receipt(source_task_id, action_type, what):
    """A never-deleted Keep/Undo receipt for an auto-shipped action. Undo demotes
    the type to supervised (it cannot un-send — the receipt copy says so)."""
    src = task_lib.read_task(source_task_id).get("frontmatter") or {}
    cid, _ = task_lib.create_task(
        f"Auto-shipped: {what}", queue="collab", domain="ops", creator="agent",
        description=(f"Autonomous Mode shipped this without a per-instance approve.\n\n"
                     f"**{what}**\n\nThe external action already happened. **Keep** to "
                     f"acknowledge, or **Undo** to stop auto-shipping '{action_type}' "
                     f"(drops it back to supervised — it cannot un-send)."),
        card_type="receipt")
    task_lib.update_task(cid, changes={
        "receipt_kind": "autoship",
        "autoship_task_type": action_type,
        "receipt_summary": what,
        "judge_score": src.get("judge_score"),
        "judge_why": src.get("judge_why"),
    })
    return cid
```

**Step 4: Run — expect PASS** (`tests/test_enforce_apply.py`). Then full gates.

**Step 5: Commit**
```bash
git add scripts/enforce_lib.py scripts/shipper.py tests/test_enforce_apply.py
git commit -m "feat(trust-ladder): apply_post_judge policy + shipper.autoship (Tier-2 gated, receipted)"
```

---

## Task 8: Wire the judge to call `apply_post_judge`

**Files:**
- Modify: `scripts/judge.py` (after `write_back` is called in `main`/score flow — find the call site)
- Test: `tests/test_judge_calls_enforce.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_judge_calls_enforce.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import judge

def test_write_back_success_calls_apply_post_judge(monkeypatch):
    calls = []
    monkeypatch.setattr(judge, "_post_judge", lambda tid, v: calls.append((tid, v)))
    # call whatever wrapper invokes write_back + _post_judge; assert it ran.
    judge._finalize("T-9", {"score": 8, "why": "ok", "dimensions": {}}, "rubric-v1", "message")
    assert calls and calls[0][0] == "T-9"

def test_enforce_error_does_not_raise(monkeypatch):
    monkeypatch.setattr(judge, "_post_judge", lambda tid, v: (_ for _ in ()).throw(RuntimeError("boom")))
    # must not raise — judge stays additive / exit 0
    judge._finalize("T-9", {"score": 8, "why": "ok", "dimensions": {}}, "rubric-v1", "message")
```

> The executor should introduce a small `_finalize(task_id, verdict, rubric_version,
> kind)` helper that calls `write_back(...)` then `_post_judge(...)`, and have `main`
> call `_finalize` instead of `write_back` directly — this gives a clean seam to test
> and keeps the enforcement call strictly after a successful write-back.

**Step 2: Run — expect FAIL.**

**Step 3: Implement** in `scripts/judge.py`:

```python
def _post_judge(task_id, verdict):
    import enforce_lib
    return enforce_lib.apply_post_judge(task_id, verdict)


def _finalize(task_id, verdict, rubric_version, kind):
    """Persist the verdict, then run trust-ladder enforcement. Strictly additive:
    an enforcement failure never breaks judging (judge exits 0)."""
    ok = write_back(task_id, verdict, rubric_version, kind)
    try:
        _post_judge(task_id, verdict)
    except Exception as e:
        log(f"post-judge enforcement failed for {task_id} (non-fatal): {e}")
    return ok
```

Then replace the `write_back(...)` call in `main` (around `judge.py:531+`) with
`_finalize(...)`.

**Step 4: Run — expect PASS.** Then full gates.

**Step 5: Commit**
```bash
git add scripts/judge.py tests/test_judge_calls_enforce.py
git commit -m "feat(trust-ladder): judge runs apply_post_judge after write-back (additive)"
```

---

## Task 9: Server routes — autonomy flag GET/POST + demote

**Files:**
- Modify: `scripts/task_server.py` (handlers + the `_route_request` table ~`2171`)
- Test: `tests/test_enforcement_routes.py` (create)

**Step 1: Write the failing test** — mirror the request-handler test style already in
`tests/test_send_message_route.py` (a fake handler capturing `_json_response`). Assert:
- `GET /api/config/autonomy` → `{"enabled": <bool>}`.
- `POST /api/config/autonomy {"enabled": true}` flips `profile_lib.autonomy_enforcement`.
- `POST /api/tasks/SEND/demote` calls `ladder_lib.kill_to_supervised` with the row's
  `task_type` and returns the new tier `"supervised"`.

**Step 2: Run — expect FAIL.**

**Step 3: Implement** handlers in `task_server.py`:

```python
def handle_get_autonomy(handler):
    _json_response(handler, {"enabled": profile_lib.autonomy_enforcement()})


def handle_set_autonomy(handler):
    try:
        body = _read_request_body(handler)
    except (json.JSONDecodeError, ValueError) as e:
        _error_response(handler, f"Invalid JSON body: {e}", status=400); return
    enabled = bool(body.get("enabled"))
    profile_lib.set_autonomy_enforcement(enabled)
    _json_response(handler, {"ok": True, "enabled": enabled})


def handle_demote(handler, task_type):
    if not task_type:
        _error_response(handler, "Missing task_type", status=400); return
    tier = ladder_lib.kill_to_supervised(task_type)
    _json_response(handler, {"ok": True, "task_type": task_type, "tier": tier})
```

Register in `_route_request` (alongside the other `/api/...` routes):
```python
        if path == "/api/config/autonomy" and method == "GET":
            handle_get_autonomy(self); return
        if path == "/api/config/autonomy" and method == "POST":
            handle_set_autonomy(self); return
        m = re.match(r"^/api/tasks/([^/]+)/demote$", path)
        if m and method == "POST":
            handle_demote(self, urllib.parse.unquote(m.group(1))); return
```
> The demote endpoint is keyed by **task_type** (the Quality row), not a task id —
> the `{id}` slot carries the type string. Decode it.

**Step 4: Run — expect PASS.** Then full gates.

**Step 5: Commit**
```bash
git add scripts/task_server.py tests/test_enforcement_routes.py
git commit -m "feat(trust-ladder): /api/config/autonomy + /api/tasks/{type}/demote routes"
```

---

## Task 10: `handle_undo` — autoship branch (demote instead of git-revert)

The reused `receipt` card's Undo currently git-reverts a local patch. An auto-ship
receipt can't be reverted — Undo must demote the type to supervised.

**Files:**
- Modify: `scripts/task_server.py` (`handle_undo` / `undo_recommendation` ~`1140`)
- Test: `tests/test_undo_autoship.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_undo_autoship.py — assert that undo on a receipt with
# receipt_kind == "autoship" calls ladder_lib.kill_to_supervised(autoship_task_type)
# and archives the receipt, and does NOT attempt a git revert.
```

**Step 2: Run — expect FAIL.**

**Step 3: Implement** — at the top of the undo core, branch:
```python
    fm = task_lib.read_task(task_id)["frontmatter"] or {}
    if fm.get("receipt_kind") == "autoship":
        at = fm.get("autoship_task_type")
        if at:
            ladder_lib.kill_to_supervised(at)
        task_lib.update_task(task_id, changes={"status": "done"},
            comment=f"Undo: stopped auto-shipping '{at}' (dropped to supervised). "
                    "The external action already happened and cannot be un-sent.",
            actor="human")
        return
    # ... existing git-revert path unchanged ...
```

**Step 4: Run — expect PASS.** Then full gates.

**Step 5: Commit**
```bash
git add scripts/task_server.py tests/test_undo_autoship.py
git commit -m "feat(trust-ladder): autoship receipt Undo demotes to supervised (honest, no fake revert)"
```

---

## Task 11: Frontend — settings cog + Autonomous Mode toggle

Theme-compliant gear in the top-bar (top-right), opening a popover with the toggle.

**Files:**
- Modify: `ui/task-board/index.html` (top-bar markup + script include + a `:root`-less, token-only style block goes in `css/magnolia.css`)
- Modify: `ui/task-board/js/icons.js` (add a `gear`/`settings` icon)
- Modify: `ui/task-board/css/magnolia.css` (cog button + popover + switch — **theme tokens only**, no hex/px-color; sizes use existing radius/spacing tokens)
- Create: `ui/task-board/js/settings.js` (fetch `GET /api/config/autonomy`; render switch; `POST` on toggle; toast)
- Modify: `ui/task-board/index.html` to `<script src="/js/settings.js">` and mount the cog

**Steps (UI — verify by running the board, not a unit test):**
1. Add a `settings` icon to `icons.js` (match the stroke/viewBox style of existing icons).
2. Add the cog button to the top bar right cluster (next to the Mood control). Class names + colors from existing tokens (see `css/magnolia.css` top-bar controls; invariant #3).
3. `settings.js`: `initSettings()` wires the cog click → popover; popover holds a labelled switch "Autonomous Mode" + one calm line of help text ("Let trusted action-types ship without asking. Off by default."). On change → `POST /api/config/autonomy`; on open → `GET` to reflect current state; toast on success/failure.
4. Restart the dev board (it caches modules) and verify (Task 13 / e2e): cog appears, popover opens, toggle persists across reload, matches each Mood.

**Commit**
```bash
git add ui/task-board/index.html ui/task-board/js/icons.js ui/task-board/js/settings.js ui/task-board/css/magnolia.css
git commit -m "feat(trust-ladder): top-bar settings cog with Autonomous Mode toggle (token-only)"
```

---

## Task 12: Frontend — Quality-tab kill switch + honest receipt copy

**Files:**
- Modify: `ui/task-board/js/quality.js` (`renderQuality` group card — `quality.js:130-143`)
- Modify: `ui/task-board/js/card-registry.js` (receipt body revert copy — `card-registry.js:195`)
- Modify: `ui/task-board/css/magnolia.css` (kill-switch button — token-only)

**Steps:**
1. In `quality.js`, for each group where `tier === 'autonomous'`, render a clear control
   in `.q-card-head` (or `.q-foot`): a button "Stop auto-shipping" → on click,
   `POST ${API}/tasks/${encodeURIComponent(g.task_type)}/demote` → toast
   ("Dropped {type} to supervised — it'll ask again before sending.") → `renderQuality()`
   to refresh. Render the button ONLY for `autonomous` types.
2. In `card-registry.js` receipt body (`receipt-revert` line), branch on the task:
   if `task.receipt_kind === 'autoship'`, show
   `"Already sent — Undo stops auto-shipping this type."` instead of
   `"Applied — Undo reverts this change."`.
3. Restart the dev board; verify in e2e.

**Commit**
```bash
git add ui/task-board/js/quality.js ui/task-board/js/card-registry.js ui/task-board/css/magnolia.css
git commit -m "feat(trust-ladder): Quality-tab kill switch + honest auto-ship receipt copy"
```

---

## Task 13: Live e2e verification + docs

**Step 1 — e2e (dev board only, `localhost:8743`):**
Restart the dev board (it caches Python modules + serves JS):
```bash
# stop any running dev board on 8743, then:
python3 scripts/task_server.py   # or the project's documented dev-board start
```
Verify by exercising the real flow (see `docs/plans/.../visual-pass` technique / Chrome headless if no display):
- Cog → popover → toggle Autonomous Mode on/off; reload → state persists.
- Quality tab: a type at `autonomous` shows "Stop auto-shipping"; clicking it drops the
  row to supervised and the button disappears.
- Drive a `send-message` task to `autonomous` (set tier via `ladder_lib`), flag ON,
  integration confirmed → on completion the judge scores → it auto-ships → a receipt card
  appears in collab; Undo drops the type to supervised.
- With the integration **unconfirmed**, the same flow emits the one-time confirm card
  (autonomy did NOT bypass Tier-2). 
- Flag OFF → the autonomous type parks for human (no auto-ship).

**Step 2 — docs:** update `docs/reference/architecture.md` trust-ladder section to state
the ladder now ENFORCES (was advisory): the judge→`enforce_lib.apply_post_judge` seam, the
tier×score table, the action/artifact hard-stop, the global flag, the kill switch, and the
Tier-2 composition. Keep it a concise reference (link the design doc).

**Step 3 — full gates one final time, then commit docs:**
```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
git add docs/reference/architecture.md
git commit -m "docs(trust-ladder): architecture — ladder is now enforcing (judge seam, flag, kill switch)"
```

---

## Notes for the executor

- **Never commit to `main`**; you're on `feat/trust-ladder-enforcement`.
- **Gates green before every commit.** If a gate is red, fix before moving on.
- Inspect history with `git show` / `git diff` — never `git checkout` (it derails the tree).
- The engine stays de-personalized (invariant #1): no person/team literals in any
  `scripts/`/`.claude/` file — `test_engine_no_jay.py` enforces it.
- Card definitions are token-only (invariant #3) — `card_schema.py` enforces it for the
  registry; for `magnolia.css` additions, reuse existing tokens (no raw hex/px-color).
- Auto-ship is **judge-gated and Tier-2-gated and flag-gated** — three independent gates.
  Do not collapse them.
