---
name: workflow-magnolia-build
description: Use when starting any new Magnolia engine feature, epic, or build — the operator runs /magnolia-build, drops a PRD, or says "build X". Loads the operating context and runs the brainstorm → plan → build → verify → ship loop in line with precedent.
---

# Magnolia Build — the feature-build preamble

The operator just wants to start building and not retype the operating rules. This skill is
the preamble: it loads how-we-find-things and how-we-work from the reference layer, then runs
the standard loop. It is a **trigger, not a manual** — it links to the canonical docs rather
than restating them.

## When to use
- The operator runs `/magnolia-build`, or says "build X", "let's build", "new feature/epic", or drops a PRD/spec.
- Assume epic-level complexity by default; scale down if the ask is small.

**When NOT to use:** trivial one-line fixes (just do them); PM-artifact work like PRDs/strategy (use the `workflow-*` PM skills); creating a *single* skill/worker/card-type/adapter where the operator already knows the shape (go straight to the matching `meta-create-*` skill).

## Step 0 — Preflight: is this environment ready? (don't assume; check)
This loop depends on tools and state that are **not guaranteed on a fresh clone**. Verify each before relying on it; remediate or route, don't barrel ahead.

- **Superpowers plugin** — Step 5 *is* the superpowers skills. Confirm `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:subagent-driven-development`, and `superpowers:finishing-a-development-branch` appear in the session's available-skills list. If they're absent, the plugin isn't enabled for this user (it lives in per-user Claude Code config, not the repo). Install it before proceeding: `/plugin` → add the `superpowers-marketplace` marketplace → enable `superpowers@superpowers-marketplace`, then confirm the `superpowers:*` skills now appear. **Never silently fall back to ad-hoc building if they're missing** — the loop's discipline comes from these skills.
- **Profile populated** — the engine reads person/team identity from `profile/` (invariant #1). If `profile/` is missing or unpopulated, this is a first-time user: route to **`meta-onboard`** first. Don't proceed with de-personalization rules against an empty profile.
- **Git author is *theirs*** — set the local git author to the *current* user's own identity, not whoever set up the repo (see Step 2). Confirm `gh auth status` is authenticated before any PR step.
- **Dev board runs** — e2e verification (Step 5.4) assumes the board starts on `localhost:8743`. On a fresh clone, dependencies may not be installed; if the board won't start, install/setup per `ui/task-board/CLAUDE.md` before claiming e2e verification.

If anything here is degraded or unclear, the **`workflow-doctor`** skill detects and remediates capabilities conversationally — reach for it rather than guessing.

## Step 1 — Ground in the reference layer (read first)
Read, in order: `docs/reference/invariants.md` (the laws — load before acting), `docs/reference/conventions.md` (the working rhythm), and the relevant section(s) of `docs/reference/architecture.md` for whatever subsystem the build touches. This is where the dev/prod split, the green gates, branch + author discipline, and capture-to-profile live — honor them by reference; do not re-derive them.

## Step 2 — Kickoff (set context once, ask the one thing)
State briefly that you've loaded the invariants + conventions and will work the standard loop. Then ask **merge authority for this build**: *"Merge to main when it's green, or open a PR for you to merge?"* Remember the answer for this build. Default branch off `main`, set the git author locally to **the current user's own identity** (their name + their GitHub no-reply email — never inherit whoever last configured the repo), and end commits with the standard `Co-Authored-By` trailer (per conventions). If the local author isn't set, ask for it rather than assuming.

## Step 3 — Take the ask
Accept a PRD/spec path, pasted details, or a freeform conversation. If the ask is thin or ambiguous, ask a few targeted clarifying questions before designing — do not guess at scope.

## Step 4 — Route
- **Known engine extension** (a new worker, card-type, adapter, or skill): hand off to the matching factory skill — `meta-create-worker` / `meta-create-card-type` / `meta-create-adapter` / `meta-create-skill` (each reads `meta-factory-core` first). They own scaffold → capture → gate → commit → Keep/Undo.
- **Larger / novel / cross-subsystem feature:** run the full loop (Step 5).

## Step 5 — Run the loop
Follow the superpowers workflow, in order:
1. `superpowers:brainstorming` — design first; 2–3 options + a recommendation; get approval before writing. The operator owns WHAT; the skills own HOW.
2. `superpowers:writing-plans` — bite-sized TDD tasks with the green gates baked in.
3. `superpowers:subagent-driven-development` — fresh subagent per task with two-stage review (spec-compliance first, then code-quality). For epic scale, consider git worktrees / parallel dispatch for independent tasks. (Tell subagents to inspect history with `git show`/`git diff`, never `git checkout` — switching branches mid-run derails the working tree.)
4. Live e2e verification — run the real board/feature and observe the change, not just tests.
5. `superpowers:finishing-a-development-branch` — then branch → PR → merge per the kickoff merge authority.

## Iron laws (non-negotiable)
- **Brainstorm before building.** No code until a design is approved — even when it "looks simple."
- **Gates green before every code commit** (invariant #2) and **never commit to `main`** — branch always.
- **The engine stays de-personalized** (invariant #1): capture team/person nuance to `profile/`, never into the artifact (invariant #4).
- **Dev board only** (invariant #7); never operate the production install from engine work.
- **Git stays invisible to the operator** where the factory handles it: speak Keep/Undo, not commits/reverts.

## Success criteria
- Preflight passed: the superpowers skills were present (installed if not), the profile was populated (onboarded if not), and the git author was the current user's own.
- The operator typed `/magnolia-build` (or equivalent) and never had to restate the operating context.
- The reference layer was read before any code was written.
- The build went through brainstorm → plan → subagent-driven build → e2e verify → ship, with gates green and the engine denylist-clean.

## Related skills
- **superpowers:brainstorming**, **superpowers:writing-plans**, **superpowers:subagent-driven-development**, **superpowers:finishing-a-development-branch** — the loop.
- **meta-factory-core** and the **meta-create-\*** family — the routing target for known engine extensions.
- **meta-onboard** — first-time setup when `profile/` is unpopulated; **workflow-doctor** — detect/remediate a missing or degraded capability (e.g. the superpowers plugin, `gh` auth, the dev board).
