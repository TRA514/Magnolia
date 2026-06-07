# Phase 8 — Workers & Prompts, file-backed — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Engine → Workers & Prompts board tab render with no Docker/LangFuse, driven by an
enriched file-backed `GET /api/workers`, as a read-only inspector that surfaces each worker's tier,
resolved model, and pack membership.

**Architecture:** Three layers. (1) Fix stale nested worker `skills:` → flat folder names (prerequisite
for a trustworthy pack join; also repairs a latent dispatch-scoping no-op). (2) Enrich `/api/workers`
server-side with `tier` + resolved `model` (via `profile_lib.resolve_model`) + `packs` (via
`packs_lib.load_packs`). (3) Rewrite `ui/task-board/js/agents.js` to drive the list off `/api/workers`
and drop all LangFuse/infra-prompt coupling; keep the detail modal file-backed and read-only.

**Tech Stack:** Python 3 (bare Homebrew, PEP-668 → `pip install --break-system-packages`),
`ruamel.yaml`, stdlib `http.server`; vanilla HTML/CSS/JS board served by `scripts/task_server.py`;
`pytest`. Design doc: `docs/plans/2026-06-07-phase-8-workers-prompts-filebacked-design.md`.

**Conventions:** Branch is `feat/phase-8-workers-prompts-filebacked` (already created). Git author is
set locally. End every commit message with
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Keep `python3 -m pytest`
(baseline **209 passed**) and `python3 scripts/card_schema.py` green. Dev board is `:8743`; **never**
touch `:8742` or `/Users/jayjenkins/pm-os`.

---

## Task 1: Fix worker skill names (nested → flat) + regression lock

Prerequisite for the pack join. The nested→flat mapping was verified 1:1 against on-disk folders
during brainstorm (zero unresolved). `eval-analyst` and `ticket-creator` are already flat; the
no-skills workers (`_default`, `grad-assessor`, `message-writer`) are untouched.

**Files:**
- Test: `tests/test_worker_skills_resolve.py` (create)
- Modify: `scripts/workers/researcher.md` (the `skills:` block)
- Modify: `scripts/workers/scheduler.md` (the `skills:` block)
- Modify: `scripts/workers/product-analyst.md` (the `skills:` block)

**Step 1: Write the failing test**

Create `tests/test_worker_skills_resolve.py`:

```python
import os
from task_dispatch import load_workers

PM_OS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(PM_OS_DIR, ".claude", "skills")


def _folder_exists(name):
    d = os.path.join(SKILLS_DIR, name)
    return os.path.isfile(os.path.join(d, "SKILL.md")) or os.path.isfile(os.path.join(d, "skill.md"))


def test_every_worker_skill_resolves_to_a_flat_folder():
    """Worker skills: must be flat folder names that exist on disk. Guards the
    nested->flat rename and stops a regression where build_skills_catalog_filtered
    silently falls through to the full catalog."""
    offenders = []
    for w in load_workers():
        for s in w.get("skills", []):
            if "/" in s or not _folder_exists(s):
                offenders.append(f"{w['name']}: {s}")
    assert not offenders, "Unresolved/nested worker skills:\n" + "\n".join(offenders)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jayjenkins/dev/pm-os-team && python3 -m pytest tests/test_worker_skills_resolve.py -v`
Expected: FAIL — offenders list includes `researcher: context-assembly/research-gathering`,
`product-analyst: workflows/prd-creation`, `scheduler: workflows/schedule-meeting`, etc.

**Step 3: Rewrite the three `skills:` blocks to flat names**

In `scripts/workers/researcher.md`, replace the `skills:` block with:

```yaml
skills:
  - context-research-gathering
  - context-meeting-synthesis
  - context-pendo-analytics
  - context-databricks-analytics
  - context-search
  - context-source-normalization
  - quality-source-integrity
  - quality-citation-compliance
```

In `scripts/workers/scheduler.md`, replace the `skills:` block with:

```yaml
skills:
  - workflow-schedule-meeting
  - task-update
  - task-communicate
```

In `scripts/workers/product-analyst.md`, replace the `skills:` block (keep the `#` section comments if
desired — they are harmless) with these flat names:

