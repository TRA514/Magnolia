# Magnolia Phase 8 — Workers & Prompts, reconciled off LangFuse → file-backed (Design)

**Date:** 2026-06-07
**Status:** Design approved (brainstorm complete) — ready for implementation plan
**Branch:** `feat/phase-8-workers-prompts-filebacked`
**Builds on:** Phases 1–7 (PRs #5–#10 merged to `main` at `6075a37`)
**Master design:** `2026-06-05-pm-os-portability-design.md` §5 (eval & judge substrate — LangFuse is a
silent power-user opt-in, never required; Docker LangFuse dropped). **Mirrors:**
`2026-06-06-phase-6-integrate-frontend-design.md` (the Profile room: file-backed, Docker-free,
gracefully-degrading config surface) and `2026-06-07-phase-7-packs-tiering-design.md` (worker tiers,
`resolve_model`, `packs_lib`).

---

## What Phase 8 is

The Engine → **Workers & Prompts** tab is the last surface still coupled to the dropped Docker
LangFuse stack. `fetchPrompts()` (`agents.js`) hits `GET /api/langfuse/prompts` +
`/api/langfuse/traces/stats`; without the stack those return `{prompts:[], error:"LangFuse not
available"}`, so `renderPrompts` shows *"No worker prompts registered. Run: python3
scripts/langfuse_setup.py"* — i.e. **the tab is empty for every non-technical teammate**, and points
them at a tool that no longer exists. This contradicts §5.

The file truth already exists: `GET /api/workers` (`task_server.py:1625`) parses all 8
`scripts/workers/*.md` (name, description, priority, match, allowed_tools, skills, langfuse_prompt,
timeout, max_turns, prompt_body), and the worker-detail modal already uses it. Phase 8 moves the
**list** off LangFuse onto `/api/workers`, surfaces the Phase-7 additions (tier, resolved model, pack
membership), and makes the tab a **read-only inspector** that renders with no Docker.

This is a reconcile, not a rewrite. Single PR off `main`.

## Decisions (from brainstorm)

1. **Read-only inspector**, not an editor. The list + detail render fully off `/api/workers`; there is
   no write-back path. Editing worker `.md` happens by hand or via the Phase-9 factory. Matches "git
   is the version history"; smallest, lowest-risk PR; zero new write endpoints.
2. **Cut the Infrastructure-prompts section.** `task-parser` / `cron-parser` are inline strings in
   `scripts/parse_*.py`, not files; they are dropped from the tab. The tab becomes a Workers
   inspector. (Power users still edit those prompts in the `.py` files.)
3. **Cut LangFuse from this tab entirely.** No trace success-rate UI here; the tab is 100%
   file-backed. LangFuse remains a silent global opt-in elsewhere (the top-bar health dot and the
   per-task trace viewer are separate features and stay).
4. **Absorb tier + resolved model + pack membership into `/api/workers`** (server-side join), so the
   frontend does one fetch and the join logic lives where `build_profile` already computes it.
5. **Fix the stale worker skill names (nested → flat).** Required to make the pack join trustworthy;
   also repairs a latent dispatch-scoping no-op. Verified safe (see below).

## Reconnaissance findings (what makes this safe)

**The skill-name staleness.** Worker `.md` files declare `skills:` in a **stale nested layout**
(`workflows/prd-creation`, `context-assembly/research-gathering`, `quality-gates/citation-compliance`,
`task-management/task-update`) but the repo went **flat** (`.claude/CLAUDE.md`: "flat — one level
deep"); real folders / `packs.yaml` use flat prefixed names (`workflow-prd-creation`,
`context-research-gathering`, `quality-citation-compliance`, `task-update`). Consequences:

- A naive `worker.skills ∩ pack.skills` join returns **mostly empty** — hence the name fix is a
  prerequisite for showing pack membership at all.
- **`build_skills_catalog_filtered` (`task_dispatch.py:487`) silently fails** for nested names:
  `os.path.join(skills_dir, "workflows/prd-creation", "SKILL.md")` doesn't exist → no match → it falls
  through to the **full** pack-gated catalog (line 512). So today `researcher`, `scheduler`, and
  `product-analyst` get the *whole* catalog instead of their curated allowlist. Renaming **repairs**
  this. The catalog is advisory prompt text (not a hard tool gate), so the behavior change is soft and
  matches author intent.

**Blast-radius sweep (the fix is safe):**

- All 33 unique nested names across `researcher` (8), `scheduler` (3), `product-analyst` (30 — overlap
  deduped) map **deterministically to exactly one existing flat folder**. Zero unresolved.
- **No code outside worker `.md` consumes nested skill names.** `langfuse_setup.py` only records
  `skills` as prompt metadata (a LangFuse-only path; harmless if renamed).
- **No test hardcodes nested skill paths.** Baseline `python3 -m pytest` = **209 passed**; the rename
  does not break them.
- `eval-analyst` and `ticket-creator` already use flat names; `_default`, `grad-assessor`,
  `message-writer` have no `skills:` (full catalog, unchanged).
- **Out of scope (flagged, not pulled in):** `scripts/task-extract-meetings.sh:87` references a
  separate stale path `.claude/skills/task-management/task-extract-from-meeting/SKILL.md`.

## Design

### Section 1 — Backend: enrich `GET /api/workers`

`handle_list_workers` (`task_server.py:1625`) gains three fields per worker, computed server-side:

- `tier` — worker frontmatter (`fm.get("tier")`; `load_workers` already parses it).
- `model` — `profile_lib.resolve_model(tier, posture=current_posture)`, where `current_posture` comes
  from `config.yaml` (the same source `build_profile` reads:
  `(cfg.get("models") or {}).get("cost_posture") or "balanced"`).
- `packs` — `[pack_id for pid, spec in packs_lib.load_packs() if set(worker.skills) & set(spec.skills)]`.
  Reliable because of Section 3. Workers with no skills → `[]`.

One endpoint, one fetch; both list and modal read it. Degrades: missing tier → `resolve_model`
already defaults to `standard`; missing/malformed `packs.yaml` → `load_packs()` returns `{}` → `[]`.

### Section 2 — Frontend: rewrite the tab off file truth (`js/agents.js`)

- **Delete** `fetchPrompts`, `renderPrompts`, `toggleSkillsList` (LangFuse list + infra-prompts +
  skills sections — all cut).
- **Add** `fetchWorkers()` → `GET /api/workers` → `renderWorkers()`: one card per worker showing name,
  **tier badge** (reuse the `.pf-tier` styling from `profile.js`), **resolved model**, one-line
  description, and a compact tool/pack hint. Card click → existing `openWorkerDetail`.
- **`openWorkerDetail`** (already file-backed via `/api/workers`): add a **tier + resolved-model line**
  and a **pack-chips row**; **remove** the "Edit Prompt in LangFuse" button (footer → plain Close).
  Keep "Prompt (read-only)" prose, Allowed Tools, Skills, Matching Rules.
- `app.js` `switchEngine('prompts')` wiring unchanged; it calls `fetchWorkers()` instead of
  `fetchPrompts()`.
- **Left untouched:** `checkLangfuseHealth` (top-bar health dot) and the per-task trace viewer
  (`handle_task_traces`). The now-unused **backend** `handle_langfuse_prompts` /
  `handle_langfuse_trace_stats` endpoints are left in place (dead-but-harmless, minimal/reversible
  diff) rather than removed.
- **Tab label:** keep id `engine-prompts` and label "Workers & prompts" (worker prompt bodies are
  still shown, so it stays accurate; avoids churn).

### Section 3 — Fix worker skill names (nested → flat)

Rewrite `skills:` in `scripts/workers/researcher.md`, `scheduler.md`, `product-analyst.md` to the
verified flat folder names (1:1 mapping, already validated). `eval-analyst` / `ticket-creator` already
flat; the four no-skills workers untouched. This makes the pack join trustworthy and repairs the
`build_skills_catalog_filtered` scoping no-op.

### Section 4 — Testing & verification

**Python tests** (extend the suite):
- `/api/workers` returns `tier` / `model` / `packs` per worker.
- `model` tracks posture (low/balanced/high) through `resolve_model` (assert the matrix shift for a
  known worker).
- Pack join is correct for a known worker (e.g. `product-analyst` → includes `pm`) and `[]` for a
  no-skills worker; degrades to `[]` when `packs.yaml` is absent.
- **Lock the fix:** every worker's `skills:` resolves to a real on-disk flat skill folder (guards
  regressions of the nested→flat rename).

