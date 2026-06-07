# Magnolia Phase 6 — Integrate the Returned Frontend — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Land the designer's returned drop-in HTML/CSS/JS natively in the live vanilla board at
`ui/task-board/`, reconciling the mock-API seams against the real backend, and build the real
Profile/Config endpoints.

**Architecture:** Four sequential, independently-verifiable stages (Foundation+theme → Card system →
Quality restyle → Profile room+backend). Frontend is *evolved* in place (no framework): returned files
are diffed against the live board and adopted faithfully, with three deliberate adaptations (two-file
Voice, no System section, doctor/fix as conversational guidance). Backend adds real Profile endpoints
backed by `profile_lib` with full pytest coverage.

**Tech Stack:** Vanilla HTML/CSS/JS (token-driven theme system), Python `http.server` (`task_server.py`),
`ruamel.yaml`, pytest. Verification via Chrome.app headless against dev board on **:8743** (no JS test
harness — deliberate).

**Design doc:** `docs/plans/2026-06-06-phase-6-integrate-frontend-design.md`
**Contract:** `docs/plans/2026-06-06-phase-5-designer-commission-brief.md` (§8 API appendix = reconciliation map)

---

## Conventions for every task

- **Returned design files** live in the handoff bundle. **Task 0 stages them** to a stable path; all
  later tasks reference `$DESIGN/` = `/tmp/magnolia-design/handoff/`.
- **Live board** is `ui/task-board/`. **Never overwrite `index.html` wholesale** — apply targeted
  edits (it carries a large inline `<style>` block and the live structure).
- **Do NOT copy `mock-api.js`** into the repo — it is the review harness only.
- Set git author once at the start: `git config user.email "11728296+jayhjenkins@users.noreply.github.com"`
  and `git config user.name "Jay Jenkins"`.
- **Green-bar gates** that must pass before every commit: `python3 -m pytest -q` and
  `python3 scripts/card_schema.py`.
- **pip** (PEP-668): `pip install --break-system-packages` if a dep is missing.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Frontend verification** (no unit tests): start the dev board, drive Chrome.app headless, and inspect
  the post-JS DOM. Reusable commands in the Appendix.

---

## Task 0: Stage the design bundle + baseline snapshot

**Files:** none committed (staging only).

**Step 1: Unzip the returned design to the working path**

```bash
mkdir -p /tmp/magnolia-design && cd /tmp/magnolia-design
unzip -o "$HOME/Downloads/Magnolia - Foundation.zip"
ls /tmp/magnolia-design/handoff/   # expect: index.html, css/, js/, themes/, *.md
```

**Step 2: Confirm the green baseline before touching anything**

```bash
cd ~/dev/pm-os-team
python3 -m pytest -q                 # expect: 144 passed
python3 scripts/card_schema.py       # expect: OK / exit 0
```

Expected: 144 passing, card_schema OK. If not, STOP and report — do not build on a red baseline.

**Step 3: Capture a pre-change screenshot of the live board** (for before/after comparison)

Start the board (Appendix A), then run Appendix B against `Now` and `Engine`. Save under
`/tmp/magnolia-shots/00-before-*.png`. No commit.

---

## Task 1 — STAGE 1: Foundation & theme

Establishes the styling substrate + the new mood + the wordmark. Low risk, no behavior change to the
existing board. **Branch already:** `feat/phase-6-integrate-frontend`.

### Task 1.1: Drop in the new stylesheet, theme, and icons

**Files:**
- Create: `ui/task-board/css/magnolia.css` (from `$DESIGN/css/magnolia.css`)
- Create: `ui/task-board/themes/sugarmagnolia.css` (from `$DESIGN/themes/sugarmagnolia.css`)
- Replace: `ui/task-board/js/icons.js` (from `$DESIGN/js/icons.js`)

**Step 1: Confirm `icons.js` is a superset of the live one** (additive only)

```bash
diff <(grep -oE '^\s+[a-zA-Z]+:' ui/task-board/js/icons.js) \
     <(grep -oE '^\s+[a-zA-Z]+:' /tmp/magnolia-design/handoff/js/icons.js)
```
Expected: the returned file ADDS `spark, receipt, ladder, patch, undo, arrowRight` and keeps all
existing glyphs. If any existing glyph is missing, reconcile (keep both) rather than dropping.

**Step 2: Copy the three files in**

