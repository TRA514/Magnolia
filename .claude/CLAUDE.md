# .claude/ Configuration Reference

Tooling reference for the `.claude/` directory. For project-level guidance, see `/pm-os/CLAUDE.md`.

## Modes

Two operational modes routed by working directory or invoked command:

1. **Product Mode** (default outside `datasets/marketing/`)
   - Outputs: backlog/roadmap, customer briefs, internal docs, PRDs
   - Sources: `datasets/meetings/**`, `datasets/product/**`
   - Commands: `/project:*`, `/metrics:*`, `/task:*`, `/strategy:*`

2. **Content Mode** (inside `datasets/marketing/**` or when `/content:*` runs)
   - Outputs: briefs, outlines, drafts, verification reports, snippets
   - Non-negotiables: intent-first, footnote+verbatim quote per factual sentence, grade 8 readability, no em dashes, "(source needed)" stops processing
   - Sources: `datasets/marketing/content/**/inputs/**`, verified meeting files

If both could apply and the user invokes `/content:*`, prefer Content Mode.

## Skills (`.claude/skills/`)

Skills auto-discover from `.claude/skills/<name>/SKILL.md` (flat — one level deep). They appear in the available-skills system reminder at session start with their `description` as the trigger. Drop a new SKILL.md into a new directory and it just works — no manifest, no registration step.

### Naming convention

Category prefix, then skill name:

| Prefix | Category |
|---|---|
| `meta-` | System / skill management |
| `quality-` | Validation gates |
| `context-` | Reusable context assembly |
| `workflow-` | End-to-end workflows |
| `metric-` | Metrics analysis |
| `task-` | Task management |

### SKILL.md format

```yaml
---
name: workflow-cs-prep
description: Use when [trigger condition] — [what the skill does]
allowed-tools: Read, Grep, Glob, Bash
---

# Skill body
```

Keep `description` action-oriented and trigger-led ("Use when…") so the skill matches against user intent.

### Skill packs

`.claude/packs.yaml` groups skill folders into packs (`core`/`pm`/`exec`/`eng`/`recruiting`/`ops`). The active list lives in `profile/config.yaml` `active_skill_packs`; `core` is always active. Packs gate the **background-worker dispatch catalog** and the Profile UI — not your interactive session (native auto-discovery there is unchanged). To add a skill to a pack: drop the folder in `.claude/skills/` (auto-discovered), then add its folder name to a pack's `skills:` in `packs.yaml`. A skill in no pack stays always-available.

## Slash Commands (`.claude/commands/`)

Command files (`.claude/commands/<name>.md`) are thin wrappers that point at a skill. Auto-registered by Claude Code; appear as `/<namespace>:<name>` in the available-skills list. Adding a new command means dropping a new file — no registration.

Most commands say "MANDATORY: use the X skill" and reference the path. Auto-discovery means Claude can also invoke the underlying skill directly via the `Skill` tool when description matches.

## Hooks (`.claude/hooks/`)

`hooks.json` registers a SessionStart hook (fires on `startup|resume|clear|compact`) that runs `session-start.sh`. The script reads `.claude/skills/meta-using-skills/SKILL.md` and injects it as `additionalContext` wrapped in `<EXTREMELY_IMPORTANT>` tags. This is the bootstrap that establishes the mandatory skill-usage protocol every session.

## Settings

- `settings.local.json` — project-scoped settings (permissions, env vars, hooks)
- `~/.claude/settings.json` — global settings (enabled plugins, e.g. `superpowers@superpowers-marketplace`)

## Tools & Permissions

Default-allow: file read/write, dir listing, diffs, local shell in safe paths. Ask before: MCP tools that modify external systems (Asana, HubSpot, Jira publish), deleting files. Prefer create/append; minimal idempotent diffs.