```yaml
skills:
  # /ship-it pipeline skills (vision → PRD → validation → business case)
  - workflow-vision-clarifier
  - workflow-devils-advocate
  - workflow-agentic-api-designer
  - workflow-prd-creation
  - workflow-ambition-expander
  - workflow-red-team-reviewer
  - workflow-swag-modeler
  # Strategy and planning
  - workflow-product-strategy-creation
  - workflow-strategy-session
  - workflow-strategy-memo
  - workflow-product-planning
  - workflow-roadmap-updating
  - workflow-launch-announcement
  - workflow-publish-package
  # Metrics and goals
  - workflow-goal-setting
  - workflow-metrics-definition
  - workflow-metric-diagnosis
  - workflow-tradeoff-decision
  - workflow-dashboard-design
  # Context assembly
  - context-meeting-synthesis
  - context-research-gathering
  - context-priority-scoring
  - context-search
  - context-pendo-analytics
  - context-databricks-analytics
  - context-source-normalization
  # Quality gates
  - quality-prd-validation
  - quality-product-strategy-validation
  - quality-citation-compliance
  - quality-source-integrity
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_worker_skills_resolve.py -v`
Expected: PASS.

**Step 5: Confirm no regression in the full suite**

Run: `python3 -m pytest -q`
Expected: all green (210 now, baseline 209 + 1).

**Step 6: Commit**

```bash
git add tests/test_worker_skills_resolve.py scripts/workers/researcher.md scripts/workers/scheduler.md scripts/workers/product-analyst.md
git commit -m "fix(phase-8): flatten stale nested worker skill names; lock with resolve test

Repairs build_skills_catalog_filtered scoping no-op and enables the pack join.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Enrich `GET /api/workers` with tier + resolved model + pack membership

Add a pure, testable helper next to `build_profile` in `task_server.py`, then call it from the
handler. Mirrors how `build_profile`/`_profile_workers` already compute tier+model.

**Files:**
- Test: `tests/test_workers_api.py` (create)
- Modify: `scripts/task_server.py` (add `_worker_packs` + `workers_payload`; rewrite
  `handle_list_workers` body, ~line 1625)

**Step 1: Write the failing test**

Create `tests/test_workers_api.py`:

```python
import task_server


def test_workers_payload_has_tier_model_packs():
    workers = task_server.workers_payload(posture="balanced")
    assert workers, "expected workers from scripts/workers/"
    by_name = {w["name"]: w for w in workers}
    # Every worker carries the enrichment keys
    for w in workers:
        assert "tier" in w and "model" in w and "packs" in w
        assert isinstance(w["packs"], list)
    # researcher is tier=deep -> balanced resolves to opus
    r = by_name["researcher"]
    assert r["tier"] == "deep"
    assert r["model"] == "claude-opus-4-8"
    # product-analyst's skills live in the pm pack -> pm membership
    assert "pm" in by_name["product-analyst"]["packs"]
    # _default has no skills -> no pack membership
    assert by_name["_default"]["packs"] == []


def test_workers_payload_model_tracks_posture():
    low = {w["name"]: w for w in task_server.workers_payload(posture="low")}
    high = {w["name"]: w for w in task_server.workers_payload(posture="high")}
    # deep worker: low -> sonnet, high -> opus (clamped)
    assert low["researcher"]["model"] == "claude-sonnet-4-6"
    assert high["researcher"]["model"] == "claude-opus-4-8"
    # light worker (scheduler): low -> haiku, high -> sonnet
    assert low["scheduler"]["model"] == "claude-haiku-4-5"
    assert high["scheduler"]["model"] == "claude-sonnet-4-6"


def test_worker_packs_empty_when_no_manifest(tmp_path):
    # No .claude/packs.yaml under tmp root -> load_packs returns {} -> no membership
    assert task_server._worker_packs(["workflow-prd-creation"], root=str(tmp_path)) == []
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_workers_api.py -v`
Expected: FAIL — `AttributeError: module 'task_server' has no attribute 'workers_payload'`.

**Step 3: Add the helpers in `task_server.py`**

Insert after `build_profile` (after line ~417). `packs_lib` and `profile_lib` are already imported at
module top (used by `build_profile`); confirm and reuse.

```python
def _worker_packs(worker_skills, packs=None, root=None):
    """Pack ids whose skill set intersects the worker's (flat) skill names.
    [] when no manifest or no intersection."""
    if packs is None:
        packs = packs_lib.load_packs(root)
    sk = set(worker_skills or [])
    return [pid for pid, spec in packs.items() if sk & set(spec.get("skills", []))]


def workers_payload(root=None, posture=None):
    """Enriched, read-only worker list for GET /api/workers: file truth from
    scripts/workers/*.md plus Phase-7 tier, resolved model at the current cost
    posture, and pack membership. Degrades: missing tier -> resolve_model
    defaults to standard; missing packs.yaml -> packs == []."""
    from task_dispatch import load_workers
    if posture is None:
        posture = (profile_lib.config(root).get("models") or {}).get("cost_posture") or "balanced"
    packs = packs_lib.load_packs(root)
    out = []
    for w in load_workers():
        tier = w.get("tier")
        out.append({
            "name": w.get("name", ""),
            "description": w.get("description", ""),
            "priority": w.get("priority", 0),
            "match": w.get("match", {}),
            "allowed_tools": w.get("allowed_tools", []),
            "skills": w.get("skills", []),
            "langfuse_prompt": w.get("langfuse_prompt", ""),
            "timeout": w.get("timeout", 600),
            "max_turns": w.get("max_turns", 30),
            "prompt_body": w.get("prompt_body", ""),
            "tier": tier,
            "model": profile_lib.resolve_model(tier, posture=posture),
            "packs": _worker_packs(w.get("skills", []), packs=packs),
        })
    return out
