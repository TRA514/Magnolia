# Magnolia Phase 6 — Integrate the Returned Frontend (Design)

**Date:** 2026-06-06
**Status:** Design approved (brainstorm complete) — ready for implementation plan
**Branch:** `feat/phase-6-integrate-frontend`
**Builds on:** Phases 1–5 (PR #4 merged to `main` at `efc600d`)
**Master design:** `2026-06-05-pm-os-portability-design.md` §6 (declarative card registry / factory),
§9 (design system = card schema + theme tokens; the token-only HARD RULE), §11 step 6 (integrate
the returned frontend).
**Contract built against:** `2026-06-06-phase-5-designer-commission-brief.md` (the §8 API appendix is
the reconciliation map) and `2026-06-06-phase-5-ui-commission-design.md`.
**Returned design files:** `Magnolia - Foundation.zip` → `handoff/` (HTML/CSS/JS built against a mock API).

---

## What Phase 6 is

Build-sequence step 6. The designer returned drop-in HTML/JS/CSS for four surfaces, built against a
mock API (`mock-api.js`) and the existing theme-token contract. This phase reconciles the mock seams
against the real backend and lands the design natively in the live vanilla board at `ui/task-board/`.
**Evolve, don't rewrite** — no framework.

The operator (Jay) worked directly with the designer, so the returned files **represent the intended
implementation**. The job is faithful integration, not re-interpretation.

## Reconnaissance findings (what we're integrating)

The returned files were built **on top of the live board**, so fidelity is high and integration is
largely additive:

- **`card-registry.js`** keeps the exact slot order, signal predicates, and head/title/context markup;
  it **replaces the three placeholder body renderers** (`diff` / `preview` / `agreement`) with real
  ones, adds `KIND_META` (head labels *suggestion / handled / trust*), friendly tier words
  (`shadow`→"observe-only", etc.), and wires the action verbs through `cardAction`.
- **`tasks.js`** is the live modal file **plus** an additive card-action block: `cardAction`, inline-409
  notice helpers that survive the 15s auto-refresh (`window._pendingNotices` + `reapplyCardNotices`),
  `settleCard` (the gentle success beat), and `cardDismiss` (local "Not yet").
- **`now.js`** reuses `renderCard()`; lays out Suggestions (load-bearing, with an "all-clear" empty
  state) · Promotion Cycle (graduation) · Recently handled (receipts) · then the existing
  Decide/Review/People/Agent-queue lanes.
- **`magnolia.css`** is **token-clean**: zero raw color literals, transitions use `var(--ease)`, radii
  use the `--r-*` tokens (only layout px and 999px pills, which is normal CSS).
- **`registry.json` is unchanged and already correct**, so `card_schema.py`'s token-only validation
  stays green for free.

### The seams (all expected)

1. **Profile room backend doesn't exist.** `GET /api/profile`, the write endpoints, `doctor/fix`, and
   `system/restart` are mocked. `profile_lib.py` has read helpers + `read_capabilities()`/
   `write_capabilities()`; identity/voice/packs/posture writes are net-new. This is the phase's only
   substantial backend work.
2. **`receipt_summary`** — the receipt body renderer prefers it but **degrades gracefully** to the
   title (`title.replace(/^Applied:\s*/i, '')`). Optional backend polish, non-blocking.
3. **`/api/tasks` returns a bare array** in both the mock and the real server (`_json_response(handler,
   tasks)`). No seam — the brief's `{tasks:[]}` was already reconciled in the mock.

## Decisions (from brainstorm)

1. **Faithful adoption.** Land the design as built; change only what the real backend / file
   conventions require. The token-only rule stays green (registry.json untouched; CSS is token-clean).
2. **Voice stays split (two editors).** Verified load-bearing: `profile/voice/teams.md` +
   `profile/voice/email.md` are real files; `profile_lib.voice_text()` concatenates them; `judge.py`
   reads them; and **`meta-onboard/SKILL.md` drafts both files separately**. The designer's single
   combined editor is therefore adapted into **two stacked editors** (Teams, then Email), each with the
   mockup's big-field real estate, backed by the two files. No refactor of the voice model.
3. **System-status section cut.** Per operator: the §6.6 System section (server indicator + health
   summary + Restart) is expendable — removed from `profile.js` and from the `GET /api/profile`
   response. With it goes the `system/restart` endpoint.
4. **`doctor/fix` is guidance, not automation.** The two risky endpoints (auto-auth + server restart)
   are cut. Integration **status dots** still render from real capability data
   (`read_capabilities()`), and the degraded-feature pattern (the "Publishing to Jira is paused"
   locked control) stays — but the **Fix / Authorize** button surfaces the conversational Doctor ("run
   the Doctor in Claude Code") rather than calling a heal endpoint.
5. **Keep the "Synthwave" relabel** (Modafinil → Synthwave; id `modafinil` unchanged, file unchanged —
   nothing breaks). The 5 existing moods and the `task` card are preserved.
6. **New "Sunshine Daydream" mood** (`themes/sugarmagnolia.css`, id `sugarmagnolia`) registered **2nd**
   in the mood list, after Organic. Theme-scoped cosmetic overrides (the bloom `body::after`, the
   lightning-bolt `.leaf-mark`) live in the theme file — acceptable, since theme files are the token
   *source*, not card schemas.

## Sequence (four PR-able steps, risk-ascending)

### Step 1 — Foundation & theme
`index.html` (wordmark → **"Magnolia"**, tagline removed; `<link>`s for `magnolia.css` +
`sugarmagnolia.css`; Engine → Profile sub-nav markup; `<title>`), `themes.js` (Sunshine Daydream 2nd,
Synthwave relabel, favicon swap), `themes/sugarmagnolia.css`, `icons.js` (new glyphs: `spark`,
`receipt`, `ladder`, `patch`, `undo`, `arrowRight`), `css/magnolia.css`, and the `karesansui.css` /
`vantaca.css` `--text-dim` contrast nudges.
**Verify:** all 6 moods load, Sunshine Daydream appears 2nd, wordmark reads "Magnolia", the existing
board still renders unchanged. `card_schema.py` + pytest green.

### Step 2 — Card system
`card-registry.js` (3 kinds + `KIND_META` + tier words + action wiring), `tasks.js` card-action block,
`now.js` layout. `registry.json` already correct.
**Verify on dev :8743** with seeded fixture `.md` files (one per card_type/state, cleaned up after):
every card-shell state (default, hover, agent-running pulse, needs-human, complete, failed,
error/degraded, success-after-action) + the three kinds; accept → spawns receipt; prose-only accept →
calm inline 409; undo conflict → calm inline 409; graduate; "Not yet" local dismiss; acted-on cards
leave the board on refresh; the 409 notice survives the 15s auto-refresh. `card_schema.py` + pytest
green.

### Step 3 — Quality restyle
`quality.js` + its `magnolia.css` rules, against the **real** `GET /api/quality` (already returns
agreement %, real ladder `phase`, disagreements). Read-only surface — no actions.
**Verify:** trust badges map ladder tiers to friendly labels, sparklines/dimensions render, "no ratings
from you yet" path works when `agreement_pct` is null.

### Step 4 — Profile room (frontend + backend)
`profile.js` (five sections: Identity · Integrations · Voice (two editors) · Skill packs · Model
posture — **no System section**) + `app.js` `switchEngine` wiring.

New real backend endpoints in `task_server.py` (or a `profile_api` helper), all reading/writing through
`profile_lib`:
- `GET /api/profile` → identity (profile.yaml), integrations (integrations.yaml + capability **status**
  from `read_capabilities()`), voice (teams.md + email.md), packs (config.yaml), model_posture
  (config.yaml + per-worker tiers). **No `system` key.**
- `PUT /api/profile/identity` → write `profile.yaml`.
- `PUT /api/profile/voice` → write `voice/teams.md` and/or `voice/email.md` (payload `{teams, email}`).
- `POST /api/profile/integrations/{category}` → set active provider in `integrations.yaml`.
- `POST /api/profile/packs` → set active packs in `config.yaml`.
- `PUT /api/profile/model-posture` → set posture level in `config.yaml`.
- **Cut:** `POST /api/system/restart`, `POST /api/doctor/fix/{capability}` (Fix button → conversational
  Doctor guidance instead).

**Python tests** for every new endpoint (read shape + each write round-trips to the right file).
**Verify on :8743:** the room loads, each section saves and persists, the Jira degraded/locked pattern
shows when capabilities mark Jira unauthorized, the Fix button surfaces Doctor guidance.

## Out of scope (unchanged Phase 4/5 deferrals)

Dispatch-behavior enforcement of ladder tiers (gated hold-for-review, autonomous auto-complete);
task→transcript join (capture dispatch `session_id`); `description_patterns` ignored by the regex
worker-matcher; `ladder.json` single-writer concurrency. Also noted but not pulled in: scoping the
accept commit to the patch's files (today `git add -A` on a clean-tree assumption); emitting
`receipt_summary` from the backend (renderer degrades gracefully without it).

## Verification posture

No JS test harness (deliberate — Python repo). Each step is verified on-screen via Chrome.app headless
against the dev board on **:8743** (headless screenshot + `--dump-dom` of the post-JS DOM; seed fixture
task `.md` files with the right `card_type` to exercise variants, then clean up — `datasets/evals/
ladder.json` is gitignored runtime state). `python3 -m pytest` (144 passing at Phase 5 close) stays
green and grows with the new Profile endpoint tests. `python3 scripts/card_schema.py` must stay green
throughout (token-only rule).
