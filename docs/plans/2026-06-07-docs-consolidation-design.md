# Knowledge-Architecture Consolidation — Design Baseline

**Date:** 2026-06-07
**Status:** Design approved (brainstorm complete) — ready to plan implementation
**Scope:** Documentation + knowledge-architecture only. No engine behavior changes. Doc-only blast radius.

---

## Goal

The Magnolia engine is feature-complete (build sequence 1–8 + de-personalization + the
3-PR factory, all merged). What it lacks is a **consolidated, current-state knowledge
layer**. Today the architecture lives scattered across point-in-time design docs in
`docs/plans/` (historical, not a living reference) and across five `CLAUDE.md` files,
and the design-system rules are split between `card_schema.py`, the theme tokens, and
prose in several places. A fresh agent can't yet read ONE coherent set of docs and "do
things the way they're best done."

Bring everything together so every future agent (and teammate) is on the same page —
optimized for **agent consumption first**.

## Design principle (the load-bearing decision)

The structure is derived from how an agent actually works here, not from a topic outline.

1. **Agents route to a question, they don't read cover-to-cover.** Two agent contexts hit
   these docs — the interactive session doing dev work on the engine, and the headless
   worker dispatched against a task. Both arrive with a question they need answered *now*.
   So docs are cut by **agent-moment**, and a router maps question → source.

2. **Canonical truth in this system is usually executable, not prose.** Skills are
   versioned, auto-discovered, executable instructions. `card_schema.py` *is* the
   design-system gate. `profile_lib.py` *is* the identity API. `test_engine_no_jay.py`
   *is* the de-personalization spec. `_contract.py` *is* the adapter law. A prose doc that
   re-explains any of these becomes an anti-DRY liability the moment the code changes.