**Standing gates:** `python3 -m pytest` (209 → grows) stays green; `python3 scripts/card_schema.py`
stays green (no card-schema changes).

**On-screen on `:8743`** (Chrome.app headless; restart the dev server after backend changes —
`/api/*` loads at process start): the tab renders worker cards **with LangFuse not running**; tier
badges + resolved model show on cards; the modal shows pack chips and no LangFuse button; changing
model posture in the Profile room reflects in each worker's resolved model. The prod board on `:8742`
is never touched.

## Out of scope (unchanged deferrals)

- The factory (`meta-create-*` skills) — Phase 9 / build-sequence step 8.
- Editing worker `.md` from the UI (factory / by-hand only).
- Removing the dead `handle_langfuse_prompts` / `handle_langfuse_trace_stats` endpoints.
- The `task-extract-meetings.sh:87` stale skill path (separate concern).
- Phase-4–7 carryovers: dispatch-behavior enforcement of ladder tiers; task→transcript join;
  `description_patterns` ignored by the regex matcher; `ladder.json` single-writer concurrency;
  `receipt_summary` backend emission; scoping the accept commit to the patch's files; unvalidated
  per-task `model:` override; `profile.js` rendering the resolved model string (tier badge only).

## Verification posture

Subagent-driven-development: a fresh implementer per task, two-stage review (spec-compliance, then
code-quality) per the superpowers workflow. No JS test harness by design — front-end verified
on-screen via Chrome.app headless against `:8743`. `python3 -m pytest` and
`python3 scripts/card_schema.py` stay green throughout.
