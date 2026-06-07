# Magnolia Phase 7 — Skill Packs + Model Tiering (Design)

**Date:** 2026-06-07
**Status:** Design approved (brainstorm complete) — ready for implementation plan
**Builds on:** Phases 1–6 (PRs #5–#8 merged to `main` at `0b22b57`)
**Master design:** `2026-06-05-pm-os-portability-design.md` §7 (model cost tiering), §8 (skill
packaging), §11 step 7.
**Phase 6 context:** `2026-06-06-phase-6-integrate-frontend-design.md` — the Profile room already
ships a Skill-packs section (`POST /api/profile/packs` → `profile_lib.set_active_packs`) and a
Model-posture section (`PUT /api/profile/model-posture` → `profile_lib.set_cost_posture`).

---

## What Phase 7 is

Build-sequence step 7: "Skill packs (profile + factory) + model tiering — polish." Both surfaces
already exist in the UI and write to `profile/config.yaml`, but **nothing acts on what they write**:

- `active_skill_packs` is recorded; `PACK_CATALOG` is a hardcoded constant in `task_server.py`;
  auto-discovery still loads every skill folder regardless.
- `cost_posture` is recorded; **dispatch never passes `--model`** (confirmed — `dispatch_task`
  builds `claude <prompt> --allowedTools … --max-turns … --permission-mode bypassPermissions`, no
  model flag). No worker declares a tier, so the Model-posture section's worker list is empty.

Phase 7 makes both real. Two independent halves, shipped as **two separate PRs** off `main`:
**PR 1 — Skill packs**, then **PR 2 — Model tiering**. Neither blocks the other; each is
independently reviewable and verifiable on the dev board (`:8743`).

## Guiding decisions (from brainstorm)

1. **Packs are a manifest, catalog-gated.** A pack is a named set of skill folders defined in a
   single engine-shared `packs.yaml`. Activation gates the **Magnolia background workers + the
   Engine/Profile UI** — *not* the operator's interactive Claude Code session (native auto-discovery
   there stays normal). The reach that matters for a calm chief-of-staff is *what the autonomous
   workers reach for*; the operator driving interactively seeing all skills is harmless.
2. **The UI unit is the pack, never the individual skill.** A user toggles packs on/off (works
   as-built from Phase 6). A user never adds a skill in the UI. Authoring new skills is the factory
   (step 8, deferred) or a power user dropping a folder. **Kept minimal: no skill list rendered in
   the UI** — pack cards stay `id/label/description`.
3. **No new wiring subsystem.** The contract for adding a skill is tiny and mostly automatic:
   folder + `SKILL.md` → auto-discovered; optionally list the folder under a pack in `packs.yaml`;
   optionally name it in a worker's `skills:`. A skill in no pack defaults to always-available
   (drop-a-folder still "just works"). Documented as a commented header in `packs.yaml` + a note in
   `.claude/CLAUDE.md` — not a registry.
4. **Model tiering uses a shift model.** Each worker declares a `tier:` (light/standard/deep). The
   persona's `cost_posture` (low/balanced/high) shifts the whole fleet ±1 step, clamped at the ends.
   `balanced` = use the declared tier as-is. A per-task override pins one task to a specific model.
5. **Dispatch enforces the model**, it is not advice — `dispatch_task` appends `--model <resolved>`.

---

## PR 1 — Skill packs (manifest, catalog-gated)

### New file: `.claude/packs.yaml`

Engine-shared, git-tracked. (The *which packs are active* choice stays per-person in
`profile/config.yaml` `active_skill_packs`.) Co-located with the `.claude/skills/` folders it maps.
Maps each pack id → `{label, description, skills: [folder names]}`. Taxonomy is the existing five
ids the Phase 6 UI already references: `core` (always-on), `pm`, `exec`, `eng`, `recruiting`.

A commented header documents the "how to add a skill to a pack" contract (the three-line surface
from decision 3).

```yaml
# packs.yaml — skill pack definitions (engine-shared).
# A "pack" is a named set of skill folders under .claude/skills/.
# To add a skill to a pack: drop the folder in .claude/skills/ (auto-discovered),
#   then add its folder name to a pack's `skills:` list below.
# A skill listed in NO pack stays always-available (gating never hides it).
# WHICH packs are active is per-person, in profile/config.yaml active_skill_packs.
core:
  label: "Core"
  description: "Baseline PM-OS skills: tasks, search, meeting synthesis, onboarding, doctor."
  skills: [task-create, task-query, task-update, context-search, ...]
pm:
  label: "Product Management"
  description: "PRDs, roadmaps, strategy, metrics, and prioritization."
  skills: [workflow-prd-creation, workflow-product-planning, ...]
# exec / eng / recruiting …
```

> **Implementation review checkpoint:** the exact skill→pack assignment for all ~60 folders is
> reviewed with the operator the same way the worker-tier map was reviewed in this brainstorm,
> before the assignment is finalized.

### New module: `scripts/packs_lib.py`

- `load_packs(root=None)` → parse `.claude/packs.yaml` into `{id: {label, description, skills}}`.
- `pack_catalog()` → `[{id, label, description}]` — replaces the hardcoded `PACK_CATALOG`.
- `active_skill_folders(active_packs)` → set of folder names visible to gating: **union of `core`
  + each active pack's `skills`**, plus the **always-available** set (any skill folder present on
  disk but listed in no pack). Core is always included even if absent from `active_packs`.

### Gating point: `task_dispatch.build_skills_catalog()`