```

**Step 4: Rewrite `handle_list_workers` to use the helper**

Replace the body of `handle_list_workers` (~line 1625) with:

```python
def handle_list_workers(handler):
    """GET /api/workers — file-backed worker definitions enriched with tier,
    resolved model at current posture, and pack membership (read-only)."""
    try:
        _json_response(handler, {"workers": workers_payload()})
    except Exception as e:
        _error_response(handler, f"Failed to load workers: {e}", status=500)
```

**Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_workers_api.py -v`
Expected: PASS (all three).

**Step 6: Confirm the full suite + card schema gate**

Run: `python3 -m pytest -q && python3 scripts/card_schema.py`
Expected: all green; card_schema prints OK.

**Step 7: Commit**

```bash
git add scripts/task_server.py tests/test_workers_api.py
git commit -m "feat(phase-8): /api/workers surfaces tier, resolved model, pack membership

Server-side join via resolve_model + packs_lib; read-only, degrades gracefully.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Rewrite the tab frontend off LangFuse (read-only inspector)

No JS test harness — verified on-screen in Task 4. This task is the edit + a syntax sanity check.

**Files:**
- Modify: `ui/task-board/js/agents.js` (delete LangFuse list fns; add `fetchWorkers`/`renderWorkers`;
  edit `openWorkerDetail`)
- Modify: `ui/task-board/js/app.js:10` and `:26` (`fetchPrompts()` → `fetchWorkers()`)

**Step 1: Delete the LangFuse-coupled list functions**

In `ui/task-board/js/agents.js`, delete `fetchPrompts` (lines ~19-32), `renderPrompts` (~34-146), and
`toggleSkillsList` (~148-158). **Keep** `checkLangfuseHealth` (top-bar health dot — separate feature).

**Step 2: Add `fetchWorkers` + `renderWorkers`**

Insert in their place (under the `// ─── Workers View ───` banner):

```javascript
// ─── Workers View (file-backed; no LangFuse) ────────────────────────

async function fetchWorkers() {
  const view = document.getElementById('prompts-view');
  try {
    const res = await fetch(`${API}/workers`);
    const data = await res.json();
    _workerCache = data.workers || [];          // reused by the detail modal
    renderWorkers(_workerCache);
  } catch (err) {
    view.innerHTML = `<div class="loading" style="color:var(--danger)">Could not load workers: ${err.message}</div>`;
  }
}

function renderWorkers(workers) {
  const view = document.getElementById('prompts-view');
  let html = '<div class="prompts-section-title">Workers</div>';
  if (!workers.length) {
    html += '<div style="color:var(--text-muted);font-size:13px;">No workers found in scripts/workers/.</div>';
    view.innerHTML = html;
    return;
  }
  html += '<div class="prompt-cards">';
  for (const w of workers) {
    const tier = w.tier || 'standard';
    const packs = (w.packs || []).join(', ');
    html += `<div class="prompt-card" onclick="openWorkerDetail('${w.name}')" style="cursor:pointer">
      <div class="prompt-card-header">
        <span class="prompt-card-name">${escapeHtml(w.name)}</span>
        <span class="pf-tier ${escapeHtml(tier)}">${escapeHtml(tier)}</span>
      </div>
      <div class="prompt-card-desc">${escapeHtml(w.description || '')}</div>
      <div class="prompt-card-stats">
        <span>Model: ${escapeHtml(w.model || '—')}</span>
        ${packs ? `<span>Packs: ${escapeHtml(packs)}</span>` : ''}
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-top:6px;">Click for details</div>
    </div>`;
  }
  html += '</div>';
  view.innerHTML = html;
}
```

Note: `fetchWorkerDetails()` already populates `_workerCache` from `/api/workers`; setting it in
`fetchWorkers` just warms the same cache. Leave `fetchWorkerDetails` as-is (idempotent).

**Step 3: Edit `openWorkerDetail` — add tier+model line and pack chips; drop the LangFuse button**

In `openWorkerDetail`, after the Description + meta block (the `Priority / Timeout / Max turns` row,
~line 199), insert a tier + model line:

