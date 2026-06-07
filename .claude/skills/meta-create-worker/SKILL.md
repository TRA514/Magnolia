---
name: meta-create-worker
description: Use when the operator asks to build, add, or scaffold a new background worker / agent for a kind of task - generates a profile-driven scripts/workers/<name>.md, validates it, and emits a Keep/Undo receipt card
---

# Create Worker

Scaffold a new background worker (`scripts/workers/<name>.md`) that the dispatcher
matches and runs. **Read `meta-factory-core` first** — this skill is its worker
specialization. Reuses `meta-create-skill`'s RED-GREEN-REFACTOR spine.

## When to Use

- The operator wants a new kind of task handled autonomously ("build me a worker that
  files bugs", "add an agent that drafts release notes").
- **Not** for a new card type (use `meta-create-card-type`) or a new external
  integration (use `meta-create-adapter`).

## The Gate (must be green before commit)

1. `python3 scripts/factory_lib.py validate-worker scripts/workers/<name>.md` → `ok`
   (frontmatter parses + required fields present).
2. `python3 -m pytest tests/test_engine_no_jay.py -q` → passes (the new worker is
   denylist-clean — it reads team/identity specifics from `profile/`, never hardcodes).
3. The dispatcher loads it: `python3 -c "import sys; sys.path.insert(0,'scripts'); import task_dispatch; print(any(w['name']=='<name>' for w in task_dispatch.load_workers()))"` → `True`.

## Workflow

1. **Capture the spec.** Ask what tasks it handles, the title/description keywords
   that should route to it, which tier (`light`/`standard`/`deep`), tools, and skills.
   For team-specific nuance with no profile field (required fields, title format,
   labels), write it to the profile — do **not** put it in the worker:
   `python3 -c "import sys; sys.path.insert(0,'scripts'); import profile_lib; profile_lib.set_integration_conventions('project_management', '<nuance>', provider='jira')"`
   (use the relevant category/provider). Structured targets (board/project/assignee)
   are already in `profile/integrations.yaml` — the worker reads them at runtime.
2. **Scaffold** `scripts/workers/<name>.md` from the skeleton below. Fill the
   frontmatter; keep the body's "read specifics from profile" boilerplate.
3. **Gate** — run all three gate checks above. Fix until green.
4. **Commit + receipt** — `python3 scripts/factory_lib.py commit-and-receipt --summary "a <name> worker" --kind worker scripts/workers/<name>.md`
   (add any profile file you changed to the same command's file list).
5. **Hand back** — tell the operator: *"Built you a `<name>` worker → it's on the
   Workers tab and there's a receipt card. Keep / Undo."* Never mention git.

## Worker Skeleton (token-only, profile-driven, denylist-clean)

```yaml
---
name: <worker-name>
description: <one-line trigger — what tasks this worker handles>
priority: 10
tier: standard          # light | standard | deep — cheapest model that does the job well
match:
  task_type: []
  domains: []
  title_patterns:
    - "(?i)<keyword>"
  description_patterns: []
allowed_tools:
  - "Bash(*)"
  - "Read(*)"
  - "Write(*)"
skills: []
langfuse_prompt: "worker-<worker-name>"
timeout: 300
max_turns: 15
---

You are the PM-OS <role> agent working in this project. Read and follow CLAUDE.md.

## Your Focus

<what this worker specializes in>

## Team specifics

Read any team-specific configuration and conventions from `profile/` at runtime —
never hardcode them here. For external systems, read the target from
`profile/integrations.yaml`; read free-form team conventions from the relevant
`conventions` field. If a field is unset, proceed without it and flag it for the
operator's review. Sound like the operator by reading `profile/voice/*` when drafting.

## Available Skills

{skills_catalog}

## Your Assignment

Task {task_id}. Follow these steps:

0. Read CLAUDE.md in the project root.
1. Read the full task: `./scripts/task.sh show {task_id}`
2. Mark it started: `./scripts/task.sh agent:start {task_id}`
3. <do the work, reading profile/ for any team/identity specifics>
4. Finish one of:
   - Done: `./scripts/task.sh agent:complete {task_id} --output "<path>"`
   - Need a decision: `./scripts/task.sh agent:ask {task_id} "your question"` then STOP
   - Failed: `./scripts/task.sh agent:fail {task_id} --error "what happened"`

{rerun_block}Important rules:
- Read the task and any source meeting first.
- Read identity/team specifics from `profile/`, never hardcode them.
```

## Iron Laws

1. **The worker reads team/identity specifics from `profile/`** — never hardcoded.
2. **Gate green before commit** (validate-worker + test_engine_no_jay + dispatcher loads it).
3. **Stage only the worker file (+ any profile change)** via `factory_lib`.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Hardcoding the board/project/assignee in the worker | Read from `profile/integrations.yaml` at runtime |
| Hardcoding "always set Sprint" in the prompt | Capture it to `conventions` in profile |
| Committing before `test_engine_no_jay` passes | Run the gate first |
| Telling the operator about the commit | Speak in Keep / Undo |

## Related Skills

- **meta-factory-core**: the shared lifecycle + capture-to-profile rule (read first).
- **meta-create-skill**: the TDD spine.