```bash
cp /tmp/magnolia-design/handoff/css/magnolia.css      ui/task-board/css/magnolia.css
cp /tmp/magnolia-design/handoff/themes/sugarmagnolia.css ui/task-board/themes/sugarmagnolia.css
cp /tmp/magnolia-design/handoff/js/icons.js           ui/task-board/js/icons.js
```

**Step 3: Verify magnolia.css is token-clean** (the §9 hard rule extends to returned CSS)

```bash
grep -nE '#[0-9a-fA-F]{3,8}|rgba?\([0-9]|oklch\(' ui/task-board/css/magnolia.css
```
Expected: NO output (zero raw color literals). Layout px / `999px` pills / `50%` circles are fine.

**Step 4: Commit**

```bash
git add ui/task-board/css/magnolia.css ui/task-board/themes/sugarmagnolia.css ui/task-board/js/icons.js
git commit -m "feat(phase-6): add magnolia.css, Sunshine Daydream theme, new card-kind icons"
```

### Task 1.2: Wire index.html (wordmark, links, title, Engine sub-nav)

**Files:**
- Modify: `ui/task-board/index.html`

**Step 1: Diff the returned index.html against live to enumerate the exact deltas**

```bash
diff ui/task-board/index.html /tmp/magnolia-design/handoff/index.html | head -120
```
Read the diff. The intended changes are: (a) `<title>` → "Magnolia"; (b) wordmark text → "Magnolia",
tagline/`.h1-sub` removed; (c) add `<link rel="stylesheet" href="/css/magnolia.css">` and
`<link rel="stylesheet" href="/themes/sugarmagnolia.css">` in `<head>`; (d) Engine tab → Profile
sub-nav markup + a `#profile-view` container; (e) any `<script src>` for `profile.js`.

**Step 2: Apply ONLY those deltas to the live index.html** (targeted edits; preserve the live inline
`<style>` block and all existing structure). For the Engine sub-nav, mirror the returned markup: a
sub-tab strip inside the Engine tab switching between the existing prompts/workers view and a new
`<div id="profile-view" class="profile-view">`. Add `<script src="/js/profile.js"></script>` near the
other module scripts.

**Step 3: Verify the head links + wordmark + scripts are present**

```bash
grep -nE 'magnolia\.css|sugarmagnolia\.css|profile\.js|<title>|profile-view' ui/task-board/index.html
```
Expected: all five present; `<title>` reads Magnolia.

**Step 4: Verify on screen** — start board (Appendix A), screenshot `Now` (Appendix B). Confirm the
top-left wordmark reads **"Magnolia"** and the board renders unchanged otherwise. Save
`/tmp/magnolia-shots/01-wordmark.png` and eyeball it.

**Step 5: Commit**

```bash
git add ui/task-board/index.html
git commit -m "feat(phase-6): wordmark → Magnolia, link magnolia.css + sugarmagnolia, Engine→Profile sub-nav"
```

### Task 1.3: Register the moods (Sunshine Daydream 2nd, Synthwave relabel) + contrast nudges

**Files:**
- Replace: `ui/task-board/js/themes.js` (from `$DESIGN/js/themes.js`)
- Modify: `ui/task-board/themes/karesansui.css`, `ui/task-board/themes/vantaca.css` (`--text-dim` nudge)

**Step 1: Confirm the returned themes.js preserves all 5 existing mood ids**

```bash
grep -oE "id: '[a-z]+'" /tmp/magnolia-design/handoff/js/themes.js
```
Expected order: `organic, sugarmagnolia, modafinil, breathe, karesansui, vantaca`. The `modafinil` **id
is unchanged** (only its label becomes "Synthwave"). If any of organic/modafinil/breathe/karesansui/
vantaca is missing, STOP.

**Step 2: Copy themes.js in**

```bash
cp /tmp/magnolia-design/handoff/js/themes.js ui/task-board/js/themes.js
```

**Step 3: Apply the `--text-dim` contrast nudges** — diff the two theme files and apply only the
`--text-dim` change (darker, for AA contrast on the light surfaces):

```bash
diff ui/task-board/themes/karesansui.css /tmp/magnolia-design/handoff/themes/karesansui.css
diff ui/task-board/themes/vantaca.css    /tmp/magnolia-design/handoff/themes/vantaca.css
```
Apply only the `--text-dim:` line change in each (ignore any unrelated drift).

**Step 4: Verify all 6 moods load and Sunshine Daydream is 2nd**