3. **Therefore the reference layer is a thin `map + invariants` layer**, doing only the
   three things prose is uniquely good at and code/skills can't:
   - give the **mental model** of how subsystems interlock,
   - state the **cross-cutting invariants no single file owns**,
   - **route to the executable canonical source** ("…the lifecycle lives in
     `meta-factory-core`; the gate is `card_schema.py`").

   Every subsystem section ends in an explicit **"canonical source: X"** line. The docs
   never become a second copy of what the code already says.

This is "simplicity is the architecture" applied to the docs themselves: the minimum an
agent must read to act correctly, and never a duplicate of executable truth.

## Audience

**Agent-first.** Terse, router-style, high signal density, `file:line` citations,
"do it the best way" rules. Teammates can still read it; it is not hand-holding. The two
existing localized READMEs (`profile/README.md`, `themes/README.md`) are accurate and
stay **canonical** — reference docs link to them, never copy them.

---

## Target structure

### Router layer — the CLAUDE.md hierarchy (scoped as Claude Code already scopes)

- **`CLAUDE.md` (root)** — slims from dumping-ground to **router**. Leads with a one-block
  invariants summary + link to `docs/reference/invariants.md`, then a question→source
  table. The inline task-CLI / cron / LangFuse prose moves *out* to `architecture.md`.
- **`.claude/CLAUDE.md`** — keep (it is good). Trim the parts that now live in
  `architecture.md`; point at the reference docs.
- **`ui/task-board/CLAUDE.md`** — keep. **Fix the `:8742`→`:8743` dev-port bug** (line 6).
  Point at `design-system.md`.
- **`datasets/research/CLAUDE.md`, `datasets/strategy/CLAUDE.md`** — leave as-is (scoped
  content-mode defaults; out of this consolidation's scope).
- **`~/CLAUDE.md`** — operator's home env, out of repo scope. Informs layering only; the
  repo docs stay operator-agnostic (the engine is de-Jay'd; docs that ship to teammates
  must not re-personalize it).

### Reference layer — `docs/reference/` (new)

| File | Agent's moment | Contents |
|---|---|---|
| **`invariants.md`** | "What must never break?" — loaded first, by everyone | The laws + their enforcing command, one line each: *rule → why → executable check.* Covers: engine stays de-personalized · gates stay green · token-only card schema · capture-to-profile · Tier-2 confirm before first external write · never-delete/append-version · dev:8743 ≠ prod:8742. Pure law. |
| **`architecture.md`** | "How does this fit together — where do I make this change?" | Engine map: spine (engine/profile/content) → subsystems → the **seams** between them. Subsystems: skill/pack system + auto-discovery; worker dispatch (workers scope / skills instruct); the pluggable adapter seam + Tier-2 gate; profile + instruct-to-read-profile de-personalization; **the factory (first-class section: `meta-factory-core` spine + 3 `meta-create-*` siblings)**; eval substrate (files+git+board, LangFuse as power-user opt-in); cron. Each section ends "canonical source: X." Absorbs the task-system/cron/eval prose from root CLAUDE.md. |
| **`conventions.md`** | "I'm about to act — what's the right way?" | The rhythm: superpowers loop (brainstorming → writing-plans → subagent-driven-development with two-stage review: spec then code-quality → live e2e → finishing-a-development-branch); *when* in that loop the green gates run; capture-to-profile-not-artifact; capability tiers (Tier-2 = anything writing to the outside world); the factory spine; never-delete output convention; dev/prod board safety. References `invariants.md` for the laws; does not restate them. |
| **`design-system.md`** | "I'm touching the board / cards / themes." | UI-surface rules: token-only HARD RULE, card schema (slot order, signals/actions/body-renderers), the composition-only vs new-JS boundary, the Moods/theme-token system. Links `themes/README.md` + `_TEMPLATE.css` + `card_schema.py` + `cardtypes/registry.json` as truth. |

### Stays canonical, linked not copied

- `profile/README.md` — `architecture.md` links to it for profile schema/API.
- `ui/task-board/themes/README.md` — `design-system.md` links to it for the add-a-mood steps.

### Archive, untouched

- `docs/plans/**` — the historical design + implementation record. Distill current truth
  *out* of it into the reference docs; never turn the plans into the reference.

---

## Ownership boundaries (prevent drift)

- `invariants.md` owns **laws + enforcing commands**. `conventions.md` owns **when/how**
  in the workflow — and references the laws rather than restating them. The green-gate
  commands live in `invariants.md` (as enforcement of "gates stay green"); `conventions.md`
  only says when to run them.
- The factory's operational lifecycle lives in the 5 `meta-*` skills (canonical).
  `architecture.md` describes the **seam + spine** and links; it does not duplicate the
  skill steps.
- Design-system enforcement lives in `card_schema.py` (canonical). `design-system.md`
  explains the model and the composition boundary and links; it does not re-spec the gate.

## Accuracy fixes folded in (surfaced during inventory)

1. `ui/task-board/CLAUDE.md:6` — *"Default dev URL: http://localhost:8742"* contradicts the
   prod:8742 / dev:8743 split. Fix in the UI CLAUDE.md; state the split canonically in
   `invariants.md` + `conventions.md`.
2. Root `CLAUDE.md` documents **LangFuse as the system of record** for prompts/traces/scores.
   Master-design §5 moved that to native files+git+board with LangFuse as a *silent
   power-user opt-in*. Reframe accordingly in `architecture.md`.
3. General rule for the whole pass: **verify every file name, flag, function, CLI subcommand,
   and path against the real tree before documenting it.** If a doc and the code disagree,
   the code wins and the discrepancy is surfaced.

## Non-goals

- No changes to engine behavior, skills' logic, adapters, or the board.
- No new tooling or framework. Markdown only.
- Not re-documenting what skills/code authoritatively own — link instead.
- `datasets/*/CLAUDE.md` content-mode docs are out of scope.

## Safety / gates

- Reference docs live in `docs/`, which `test_engine_no_jay.py` does **not** scan.
- If trimming touches any `scripts/workers/*.md`, `.claude/skills/**/*.md`,
  `.claude/commands/*.md`, or `scripts/adapters/**/*.py`, the de-personalization gate must
  stay green: `python3 -m pytest tests/test_engine_no_jay.py`.
- Full suite stays green if any code is touched: `python3 -m pytest`,
  `python3 scripts/card_schema.py`.
- Doc-only work, no external blast radius. Branch → commits → PR against `main`; may merge
  when green and structure-approved (confirm before merging).

## Open questions (carry into planning)

- Exact landing spot for the task-CLI quick-reference: a section of `architecture.md` vs a
  short callout in root `CLAUDE.md`. Lean: full reference in `architecture.md`, one-line
  pointer in root.
- Whether `conventions.md` should embed a compact superpowers-loop diagram or just link to
  the superpowers skills. Lean: brief inline summary + links (the skills are canonical).
