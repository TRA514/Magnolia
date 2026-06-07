# /magnolia-build

MANDATORY: Use the `workflow-magnolia-build` skill (`.claude/skills/workflow-magnolia-build/SKILL.md`).

The preamble for building a new Magnolia engine feature or epic. Type `/magnolia-build` and then talk, or drop a PRD/spec — the skill loads the operating context (the laws in `docs/reference/invariants.md`, the rhythm in `docs/reference/conventions.md`, the relevant `architecture.md` section) and runs the standard loop so you don't retype any of it.

## Arguments
- (no args) — start talking; the skill takes it from there and asks clarifying questions if the ask is thin
- `--prd <path>` / `--spec <path>` — point it at a PRD or spec to build from
- freeform text — describe the feature inline

## What it does
Grounds in the reference layer → asks merge authority once → takes your ask → routes (a known engine extension goes to the matching `meta-create-*` factory skill; anything larger runs the full loop) → brainstorm → plan → subagent-driven build with two-stage review → e2e verify → ship per your merge choice. Assumes epic-level complexity by default.
