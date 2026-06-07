# Knowledge-Architecture Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an agent-first reference layer (`docs/reference/`) that is a thin map+invariants pointing at executable truth, and slim the CLAUDE.md hierarchy into a router that links to it.

**Architecture:** Four reference docs cut by agent-moment — `invariants.md` (laws + enforcing commands, loaded first), `architecture.md` (engine map → subsystems → seams, each ending "canonical source: X"), `conventions.md` (the working rhythm), `design-system.md` (UI-surface rules). The reference docs never duplicate skills/code — they link to them. The three repo CLAUDE.md files (root, `.claude/`, `ui/task-board/`) become routers that point into the reference layer. Two existing READMEs (`profile/README.md`, `themes/README.md`) stay canonical and are linked, not copied. `docs/plans/**` is the untouched archive.

**Tech Stack:** Markdown only. Verification via existing gates: `python3 -m pytest`, `python3 scripts/card_schema.py`, `python3 -m pytest tests/test_engine_no_jay.py`. Plus an accuracy gate: every cited path/flag/line is confirmed against the real tree before it's written.

**Design doc:** `docs/plans/2026-06-07-docs-consolidation-design.md`

**Branch:** `docs/knowledge-architecture-consolidation` (already created; design doc already committed at `2f73360`).

---

## How "TDD" maps to doc work

There is no failing unit test for prose. The discipline analog, applied to every task:

1. **RED (verify the source):** before writing a claim, run the grep/read that confirms the file, line, flag, or command actually exists as stated. If code and a draft disagree, **the code wins** and the discrepancy is surfaced.
2. **GREEN (write):** write the doc section from verified facts only.
3. **REFACTOR (link, don't copy):** replace any paragraph that restates a skill/code with a one-line pointer + `canonical source:` link.
4. **Gate:** if the task touched any `scripts/workers/*.md`, `.claude/skills/**/*.md`, `.claude/commands/*.md`, or `scripts/adapters/**/*.py`, run `python3 -m pytest tests/test_engine_no_jay.py -q` and confirm green before commit. (Reference docs under `docs/` are NOT scanned, so doc-only tasks skip this — but the router-trim tasks must run it if they touch a scanned file. None are expected to.)

**Verified facts available to the executor** (confirmed against the tree at plan time — re-verify if the tree has moved):
- Green gates: `python3 -m pytest` (264 passing) · `python3 scripts/card_schema.py` → prints `registry.json OK` · `python3 -m pytest tests/test_engine_no_jay.py`.
- `scripts/card_schema.py:3` — "card definitions reference theme tokens ONLY (no hardcoded colors)". `:17` `SLOT_ORDER = ["head", "title", "context", "signals", "body", "actions"]`. `:16` `BODY_RENDERERS = {"diff", "preview", "agreement"}`. `:43-44` slotOrder must equal SLOT_ORDER. `:50-57` token-existence + hardcoded-color/size rejection.
- `scripts/adapters/__init__.py:28` `class NeedsConfirmation(RuntimeError)`. `:40-51` `_is_confirmed` grandfather-by-config. `:54-62` `publish()` raises `NeedsConfirmation` when configured-but-unconfirmed; returns `None` when no provider.
- Adapter contracts: `scripts/adapters/project_management/_contract.py`, `scripts/adapters/transcript/_contract.py` (Protocols). Loader: `scripts/adapters/__init__.py` `get(family, root)` dynamic-imports `adapters.<family>.<provider>` from `profile_lib.provider(family)`.
- De-personalization spec: `tests/test_engine_no_jay.py` — DENY list (`\bjay\b`, `jay-voice`, the assignee UUID, `board 1096`, `~/pm-os`, `/Users/`); TARGETS = workers `*.md` + skills `**/*.md` + commands `*.md` + adapters `**/*.py`.
- Profile API: `scripts/profile_lib.py` — getters (`display_name`, `email`, `company`, `persona`, `provider`, `jira_config`, `transcript_config`, `pendo_config`, `databricks_config`, `cost_posture`, `resolve_model`), writers (`write_identity`, `set_integration_provider`, `set_integration_conventions`, `set_integration_confirmed`, `set_active_packs`, `set_cost_posture`), CLI flags `--display-name`, `--pendo-subid`, `--databricks-catalog`. Profile schema/API doc: `profile/README.md` (canonical).
- Factory: spine `meta-factory-core`, siblings `meta-create-worker` / `meta-create-card-type` / `meta-create-adapter` (each "Read meta-factory-core first"). `scripts/factory_lib.py` subcommands: `commit-and-receipt`, `validate-worker`, `validate-card-type`, `validate-adapter`.
- Packs: `.claude/packs.yaml` — `core` (always active) + `pm`, `exec`, and placeholders `eng`/`recruiting`/`ops`. Active list in `profile/config.yaml` `active_skill_packs`. Gates background-worker dispatch + Profile UI; NOT the interactive session.
- Dispatch: `scripts/task_dispatch.py` (`load_workers()`, worker-match + worker-execution), workers in `scripts/workers/*.md` (`_default`, `researcher`, `product-analyst`, `scheduler`, `ticket-creator`).
- Task CLI: `scripts/task.sh` (add/list/show/update/done/inbox; agent: `agent:start`, `agent:complete --output`, `agent:fail --error`, `agent:ask`). Web UI: `scripts/task_server.py`.
- **Accuracy fix #1:** `ui/task-board/CLAUDE.md:6` says dev URL `:8742`; correct split is **prod=:8742, dev=:8743**.
- **Accuracy fix #2:** root `CLAUDE.md:121-144` documents LangFuse as system-of-record; per master-design §5 it's now a power-user opt-in (native files+git+board is the default substrate). Eval substrate canonical source: `docs/plans/2026-06-06-phase-4-eval-substrate-design.md` + the phase-4 impl doc.

---

## Task 1: Scaffold reference dir + write `invariants.md` (the keystone)

**Files:**
- Create: `docs/reference/invariants.md`

**Step 1 — RED (verify):** Confirm the enforcing commands exist and the laws are real.
```bash
cd /Users/jayjenkins/dev/pm-os-team
python3 -m pytest tests/test_engine_no_jay.py -q        # de-personalization gate
python3 scripts/card_schema.py                          # → registry.json OK
grep -n "SLOT_ORDER\|BODY_RENDERERS\|token" scripts/card_schema.py | head
grep -n "NeedsConfirmation\|grandfather" scripts/adapters/__init__.py
sed -n '1,20p' tests/test_engine_no_jay.py              # DENY + TARGETS
```
Expected: pytest passes, card_schema prints `registry.json OK`, greps confirm the cited symbols.

**Step 2 — GREEN (write):** Create `docs/reference/invariants.md`. One screen. Each invariant is exactly: **rule → why (one clause) → executable check / enforcing file**. Pure law, no process narrative. Cover these seven:

```markdown
# Invariants — the laws that must never break

> Load this first, before acting on the engine. Every other doc links here for the laws.

| # | Law | Why | Enforced by |
|---|-----|-----|-------------|
| 1 | The engine never hardcodes person/team identity — it reads from `profile/` via `scripts/profile_lib.py`. | The engine is shared and team-portable; identity lives only in the per-person profile. | `python3 -m pytest tests/test_engine_no_jay.py` (scans workers/skills/commands/adapters against a denylist) |
| 2 | Gates stay green before any commit. | A red gate means the engine is broken for everyone who pulls. | `python3 -m pytest` · `python3 scripts/card_schema.py` (→ `registry.json OK`) · `python3 -m pytest tests/test_engine_no_jay.py` |
| 3 | Card definitions reference theme tokens ONLY — never a hardcoded color/radius/transition. | Guarantees every card is 100% theme-aware across all Moods. | `python3 scripts/card_schema.py` (`scripts/card_schema.py:50-57`) |
| 4 | Capture team/person nuance to the PROFILE, never into a generated artifact. | Keeps artifacts denylist-clean and the nuance editable. | `profile_lib.set_integration_conventions(...)`; law #1's test |
| 5 | Anything that writes to the outside world is Tier-2: exactly one plain-language confirm before its first external action. | Blast-radius is consented in plain words; no silent external writes. | `scripts/adapters/__init__.py:54-62` (`publish()` raises `NeedsConfirmation`); arm with `profile_lib.set_integration_confirmed(family, False, provider=...)` |
| 6 | Never delete generated artifacts — append a version suffix (`v1`, `v2`). | History is the audit trail; nothing is silently lost. | Convention; reviewed in `conventions.md` |
| 7 | Dev board is `localhost:8743`; production board is `localhost:8742`. Never operate the prod board or `~/pm-os` from engine work. | Two systems; crossing them risks the live production install. | Convention; stated in root `CLAUDE.md` + `ui/task-board/CLAUDE.md` |

_Git is never a user-facing concept: generated changes are presented as **Keep / Undo** (see `meta-factory-core`)._
```

**Step 3 — REFACTOR:** Ensure no row explains *how* a subsystem works (that's architecture) or *when* in the workflow to run a check (that's conventions). Rows are laws only.

**Step 4 — Gate:** doc-only, not scanned. No gate needed. (Sanity: `ls docs/reference/invariants.md`.)

**Step 5 — Commit:**
```bash
git add docs/reference/invariants.md
git commit -m "docs(ref): invariants.md — the laws + their enforcing commands

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Write `architecture.md` (the engine map)

**Files:**
- Create: `docs/reference/architecture.md`

**Step 1 — RED (verify each subsystem's canonical source before describing it):**
```bash
cd /Users/jayjenkins/dev/pm-os-team
grep -n "^##" .claude/CLAUDE.md                              # skill/pack/auto-discovery facts
sed -n '1,30p' scripts/adapters/__init__.py                 # adapter loader + Tier-2
cat .claude/packs.yaml | head -40                            # pack names
ls scripts/workers/                                          # dispatch workers
grep -n "def load_workers\|worker-match\|worker-execution" scripts/task_dispatch.py | head
ls .claude/skills/ | grep '^meta-'                           # factory skills
sed -n '347,355p' scripts/profile_lib.py                     # CLI flags
sed -n '86,104p' CLAUDE.md                                   # task agent-queue facts (to relocate)
```
Expected: each fact confirmed. Any mismatch → fix the draft to match code.

**Step 2 — GREEN (write):** Create `docs/reference/architecture.md`. Open with the spine, then one section per subsystem. **Every subsystem section ends with a `**Canonical source:**` line** linking the skill/file that authoritatively owns it. Keep each section tight — model + seam, not a re-spec.

Required sections (in this order):
1. **The spine — engine / profile / content.** Engine is shared+de-personalized; `profile/` is the only place identity lives; `datasets/` is per-person content. _Canonical source: `profile/README.md`, `docs/plans/2026-06-05-pm-os-portability-design.md` §1._
2. **Skills + packs + auto-discovery.** Skills auto-discover from `.claude/skills/<name>/SKILL.md`; packs (`.claude/packs.yaml`) gate the background-worker catalog + Profile UI, NOT the interactive session; active list in `profile/config.yaml`. _Canonical source: `.claude/CLAUDE.md`, `.claude/packs.yaml`._
3. **Worker dispatch — workers scope, skills instruct.** `scripts/task_dispatch.py` matches a task to a `scripts/workers/*.md` worker (`_default`, `researcher`, `product-analyst`, `scheduler`, `ticket-creator`); the worker defines tools/skills/tier; skills supply the how. Model resolved by `profile_lib.resolve_model(tier, posture, override)`. _Canonical source: `scripts/workers/_default.md`, `scripts/task_dispatch.py`._
4. **The adapter seam + Tier-2 gate.** Families (`project_management`, `transcript`, `calendar`) behind Protocols in `_contract.py`; loader dynamic-imports `adapters.<family>.<provider>` from the profile's provider choice; returns `None` when unconfigured (graceful degrade); `publish()` raises `NeedsConfirmation` until confirmed. _Canonical source: `scripts/adapters/__init__.py`, `scripts/adapters/*/_contract.py`._
5. **Profile + instruct-to-read-profile de-personalization.** All identity/integration values flow through `profile_lib.py`; skills/workers/adapters reference the profile (CLI flags like `--pendo-subid`), never literals; enforced by the denylist test. _Canonical source: `profile/README.md`, `scripts/profile_lib.py`, `tests/test_engine_no_jay.py`._
6. **The factory (self-extension).** Shared lifecycle in `meta-factory-core` (scaffold → capture-to-profile → gate-green → commit → Keep/Undo receipt); three siblings `meta-create-worker` / `meta-create-card-type` / `meta-create-adapter`; `scripts/factory_lib.py` does commit-and-receipt + per-kind validate. Adapters are Tier-2; workers/card-types Tier-1. _Canonical source: `.claude/skills/meta-factory-core/SKILL.md` + the three `meta-create-*` skills._
7. **Eval substrate.** Default is native files+git+board (prompts in files, traces in Claude Code session JSONL, scores in task frontmatter, UI = board Quality tab); LangFuse is a **silent power-user opt-in** (`LANGFUSE_SECRET_KEY`), not the system of record. _Canonical source: `docs/plans/2026-06-06-phase-4-eval-substrate-design.md`._
8. **Cron.** Recurring jobs in `datasets/cron/jobs.json`, scheduler thread in `task_server.py`, template vars resolved at execution. _Canonical source: `scripts/cron_lib.py`, `scripts/cron_scheduler.py`._
9. **Task system (quick reference).** The CLI surface relocated out of root CLAUDE.md: `scripts/task.sh add|list|show|update|done|inbox`; agent queue `agent:start|complete|fail|ask`; four queues (human/agent/collab/waiting); web UI `scripts/task_server.py`. _Canonical source: `scripts/task.sh` (`--help`)._

**Step 3 — REFACTOR:** Delete any sentence that re-explains a skill's internal steps or a function's body — replace with the `Canonical source:` link. The doc should be skimmable in one pass.

**Step 4 — Gate:** doc-only, not scanned. None.

**Step 5 — Commit:**
```bash
git add docs/reference/architecture.md
git commit -m "docs(ref): architecture.md — engine map, subsystems, seams

Each section links its canonical executable source. Relocates the task/cron/
eval prose out of root CLAUDE.md; reframes LangFuse as power-user opt-in.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Write `design-system.md` (UI-surface rules)

**Files:**
- Create: `docs/reference/design-system.md`

**Step 1 — RED (verify):**
```bash
cd /Users/jayjenkins/dev/pm-os-team
sed -n '1,20p' scripts/card_schema.py                       # token rule, SLOT_ORDER, BODY_RENDERERS
python3 -c "import json;r=json.load(open('ui/task-board/cardtypes/registry.json'));print(r['slotOrder']);print(list(r['cardTypes']))"
sed -n '1,30p' ui/task-board/themes/README.md               # add-a-mood steps (canonical)
ls ui/task-board/themes/                                    # mood files
```
Expected: SLOT_ORDER and cardTypes match what you'll document; themes/README has the 3-step add-a-mood flow.

**Step 2 — GREEN (write):** Create `docs/reference/design-system.md`. Sections:
1. **The token-only HARD RULE.** A card definition references theme tokens only — never a hardcoded color/radius/transition. _Enforced: `scripts/card_schema.py:50-57`. Link invariant #3._
2. **The card schema.** Slot order is fixed: `head → title → context → signals → body → actions` (`SLOT_ORDER`, `card_schema.py:17`). A card type = `{ signals, actions, body }` in `ui/task-board/cardtypes/registry.json`. Signals = predicate-driven chips; actions = buttons mapped to handlers; body = one of `diff` / `preview` / `agreement` / `null` (`BODY_RENDERERS`, `card_schema.py:16`).
3. **The composition-only boundary.** A new card type that composes *existing* signals/actions/body renderers is registry-only (no JS) — use `meta-create-card-type`. A new signal predicate, action handler, or body renderer is JavaScript work in `ui/task-board/js/` and out of the composition path. State this boundary explicitly.
4. **Moods / theme tokens.** Themes are token-only stylesheets under `ui/task-board/themes/<id>.css` scoped to `[data-theme="<id>"]`; derived tokens computed once in `index.html` `:root`; switching only swaps tokens, never interactions. To add a mood, follow the 3 steps in `themes/README.md` (copy `_TEMPLATE.css` → link in `index.html` → register in `js/themes.js`). _Canonical source: `ui/task-board/themes/README.md`, `scripts/card_schema.py`, `ui/task-board/cardtypes/registry.json`._

**Step 3 — REFACTOR:** The add-a-mood steps live in `themes/README.md` — summarize in 2 lines and link, don't re-list verbatim.

**Step 4 — Gate:** doc-only. None. (Sanity re-run `python3 scripts/card_schema.py` to be sure nothing was disturbed → `registry.json OK`.)

**Step 5 — Commit:**
```bash
git add docs/reference/design-system.md
git commit -m "docs(ref): design-system.md — token-only rule, card schema, composition boundary, Moods

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Write `conventions.md` (the working rhythm)

**Files:**
- Create: `docs/reference/conventions.md`

**Step 1 — RED (verify):** Confirm the superpowers skills referenced exist and the gate commands are current.
```bash
cd /Users/jayjenkins/dev/pm-os-team
ls ~/.claude/plugins/cache/superpowers-marketplace/superpowers/*/skills/ | grep -E "brainstorming|writing-plans|subagent-driven|finishing-a-development|requesting-code-review"
python3 -m pytest -q 2>&1 | tail -2                          # confirm suite still green baseline
```
Expected: the skills exist; suite green.

**Step 2 — GREEN (write):** Create `docs/reference/conventions.md`. Sections:
1. **The development loop.** superpowers: brainstorming → writing-plans → subagent-driven-development with **two-stage review (spec, then code-quality)** → live e2e verification → finishing-a-development-branch. One paragraph + links to the skills (canonical). Branch off `main`; never commit to `main`; set git author locally (`11728296+jayhjenkins@users.noreply.github.com`); end commits with the Co-Authored-By line; PR via `gh pr create --base main`.
2. **The green gates — when to run them.** Before every commit that touches code: the three gates from invariant #2. Point to `invariants.md` for the laws; this section is *when*, not *what*.
3. **Capture-to-profile, not the artifact.** Team/person nuance → `profile/` via `profile_lib.set_integration_conventions(...)`; artifacts stay denylist-clean. Link invariant #4 + `meta-factory-core`.
4. **Capability tiers.** Tier-1 (workers, card-types) vs Tier-2 (adapters / anything writing externally → one plain-language confirm). Link invariant #5.
5. **The factory spine.** When extending the system (new worker/card-type/adapter), use the `meta-create-*` skill — it enforces scaffold → capture → gate → commit → Keep/Undo. Git stays invisible (Keep/Undo). Link `meta-factory-core`.
6. **Output conventions.** Never delete generated artifacts — append `v1`/`v2` (invariant #6). Markdown with clear headings; `*-draft.md` if unsure; `status.json`/`progress.md` for state.
7. **Dev vs prod safety.** Dev board `:8743`, prod `:8742`; never touch `~/pm-os` (the production install) from engine work. Link invariant #7.

**Step 3 — REFACTOR:** Any law restated here → replace with a link to its `invariants.md` row. Conventions describes rhythm and timing only.

**Step 4 — Gate:** doc-only. None.

**Step 5 — Commit:**
```bash
git add docs/reference/conventions.md
git commit -m "docs(ref): conventions.md — the working rhythm; references invariants for the laws

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Rewrite root `CLAUDE.md` as a router

**Files:**
- Modify: `CLAUDE.md` (currently 174 lines, sections at `:7-174`)

**Step 1 — RED (verify what's safe to relocate):** Confirm the task/cron/LangFuse content now lives in `architecture.md` (Task 2 §7-9) so removing it from root loses nothing.
```bash
grep -n "Task system\|LangFuse\|Cron\|task.sh" docs/reference/architecture.md
```
Expected: those facts are present in architecture.md.

**Step 2 — GREEN (write):** Replace the body of root `CLAUDE.md` with a router. Structure:
- **Header:** one line on what the repo is (the team-portable PM-OS engine).
- **⚠️ Invariants block:** the 7 one-liners (or a tight summary) + "Full laws & enforcing commands: `docs/reference/invariants.md` — read first."
- **Where to look (question → source table):**

  | If you need to… | Read |
  |---|---|
  | Know the rules that must never break | `docs/reference/invariants.md` |
  | Understand how the system fits together | `docs/reference/architecture.md` |
  | Work the right way (process, gates, safety) | `docs/reference/conventions.md` |
  | Touch the board / cards / themes | `docs/reference/design-system.md` |
  | `.claude/` config (skills, packs, commands, hooks) | `.claude/CLAUDE.md` |
  | The board UI internals | `ui/task-board/CLAUDE.md` |
  | Profile schema & API | `profile/README.md` |
  | Project history / past design decisions | `docs/plans/` (archive) |

- **Keep** the workspace-layout, search-tool-selection, MCP-data-sources, and meeting-file-schema sections that are genuinely root-level orientation (they are concise and not duplicated elsewhere). **Remove** the long Task Management / LangFuse / Cron prose now in `architecture.md`, leaving a one-line pointer each.
- Keep the dev/prod port note explicit in the invariants block.

**Step 3 — REFACTOR:** Confirm nothing actionable was deleted without a pointer. Diff-review: every removed section has a corresponding `architecture.md` home.

**Step 4 — Gate:** root `CLAUDE.md` is not in `test_engine_no_jay.py` TARGETS (it scans workers/skills/commands/adapters), so the gate is not strictly required — but run the full denylist guard anyway to be safe, and confirm green:
```bash
python3 -m pytest tests/test_engine_no_jay.py -q
```
Expected: PASS.

**Step 5 — Commit:**
```bash
git add CLAUDE.md
git commit -m "docs(router): slim root CLAUDE.md into a question->source router

Leads with invariants + link; relocates task/cron/LangFuse prose to
architecture.md; keeps concise root-level orientation only.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Trim `.claude/CLAUDE.md` + point at reference layer

**Files:**
- Modify: `.claude/CLAUDE.md` (sections at `:5-71`)

**Step 1 — RED (verify overlap):** Identify what `.claude/CLAUDE.md` says that now lives in `architecture.md`/`design-system.md` (e.g. skill/pack mechanics overlap with architecture §2). Keep `.claude/`-specific config truth (SKILL.md format, command wrappers, hooks, settings) here — that's its canonical home.
```bash
grep -n "^##\|^###" .claude/CLAUDE.md
```

**Step 2 — GREEN (write):** Add a top pointer: "System architecture: `docs/reference/architecture.md`. Laws: `docs/reference/invariants.md`." Trim the skill-pack *conceptual* explanation down to the `.claude/`-mechanical facts (where files live, the format) and link architecture §2 for the role packs play. Leave Modes / SKILL.md format / Slash Commands / Hooks / Settings intact — they're `.claude/`-canonical.

**Step 3 — REFACTOR:** No concept explained in two places — `.claude/CLAUDE.md` keeps mechanics, architecture keeps role.

**Step 4 — Gate:**
```bash
python3 -m pytest tests/test_engine_no_jay.py -q
```
Expected: PASS.

**Step 5 — Commit:**
```bash
git add .claude/CLAUDE.md
git commit -m "docs(router): point .claude/CLAUDE.md at the reference layer; trim conceptual overlap

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Fix `ui/task-board/CLAUDE.md` port bug + point at design-system

**Files:**
- Modify: `ui/task-board/CLAUDE.md:6` (and add a pointer line)

**Step 1 — RED (verify the bug):**
```bash
grep -n "8742\|8743\|localhost" ui/task-board/CLAUDE.md
```
Expected: line 6 shows `http://localhost:8742` as the dev URL — the bug.

**Step 2 — GREEN (fix):** Change the dev URL to `:8743` and state the split: "Dev board: `localhost:8743`. Production board (`~/pm-os`) runs on `:8742` — never operate it from engine work." Add a top pointer: "Design-system rules (token-only, card schema, Moods): `docs/reference/design-system.md`. Theme authoring: `themes/README.md`."

**Step 3 — REFACTOR:** Keep the Moods notes that are UI-specific; the design-system *rules* now live in `design-system.md` (link), the *theme authoring steps* stay in `themes/README.md` (canonical).

**Step 4 — Gate:**
```bash
python3 -m pytest tests/test_engine_no_jay.py -q
```
Expected: PASS.

**Step 5 — Commit:**
```bash
git add ui/task-board/CLAUDE.md
git commit -m "docs(fix): correct dev board port 8742->8743 in ui/task-board/CLAUDE.md; link design-system.md

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Final verification pass + PR

**Files:** none (verification only)

**Step 1 — Citation audit:** Spot-check that every `file:line` and command cited across the four reference docs resolves.
```bash
cd /Users/jayjenkins/dev/pm-os-team
grep -rno "[a-zA-Z_/.-]*\.py:[0-9]" docs/reference/ docs/plans/2026-06-07-docs-consolidation.md   # list cited py lines
# manually sed -n each cited line range to confirm it says what the doc claims
grep -rn "docs/reference/\|themes/README.md\|profile/README.md" CLAUDE.md .claude/CLAUDE.md ui/task-board/CLAUDE.md  # links present
```
Expected: cited lines match; router links present.

**Step 2 — Link integrity:** Confirm every cross-doc link target exists.
```bash
for f in invariants architecture conventions design-system; do test -f docs/reference/$f.md && echo "ok $f" || echo "MISSING $f"; done
```
Expected: four `ok`.

**Step 3 — Gates green (nothing disturbed):**
```bash
python3 -m pytest -q 2>&1 | tail -3
python3 scripts/card_schema.py
python3 -m pytest tests/test_engine_no_jay.py -q
```
Expected: 264 passing, `registry.json OK`, denylist green.

**Step 4 — Push + PR:**
```bash
git push -u origin docs/knowledge-architecture-consolidation
gh pr create --base main --title "docs: consolidated agent-first knowledge architecture" --body "$(cat <<'BODY'
## What

A living, current-state knowledge layer for the engine. Reference docs cut by
agent-moment, each pointing at the executable canonical source rather than
duplicating it.

- `docs/reference/invariants.md` — the laws + enforcing commands (loaded first)
- `docs/reference/architecture.md` — engine map, subsystems, seams
- `docs/reference/conventions.md` — the working rhythm
- `docs/reference/design-system.md` — token-only rule, card schema, Moods
- CLAUDE.md hierarchy slimmed into a question->source router

## Accuracy fixes
- `ui/task-board/CLAUDE.md` dev port 8742 -> 8743
- root CLAUDE.md: LangFuse reframed as power-user opt-in (native files+git+board is default)

## Safety
Doc-only. Gates green: full pytest (264), card_schema (registry.json OK),
test_engine_no_jay (denylist). `docs/plans/**` archive untouched.

Design: `docs/plans/2026-06-07-docs-consolidation-design.md`
BODY
)"
```

**Step 5 — Stop and confirm before merging.** Per operating rules: doc work may merge when green and structure-approved, but **confirm with the operator first**. Do not auto-merge.

---

## Task ordering rationale

Reference layer first (1→4) because the routers (5→7) link into it — building routers before their targets would create dangling links. `invariants.md` is task 1 because every other doc references it. Verification + PR last (8).