Start board (Appendix A). Drive the mood menu via headless DOM dump (Appendix C) and assert the mood
option order. Then switch to `sugarmagnolia` (set `localStorage 'pmos-mood'`) and screenshot `Now` to
confirm the sunburst background + lightning-bolt mark render. Save `/tmp/magnolia-shots/02-sunshine.png`.

**Step 5: card_schema + pytest still green**

```bash
python3 scripts/card_schema.py && python3 -m pytest -q
```
Expected: OK + 144 passed (no Python touched yet, but confirm nothing regressed).

**Step 6: Commit**

```bash
git add ui/task-board/js/themes.js ui/task-board/themes/karesansui.css ui/task-board/themes/vantaca.css
git commit -m "feat(phase-6): register Sunshine Daydream (2nd), relabel Modafinil→Synthwave, AA contrast nudges"
```

### Task 1.4: Stage 1 review checkpoint

Request code review (spec-compliance then code-quality) on the Stage 1 diff before moving on.
Verify: wordmark, 6 moods with Sunshine Daydream 2nd, token-clean CSS, board otherwise unchanged.

---

## Task 2 — STAGE 2: Card system (registry kinds, actions, Now layout)

The coupled drop: the three new card kinds, their action wiring + inline-409 handling, and the new Now
layout. `registry.json` is already correct (no change). **This is rendering only — backend handler
contracts are untouched** (accept/reject/keep/undo/graduate/react already exist).

### Task 2.1: Adopt card-registry.js (3 kinds) + tasks.js (card actions)

**Files:**
- Replace: `ui/task-board/js/card-registry.js` (from `$DESIGN/js/card-registry.js`)
- Replace: `ui/task-board/js/tasks.js` (from `$DESIGN/js/tasks.js`)

**Step 1: Confirm both returned files are supersets of live** (the designer built on the live code)

```bash
# card-registry: the new bodyRenderers + KIND_META + tier words are ADDED; slot/signal logic unchanged.
diff ui/task-board/js/card-registry.js /tmp/magnolia-design/handoff/js/card-registry.js | head -80
# tasks.js: the live modal (openTask, schedule/message/jira/pipeline) is intact; a cardAction block is ADDED.
diff ui/task-board/js/tasks.js /tmp/magnolia-design/handoff/js/tasks.js | head -120
```
Read both diffs. Confirm: no live function is removed; only additive changes + the placeholder
bodyRenderers (`diff`/`preview`/`agreement`) are upgraded. If a live behavior would be lost, reconcile
manually instead of blind-copying.

**Step 2: Copy both files in**

```bash
cp /tmp/magnolia-design/handoff/js/card-registry.js ui/task-board/js/card-registry.js
cp /tmp/magnolia-design/handoff/js/tasks.js          ui/task-board/js/tasks.js
```

**Step 3: card_schema still green** (registry.json unchanged, but the renderer names must match)

```bash
python3 scripts/card_schema.py
```
Expected: OK. (Validates `registry.json` against theme tokens + body renderer names.)

**Step 4: Commit**

```bash
git add ui/task-board/js/card-registry.js ui/task-board/js/tasks.js
git commit -m "feat(phase-6): real recommendation/receipt/graduation card bodies + inline-409 card actions"
```

### Task 2.2: Adopt the new Now layout

**Files:**
- Replace: `ui/task-board/js/now.js` (from `$DESIGN/js/now.js`)

**Step 1: Diff to confirm it reuses `renderCard` / `deriveAttentionState`** (no new globals required)

