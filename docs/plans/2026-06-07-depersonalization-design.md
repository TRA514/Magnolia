# Magnolia — Engine De-personalization (Vantaca-team-agnostic + per-person) (Design)

**Date:** 2026-06-07
**Status:** Design approved (brainstorm complete) — ready for implementation plan
**Builds on:** Phases 1–8 merged to `main` (latest merge `73b428b`).
**Master design:** `2026-06-05-pm-os-portability-design.md` §1 ("no 'Jay', no 'Vantaca' anywhere in
engine/" — *refined below*), §10 (de-personalization cleanup). This phase finishes the prompt + skill
layer that §1/§10 called for but that was only half-executed (the profile/voice/judge plumbing landed;
the worker prompts + skills/commands were never scrubbed).
**Independent of:** Phase 9 (the factory). Done now, before/parallel to the factory, because the
factory clones exemplar workers/skills — clean exemplars first so generated artifacts don't inherit the
debt.

---

## Why this exists (the finding)

A sweep of the engine (`scripts/workers/`, `.claude/skills/`, `.claude/commands/`, some `scripts/*.py`,
excluding `datasets/` and `docs/plans/`) found ~21 files carrying `Jay` / `jay-voice` / per-team Jira
literals. This is **real engine debt, not demo data** — the dispatcher reads these worker `.md` prompt
bodies live.

**Highest-severity (a live functional break, not cosmetic):** `scripts/workers/message-writer.md` —
the worker whose job is drafting in the operator's voice — reads `datasets/reference/jay-voice.md`,
which **does not exist**. So it ignores the real voice files and falls back to ~18 hardcoded "Jay"
mentions in its own prompt. `scripts/langfuse_setup.py` registers `judge-voice-jay` from the same dead
path. The new voice architecture (`profile/voice/{teams,email}.md` + `profile_lib.voice_text()` +
`judge.py` + `meta-onboard` writing them) already exists — the workers just never migrated.

## Scope decision (refined with the operator)

**Magnolia is for teammates AT Vantaca.** Therefore **Vantaca references STAY** — `Vantaca`,
`VantacaDatabricks`, Gong/Zendesk/Azure-DevOps are shared infrastructure. We generalize only two axes:

- **Per-person** → operator identity + voice come from `profile/`.
- **Per-team-within-Vantaca** → things that vary by team (Jira board/project/assignee, the Home AI DLC
  product area) become `profile/integrations.yaml`-driven, while the **shared structure** (Vantaca Jira
  issue types — Features/Units/Bugs/Regression Defects — and their required fields, the workflow) stays
  baked into the prompts.

This *shrinks* scope vs a full "remove Vantaca" scrub. Notably `researcher.md` and `product-analyst.md`
carry only Vantaca refs (the `VantacaDatabricks` tool + descriptions) → **no change needed**.

## How the prompts consume profile values: instruct-to-read-profile

Worker prompt bodies and skills are dispatched/read as text, not Python. Rather than add dispatch-time
template-var substitution (which would only cover workers and grows the dispatch var registry), the
prompts/skills are rewritten to **instruct the agent to read from `profile/` at runtime** — agents
already read `CLAUDE.md`, the task, and transcripts, so reading a small YAML/markdown file is reliable
and on-architecture. Pattern:

> "Read the operator's voice from `profile/voice/teams.md` and `profile/voice/email.md`."
> "Read the team's Jira target from `profile/integrations.yaml` → `project_management.jira`
> (`project_key`, `board_id`, `default_assignee`, `component_id`, `product_area`). If a field is unset,
> draft without it and flag it for the operator."

Graceful degradation is expressed in prose. No `task_dispatch.py` substitution changes.

## Batching: one phase, two risk-ordered PRs

### PR1 — Functional layer (workers + onboarding + LangFuse voice)

1. **Voice break — `scripts/workers/message-writer.md`:** replace `datasets/reference/jay-voice.md`
   refs + all "Jay" identity/voice mentions with: read the operator's voice from `profile/voice/*`,
   sound like *the operator*; if those are empty/absent, draft in a clean neutral professional voice and
   note it. "Jay" → "the operator" throughout (incl. the description frontmatter and the
   "Context for Jay" block → "Context for the operator").
2. **Jira per-team — `scripts/workers/ticket-creator.md`:** replace hardcoded board `1096` / project
   `VNT` / assignee UUID `712020:aeec48b7-3829-433b-9125-c8c2a4c84e6f` / "Home AI DLC" with: read
   `profile/integrations.yaml` `project_management.jira` (project_key, board_id, default_assignee,
   component_id, product_area); keep the shared Vantaca issue-type/field structure; unset field → draft
   without + flag. Keep illustrative Jira-native references generic (no real board/key literals).
3. **Identity pronouns — `_default.md`, `eval-analyst.md`, `scheduler.md`:** "Jay" → "the operator".
4. **Schema — `profile/integrations.yaml`:** add `board_id: ""` and `product_area: ""` to the `jira`
   block (the template/live file). `profile_lib.jira_config()` already returns the whole block.
5. **Onboarding — `.claude/skills/meta-onboard/SKILL.md`:** when the project-management provider is
   `jira`, collect the per-team Jira block (project_key, board_id, default_assignee, component_id,
   product_area) into `integrations.yaml`. (Today onboarding only sets the provider.)
6. **LangFuse — `scripts/langfuse_setup.py`:** the `judge-voice-jay` registration reads the dead
   jay-voice path → read `profile/voice/*` via `profile_lib.voice_text()`; rename the prompt to
   `judge-voice-operator`. Power-user path; kept but de-Jay'd.
7. **Tests (PR1):**
   - grep-guard: no `Jay` (standalone word), `jay-voice`, the assignee UUID, board `1096`, or `VNT`
     project literal in `scripts/workers/`. Allowlist: `Vantaca`/`VantacaDatabricks`/Gong/Zendesk/ADO.
   - `message-writer.md` references `profile/voice`; `ticket-creator.md` references
     `profile/integrations` jira config.
   - `profile_lib.jira_config()` surfaces `board_id` and `product_area`.
   - `langfuse_setup` voice source resolves through `profile_lib.voice_text()` (not a `datasets/` path).

### PR2 — Prose scrub (skills + commands)

Same instruct-to-read-profile treatment, prose-only, Vantaca intact. ~12 files: `workflow-jira-home`
(the heaviest — board/project → profile, keep the Vantaca issue-type structure), `jira-create.md`,
`strategy-memo.md`, `context-search`, `context-source-normalization`,
`quality-meeting-schema-validation`, `task-create`, `task-extract-from-meeting`,
`workflow-landing-page-creator`, `workflow-schedule-meeting`, `workflow-velocity-estimate`,
`context-databricks-analytics`. Each: "Jay" → "the operator"; per-team specifics → "read from profile";
leave Vantaca/Gong/Zendesk/ADO intact. Extend the grep-guard test to cover `.claude/skills/` +
`.claude/commands/`.

## Testing & verification posture

- The **grep-guard test** is the core regression lock (denylist of per-person/per-team literals;
  Vantaca allowlisted), scoped to `scripts/workers/` in PR1, extended to `.claude/skills/` +
  `.claude/commands/` in PR2.
- Accessor/schema tests for the new Jira fields.
- No UI change → no Chrome pass. `python3 -m pytest` (213 → grows) and `python3 scripts/card_schema.py`
  stay green.
- Subagent-driven-development: fresh implementer per task + two-stage review (spec, then code-quality).
  PR1 then PR2.

## Out of scope (unchanged deferrals)

- Phase 9 (the factory) — separate; this de-risks it by cleaning exemplars first.
- The card-driven per-user skill-personalization flow (the second half of the original
  skill-portability note) — that folds into the factory.
- Phase-7/8 follow-ups (unvalidated per-task model override; tier-badge CSS variants; dead LangFuse
  list endpoints; vestigial `langfuse_prompt` payload field).
- Non-Vantaca company-agnosticism (explicitly NOT a goal: Magnolia targets Vantaca teammates).