Becomes pack-aware. Reads `active_skill_packs` via `profile_lib.config()`, resolves
`active_skill_folders(...)`, and lists only those skills in the headless worker prompt catalog.
`build_skills_catalog_filtered(worker.skills)` (explicit per-worker scoping) is unchanged in this
PR. Interactive Claude Code is untouched.

### `build_profile()` (task_server.py)

`PACK_CATALOG` constant is replaced by `packs_lib.pack_catalog()`. The packs payload shape
(`{active, available}`) is unchanged, so the Phase 6 frontend keeps working with no JS changes.

### Graceful degradation

Missing or malformed `packs.yaml` → no gating (all on-disk skills available) and `pack_catalog()`
returns an empty/minimal list. Consistent with the system's degrade-don't-crash ethos.

### Tests (PR 1)

- `packs_lib`: load; `pack_catalog()` derivation; `active_skill_folders()` — core-always-on,
  union of active packs, unlisted-skill-defaults-on, missing-file degradation.
- `build_skills_catalog()` gates to active folders; full catalog when packs absent/malformed.
- `build_profile()` packs section derives from `packs_lib` (no hardcoded constant).

### Verify on :8743

Profile room Skill-packs section renders the derived catalog; toggling a pack persists to
`config.yaml`; a deactivated pack's skills drop out of the dispatch catalog (assert via the prompt
text / a dispatch dry-run). Restart the dev server after backend changes.

---

## PR 2 — Model tiering (shift model)

### Worker frontmatter: declare `tier:`

OOTB tier map (agreed in brainstorm — the `balanced` baseline):

| Worker | Tier | Rationale |
|---|---|---|
| grad-assessor | `light` | Runs a deterministic Python assessor + reports; "no analysis"; max_turns 6. |
| scheduler | `light` | Query M365 availability, format slot options. Mechanical. |
| _default | `standard` | Catch-all, unknown work — safe middle. |
| message-writer | `standard` | Drafts Teams/email in operator voice; tone nuance. |
| ticket-creator | `standard` | Structured Jira ticket drafting to a board convention. |
| eval-analyst | `deep` | Weekly self-improvement: clusters failures, proposes fixes at altitude. |
| researcher | `deep` | Multi-source synthesis with citations. |
| product-analyst | `deep` | PRDs, strategy, business cases, red-team — flagship strategic worker. |

### Resolution: `profile_lib.resolve_model(worker_tier, posture=None, task_override=None, root=None)`

```
TIER_ORDER  = [light, standard, deep]
TIER_MODELS = {light: claude-haiku-4-5, standard: claude-sonnet-4-6, deep: claude-opus-4-8}
POSTURE_SHIFT = {low: -1, balanced: 0, high: +1}
```

- If `task_override` present (a model id, or a tier name) → it wins; return that model.
- `posture = posture or config.cost_posture or "balanced"`.
- Shift the worker's tier index by `POSTURE_SHIFT[posture]`, clamp to `[0, len-1]`.
- Return `TIER_MODELS[shifted]`.
- Unknown/missing worker tier → `standard`; unknown posture → `balanced`.

Resolved matrix (worker declared tier × posture):

| declared | low | balanced | high |
|---|---|---|---|
| light | Haiku | Haiku | Sonnet |
| standard | Haiku | Sonnet | Opus |
| deep | Sonnet | Opus | Opus |

### `task_dispatch.dispatch_task`: enforce `--model`

- Read the matched worker's `tier` (frontmatter passes through `_parse_worker_frontmatter`; read
  `fm.get("tier")`).
- Read a per-task override from the task frontmatter (`model:` or `tier:`).
- `model = profile_lib.resolve_model(worker_tier, task_override=override)`.
- Append `--model <model>` to `claude_cmd`. (Works for the interactive `claude` invocation the
  dispatcher uses for cloud-MCP access.)

### `build_profile()` model_posture

`_profile_workers()` already surfaces each worker's `name` + `tier`. Additively include the
**resolved model at the current posture** per worker, so the UI can show the live mapping. Purely
additive to the payload — no frontend change required.

### Tests (PR 2)

- `resolve_model`: every tier × every posture (the matrix above); end clamping; override
  precedence (model id and tier-name forms); default-tier and default-posture fallbacks.
- `dispatch_task` appends `--model <resolved>` (assert via the constructed command / dry-run).
- `_profile_workers` / `build_profile` surfaces the tiers + resolved models.

### Verify on :8743

Model-posture section now lists the eight workers with their tiers; changing posture
low/balanced/high reflects the resolved model per worker. Restart the dev server after backend
changes.

---

## Out of scope (unchanged deferrals)

- **The factory** (`meta-create-*` skills) — build-sequence step 8.
- Adding/authoring skills via the UI (factory territory).
- Pack-contents / skill-list rendering in the UI (kept minimal by decision).
- Judge-driven model-downshift suggestions (master design §7, explicitly not-v1).
- Dispatch-behavior enforcement of ladder tiers; task→transcript join; `description_patterns`
  ignored by the regex matcher; `ladder.json` single-writer concurrency; `receipt_summary` backend
  emission; scoping the accept commit to the patch's files. (Carried from Phase 4–6.)

## Verification posture

`python3 -m pytest` (169 passing at Phase 6 close) stays green and grows with the new tests.
`python3 scripts/card_schema.py` stays green (no card-schema changes, but it's the standing gate).
On-screen checks via Chrome.app headless against the dev board on `:8743` (the prod board on `:8742`
is never touched). Subagent-driven-development: a fresh implementer per task, two-stage review
(spec-compliance, then code-quality) per the superpowers workflow.