```bash
diff ui/task-board/js/now.js /tmp/magnolia-design/handoff/js/now.js
grep -nE 'renderCard|deriveAttentionState|reapplyCardNotices' /tmp/magnolia-design/handoff/js/now.js
```
Confirm `deriveAttentionState` exists in the live board (it's referenced). If the live board's lane
function has a different name, reconcile the call site.

**Step 2: Copy now.js in**

```bash
cp /tmp/magnolia-design/handoff/js/now.js ui/task-board/js/now.js
```

**Step 3: Commit**

```bash
git add ui/task-board/js/now.js
git commit -m "feat(phase-6): Now layout — Suggestions/Promotion/Recently-handled + all-clear empty state"
```

### Task 2.3: Verify every card state with seeded fixtures

**Files:**
- Temp fixtures: `datasets/tasks/agent/TASK-90*.md` etc. (created then deleted — DO NOT COMMIT)

**Step 1: Seed one fixture task per kind/state** to exercise variants. Create fixture `.md` files with
the right frontmatter (`card_type`, `agent_status`, `patch_path`, `grad_*`, `revert_commit`,
`source_recommendation`) mirroring the mock seed in `$DESIGN/js/mock-api.js` (`TASKS` array) — use it
as the field reference. Cover:
- recommendation **with** `patch_path`, recommendation **prose-only** (no patch_path)
- receipt with `undo_conflicts`-style conflict target, receipt clean
- graduation (`grad_*` populated)
- task cards with `agent_status` = running / needs-human / complete / failed / null

**Step 2: Start the board (Appendix A) and screenshot Now + the gallery states** (Appendix B).
Confirm visually:
- recommendation/receipt/graduation render with real bodies + KIND_META head labels (suggestion/
  handled/trust)
- agent-running shows the pulse (not a spinner), needs-human/complete/failed marks are calm
- the Suggestions empty state shows "all caught up" when no recommendations exist

**Step 3: Exercise the action loop against the REAL backend.** With a real recommendation fixture
(with a tiny valid `.patch`), click Accept → confirm a receipt appears and the recommendation leaves.
With a prose-only recommendation, click Accept → confirm the **calm inline 409** ("apply by hand…")
appears AND survives a 15s auto-refresh (the notice re-applies). Click Undo on a conflicting receipt →
confirm the inline 409. Click Graduate → card leaves. Click "Not yet" → card settles locally.

> Drive clicks via the headless DOM (Appendix C) or document the manual click-through with screenshots
> at `/tmp/magnolia-shots/2x-*.png`. The board refresh (no toast) IS the success signal.

**Step 4: Clean up fixtures**

```bash
rm -f datasets/tasks/*/TASK-90*.md
git status --short   # expect: clean (no fixture files staged)
```

**Step 5: card_schema + pytest green**

```bash
python3 scripts/card_schema.py && python3 -m pytest -q
```

### Task 2.4: Stage 2 review checkpoint

Request code review on the Stage 2 diff (spec-compliance: all §4 states + §5 kinds + 409 behavior;
code-quality: no dead code, faithful to live conventions).

---

## Task 3 — STAGE 3: Quality trust dashboard restyle

Read-only restyle against the **real** `GET /api/quality` (already returns `groups` with `phase`,
`agreement_pct`, `disagreements`).

### Task 3.1: Adopt quality.js

**Files:**
- Replace: `ui/task-board/js/quality.js` (from `$DESIGN/js/quality.js`)

**Step 1: Diff + confirm it reads the same `/api/quality` shape** (no new endpoint)

```bash
diff ui/task-board/js/quality.js /tmp/magnolia-design/handoff/js/quality.js | head -120
grep -nE "/api/quality|agreement_pct|phase|disagreements|history|dimensions" /tmp/magnolia-design/handoff/js/quality.js
```
Confirm field names match `build_quality`'s output (run `python3 -c "import sys;sys.path.insert(0,'scripts');import task_server,json;print(json.dumps(task_server.build_quality(),indent=2)[:800])"` if needed).

**Step 2: Copy quality.js in**

```bash
cp /tmp/magnolia-design/handoff/js/quality.js ui/task-board/js/quality.js
```

**Step 3: Verify on screen** — open the Quality tab (Appendix B against `Quality`). Confirm: trust
badges map tiers → friendly labels (observe-only / gated / autonomous / trusted), sparklines +
per-dimension averages render, and a group with `agreement_pct: null` shows "no ratings from you yet".
Save `/tmp/magnolia-shots/03-quality.png`.

**Step 4: Green gates + commit**

```bash
python3 scripts/card_schema.py && python3 -m pytest -q
git add ui/task-board/js/quality.js
git commit -m "feat(phase-6): restyle Quality into a calm read-only trust dashboard"
```

### Task 3.2: Stage 3 review checkpoint

Quick review — data unchanged, presentation only; confirm null-agreement path and tier-label mapping.

---

## Task 4 — STAGE 4: Profile / Config room (frontend + real backend)

The net-new surface. **Adaptations from the mock:** (a) Voice = **two** stacked editors (Teams, Email)
backed by `voice/teams.md` + `voice/email.md`; (b) **no System-status section**; (c) the Fix/Authorize
button surfaces conversational-Doctor guidance (no `doctor/fix` or `system/restart` endpoint).

Backend is built **TDD-first** (pure functions in `profile_lib` + `build_profile` in `task_server`,
tested via the `profile_root` fixture), then wired to routes.

### Task 4.1: profile_lib write helpers (TDD)

**Files:**
- Modify: `scripts/profile_lib.py`
- Test: `tests/test_profile_lib.py`

**Step 1: Write failing tests** for round-tripping writes (use the existing `profile_root` fixture):

```python
def test_write_identity_roundtrips(profile_root):
    profile_lib.write_identity({"display_name": "Jay", "email": "jay@v.com",
                                "company": "Vantaca", "timezone": "America/Chicago"},
                               root=profile_root)
    p = profile_lib.profile(root=profile_root)
    assert p["display_name"] == "Jay" and p["company"] == "Vantaca"
    assert p["persona"] == "pm"           # untouched field preserved

def test_write_voice_per_channel(profile_root):
    profile_lib.write_voice("teams", "tight and lowercase", root=profile_root)
    assert "tight and lowercase" in profile_lib.voice_text("teams", root=profile_root)
    assert "Warm" in profile_lib.voice_text("email", root=profile_root)   # other channel untouched

def test_set_integration_provider(profile_root):
    profile_lib.set_integration_provider("transcript", "otter", root=profile_root)
    assert profile_lib.provider("transcript", root=profile_root) == "otter"

def test_set_active_packs(profile_root):
    profile_lib.set_active_packs(["core", "exec"], root=profile_root)
    assert profile_lib.config(root=profile_root)["active_skill_packs"] == ["core", "exec"]

def test_set_cost_posture(profile_root):
    profile_lib.set_cost_posture("high", root=profile_root)
    assert profile_lib.config(root=profile_root)["models"]["cost_posture"] == "high"
```

**Step 2: Run → confirm they fail** (`AttributeError: module has no attribute 'write_identity'`).

```bash
python3 -m pytest tests/test_profile_lib.py -q -k "write or set_"
```

**Step 3: Implement the write helpers** using a **round-trip** YAML (preserve comments). Add a
module-level `_yaml_rt = YAML()` (round-trip) and a `_load_rt(name, root)` / `_dump_rt(name, data, root)`
pair that reads with the rt loader and writes atomically (mkstemp + os.replace, like `write_capabilities`).
Each setter loads the doc, mutates the one key, writes back:
- `write_identity(data, root=None)` — update display_name/email/company/timezone in `profile.yaml`,
  leaving `persona` and any other keys intact.
- `write_voice(channel, text, root=None)` — write `voice/{channel}.md` atomically (channel in
  `{teams, email}`).
- `set_integration_provider(category, provider, root=None)` — set
  `integrations.yaml[category]["provider"]`.
- `set_active_packs(packs, root=None)` — set `config.yaml["active_skill_packs"]`.
- `set_cost_posture(level, root=None)` — set `config.yaml["models"]["cost_posture"]`.

**Step 4: Run → all green**

```bash
python3 -m pytest tests/test_profile_lib.py -q
```

**Step 5: Commit**

```bash
git add scripts/profile_lib.py tests/test_profile_lib.py
git commit -m "feat(phase-6): profile_lib write helpers (identity/voice/integration/packs/posture) + tests"
```

### Task 4.2: `build_profile()` assembler (TDD)

**Files:**
- Modify: `scripts/task_server.py` (add `build_profile(root=None)` near `build_quality`)
- Test: `tests/test_profile_api.py` (new)

**Step 1: Write failing tests** for the assembled GET shape (no `system` key):

```python
def test_build_profile_shape(profile_root):
    import task_server
    p = task_server.build_profile(root=profile_root)
    assert p["identity"]["name"] == "Test User"
    assert "system" not in p                       # System section is cut
    # integrations grouped by category with an active provider + options w/ status dots
    pm = p["integrations"]["project_management"]
    assert pm["active"] == "jira"
    assert any(o["id"] == "jira" for o in pm["options"])
    assert all("status" in o for o in pm["options"])
    # voice is the two channels, read from the md files
    assert "Tight" in p["voice"]["teams"] and "Warm" in p["voice"]["email"]
    # packs + posture from config
    assert "core" in p["packs"]["active"]
    assert p["model_posture"]["level"] == "balanced"

def test_build_profile_status_from_capabilities(profile_root):
    import task_server, profile_lib
    profile_lib.write_capabilities(
        {"capabilities": {"jira": {"status": "reauth"}}}, root=profile_root)
    p = task_server.build_profile(root=profile_root)
    jira = next(o for o in p["integrations"]["project_management"]["options"] if o["id"] == "jira")
    assert jira["status"] == "reauth"
```

**Step 2: Run → confirm fail.**

```bash
python3 -m pytest tests/test_profile_api.py -q
```

**Step 3: Inspect the capability vocabulary** so the status mapping is honest:

```bash
sed -n '1,40p' tests/test_capabilities.py; grep -nE "status|capabilit" scripts/doctor.py | head
```
Note the capability key names + status strings the Doctor writes (e.g. `ok|reauth|unset`). Map provider
ids → capability keys accordingly.

**Step 4: Implement `build_profile(root=None)`** assembling, from `profile_lib`:
- `identity`: `{name, email, company, timezone}` from `profile.yaml`.
- `integrations`: three categories (`transcripts`, `project_management`, `calendar`) each
  `{label, active, options:[{id,label,status,detail}]}`. `active` = configured provider from
  `integrations.yaml`. `options` = the known adapters per category (transcripts: otter/granola;
  project_management: jira/asana/linear; calendar: m365/google). `status` per option from
  `read_capabilities()` if an entry exists (`ok|reauth|unset`), else `ok` when it's the active
  configured provider, else `available`.
- `voice`: `{teams, email}` via `voice_text("teams")` / `voice_text("email")`.
- `packs`: `{active: config.active_skill_packs, available: PACK_CATALOG}` (define a small static
  `PACK_CATALOG` of `{id,label,description}` for the known packs — core/pm/exec/eng/recruiting).
- `model_posture`: `{level: config.models.cost_posture, workers:[{name, tier}]}` where `workers` is
  derived from `scripts/workers/*.md` frontmatter (`model`/`tier` field) when present; empty list if
  none declare one. **No `system` key.**

**Step 5: Run → green.**

```bash
python3 -m pytest tests/test_profile_api.py -q
```

**Step 6: Commit**

```bash
git add scripts/task_server.py tests/test_profile_api.py
git commit -m "feat(phase-6): build_profile() assembler for GET /api/profile (no system section)"
```

### Task 4.3: Wire the Profile HTTP routes (TDD via handler-level tests)

**Files:**
- Modify: `scripts/task_server.py` (`_route_request` + new handler functions)
- Test: `tests/test_profile_api.py`

**Step 1: Write failing tests** that drive the handlers. Follow the existing handler-test style; if the
repo lacks a request-fixture, test the small handler helpers directly (a `handle_get_profile`,
`handle_put_identity(payload, root)`, etc. that return `(status, body_dict)` and are wrapped by the
HTTP layer). Tests assert: GET returns the `build_profile` shape; PUT identity persists; PUT voice
writes the right channel file; POST integrations sets the provider; POST packs sets packs; PUT
model-posture sets posture. Also assert that `POST /api/system/restart` and `POST /api/doctor/fix/*`
are **NOT routed** (return 404) — they were cut.

**Step 2: Run → fail.**

**Step 3: Implement** the routes in `_route_request` (mirror the existing `re.match` style):
- `GET  /api/profile` → `build_profile()`
- `PUT  /api/profile/identity` → `profile_lib.write_identity(payload)`
- `PUT  /api/profile/voice` → for each of `teams`/`email` present in payload, `write_voice(ch, text)`
- `POST /api/profile/integrations/{category}` → `set_integration_provider(category, payload["active"])`
- `POST /api/profile/packs` → `set_active_packs(payload["active"])`
- `PUT  /api/profile/model-posture` → `set_cost_posture(payload["level"])`
- Each returns `{"ok": true, ...}`. Do **not** add `system/restart` or `doctor/fix`.

**Step 4: Run → green; full suite green.**

```bash
python3 -m pytest -q
```

**Step 5: Commit**

```bash
git add scripts/task_server.py tests/test_profile_api.py
git commit -m "feat(phase-6): real Profile HTTP endpoints (GET + identity/voice/integrations/packs/posture)"
```

### Task 4.4: Adopt profile.js with the three adaptations + app.js wiring

**Files:**
- Create: `ui/task-board/js/profile.js` (from `$DESIGN/js/profile.js`, adapted)
- Modify: `ui/task-board/js/app.js` (Engine→Profile `switchEngine` wiring, from `$DESIGN/js/app.js` diff)

**Step 1: Copy profile.js in, then apply the three adaptations:**
1. **Voice → two editors.** Replace `_pfVoice` (single combined textarea) with **two** stacked
   `pf-section` voice blocks — "Teams voice" then "Email voice" — each a full-width `pf-voice-text`
   textarea with the same big-field styling, intro line, Save + "Regenerate from history" affordance.
   `pfSaveVoice()` → `PUT /api/profile/voice` with `{teams, email}` read from the two textareas.
2. **Cut System.** Remove the `_pfSystem(...)` call from `_profileHtml`, and delete `_pfSystem` +
   `pfRestart`.
3. **Fix button = guidance.** In `pfFix(capability)`, replace the `fetch('/api/doctor/fix/…')` with a
   calm inline note appended to the control: *"To reconnect {Jira}, run the Doctor in Claude Code — type
   `fix {jira}`. Magnolia will walk you through it."* (no network call). Keep the status dots + the
   degraded `pf-locked` pattern exactly.

**Step 2: Wire app.js** — diff `$DESIGN/js/app.js` vs live and apply the `switchEngine` (or equivalent)
addition that toggles the Engine sub-views and calls `renderProfile()` when the Profile sub-tab opens.
Confirm `renderProfile` is invoked on first open.

```bash
diff ui/task-board/js/app.js /tmp/magnolia-design/handoff/js/app.js
```

**Step 3: Verify on screen** — start board (Appendix A), open Engine → Profile (Appendix C to click the
sub-tab, or set the view active). Confirm the **five** sections render (Identity, Integrations, Voice ×2,
Skill packs, Model posture), **no System section**, the Jira degraded/locked control shows when
capabilities mark Jira `reauth`, and the Fix button shows the guidance note (no failed network call in
the console). Edit Identity → Save → reload → persists. Edit a Voice box → Save → reload → persists.
Save `/tmp/magnolia-shots/04-profile.png`.

**Step 4: Green gates + commit**

```bash
python3 scripts/card_schema.py && python3 -m pytest -q
git add ui/task-board/js/profile.js ui/task-board/js/app.js
git commit -m "feat(phase-6): Profile room — two-file Voice, System section cut, Fix→Doctor guidance"
```

### Task 4.5: Stage 4 review checkpoint

Full review: spec-compliance (five sections, two-file voice round-trips to the right files, no System,
no doctor/fix or system/restart routes, degraded pattern intact) then code-quality.

---

## Task 5: Finish the branch

**Step 1: Full green sweep**

```bash
python3 -m pytest -q                 # all passing (144 + new profile tests)
python3 scripts/card_schema.py       # OK
git status --short                   # clean — no stray fixtures, no mock-api.js committed
grep -rn "mock-api" ui/task-board/ || echo "no mock shipped — good"
```

**Step 2: Final on-screen pass** across all six moods (esp. Sunshine Daydream) on Now / Quality /
Profile — confirm the design reads calmly everywhere and the token system carries every mood.

**Step 3:** Invoke `superpowers:finishing-a-development-branch` to choose merge/PR. Open a PR to `main`
summarizing the four stages, the three adaptations, and the deferred items (receipt_summary backend
emit; accept-commit file scoping).

---

## Appendix A — Start the dev board on :8743

```bash
cd ~/dev/pm-os-team
# Serve the live board via the task server (reads server.port=8743 from profile/config.yaml)
python3 scripts/task_server.py >/tmp/magnolia-board.log 2>&1 &
sleep 1 && curl -s localhost:8743/api/tasks >/dev/null && echo "board up on :8743"
```
> Do NOT touch the production board on :8742. Kill this dev server when done: `pkill -f task_server.py`
> (verify it's the :8743 instance first).

## Appendix B — Headless screenshot of a tab

```bash
SHOT=/tmp/magnolia-shots; mkdir -p $SHOT
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --window-size=1440,2200 --screenshot=$SHOT/<name>.png \
  "http://localhost:8743/#<tab>"     # tabs: now, board, activity, quality, engine
open $SHOT/<name>.png   # eyeball it
```

## Appendix C — Dump the post-JS DOM (assert structure / drive clicks)

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --dump-dom "http://localhost:8743/#now" \
  | grep -oE 'mood-option-name">[^<]+|card-kind-label[^>]*>[^<]+|now-section-name">[^<]+'
```
For interaction flows that need real clicks (Accept→receipt, 409 survival), prefer a short manual
click-through with screenshots, since the headless `--dump-dom` is a single static snapshot.