```javascript
  // Tier + resolved model
  html += `<div style="display:flex;gap:12px;align-items:center;font-size:11px;color:var(--text-dim);margin-bottom:16px;">`;
  html += `<span class="pf-tier ${escapeHtml(w.tier || 'standard')}">${escapeHtml(w.tier || 'standard')}</span>`;
  html += `<span>Model: ${escapeHtml(w.model || '—')}</span>`;
  if ((w.packs || []).length) html += `<span>Packs: ${escapeHtml(w.packs.join(', '))}</span>`;
  html += `</div>`;
```

Then change the Actions footer (~line 252-256) from the LangFuse edit button to a plain Close:

```javascript
  // Actions
  modalActions.innerHTML = `<button class="btn" onclick="closeModal()">Close</button>`;
```

(Remove the `const lfPrompt = …` line and the `Edit Prompt in LangFuse` anchor entirely.)

**Step 4: Point the tab loader at `fetchWorkers`**

In `ui/task-board/js/app.js`, change both call sites:
- Line ~10: `if (tabName === 'engine') fetchPrompts();` → `if (tabName === 'engine') fetchWorkers();`
- Line ~26: `if (which === 'prompts') fetchPrompts();` → `if (which === 'prompts') fetchWorkers();`

**Step 5: Sanity-check for dangling references**

Run:
```bash
cd /Users/jayjenkins/dev/pm-os-team
grep -rn "fetchPrompts\|renderPrompts\|toggleSkillsList" ui/task-board/
node --check ui/task-board/js/agents.js && node --check ui/task-board/js/app.js
```
Expected: the grep returns **nothing** (no dangling callers); `node --check` prints nothing (valid
syntax). If `node` is unavailable, skip the `--check` and rely on Task 4's browser load.

**Step 6: Commit**

```bash
git add ui/task-board/js/agents.js ui/task-board/js/app.js
git commit -m "feat(phase-8): Workers & Prompts tab renders off /api/workers, no LangFuse

List + detail modal are file-backed read-only; tier badge, resolved model,
pack chips; infra-prompts and LangFuse sections removed from the tab.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Verify on the dev board (:8743)

No code; on-screen verification per the project's deliberate no-JS-harness posture.

**Step 1: Restart the dev server (loads `/api/*` fresh)**

```bash
cd /Users/jayjenkins/dev/pm-os-team
PID=$(lsof -ti :8743 -sTCP:LISTEN); [ -n "$PID" ] && ps -p $PID -o args= | grep -q "$(pwd)/scripts/task_server.py" && kill $PID
nohup python3 scripts/task_server.py > logs/devserver.log 2>&1 &
sleep 2 && curl -s localhost:8743/api/workers | python3 -m json.tool | head -30
```
Expected: JSON with worker objects carrying `tier`, `model`, `packs`. **Guard:** only kill a PID whose
`ps args` shows `scripts/task_server.py` under THIS repo — never the `:8742`/`~/pm-os` prod server.

**Step 2: Confirm the tab renders with LangFuse OFF**

Ensure `LANGFUSE_SECRET_KEY` is unset in the server env (default). The list must populate anyway
(that's the whole point).

**Step 3: Capture the Workers tab via Chrome headless**

Temporarily (uncommitted) inject before `</body>` in `ui/task-board/index.html`:
```html
<script>window.addEventListener("load",()=>setTimeout(()=>{try{switchTab("engine");switchEngine("prompts")}catch(e){}},600))</script>
```
Then:
```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --virtual-time-budget=3000 --dump-dom http://localhost:8743/ > /tmp/phase8-workers.html 2>/dev/null
grep -c "prompt-card" /tmp/phase8-workers.html        # expect 8 worker cards
grep -o "pf-tier [a-z]*" /tmp/phase8-workers.html | sort -u   # expect light/standard/deep
git checkout ui/task-board/index.html                  # revert the injection
```
Expected: 8 worker cards; tier classes present; no "No worker prompts registered" text; no
"Edit Prompt in LangFuse".

**Step 4: Spot-check the detail modal**

Optionally screenshot (not just dump-dom) to eyeball a card + open modal. Confirm the modal shows the
tier badge, Model line, Packs (for a worker that has them, e.g. researcher/product-analyst), Allowed
Tools, Skills (flat names), Matching Rules, the read-only prompt prose, and a single Close button.

**Step 5: Final gates**

Run: `python3 -m pytest -q && python3 scripts/card_schema.py`
Expected: all green.

No commit (verification only; the index.html injection was reverted).

---

## Done criteria

- `python3 -m pytest` green (≥ 211: baseline 209 + Task 1 + Task 2 tests), `card_schema.py` green.
- `/api/workers` returns `tier`/`model`/`packs` per worker; the tab renders 8 worker cards on `:8743`
  with LangFuse not running; modal is read-only with no LangFuse button.
- Then: superpowers:finishing-a-development-branch → open the Phase 8 PR against `main`.
