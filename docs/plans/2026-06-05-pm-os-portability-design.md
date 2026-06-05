# PM-OS → Team-Portable: Design Baseline

**Date:** 2026-06-05
**Status:** Design approved (brainstorm complete) — ready to plan implementation
**Companion:** `2026-06-05-pm-os-ui-spec.md` (frontend spec for Claude Designer)

---

## Goal

Turn PM-OS, today a chief-of-staff system deeply personalized to one person (Jay), into something a non-technical teammate at the same company can install, onboard into, and run on their own machine — without losing the architecture and design philosophy that make it work.

**Primary persona:** Product Managers. **Secondary:** executives with heavy meeting loads.

## Non-negotiable principles (inherited, must survive)

- **It is a chief of staff, not a task board you operate.** It lowers cognitive load and anxiety: surfaces what needs you, in order, calmly. AI is frenetic; this is the calm place.
- **Simplicity is the architecture.** Tasks are markdown. Scripts are simple Python. UI is simple HTML/CSS/JS. The magic is a lightweight harness letting headless Claude do work in the background. Every decision below must keep that true.
- **Local-first.** Runs per-person on a Mac or Windows machine. No central server, no required cloud dependency.
- **Markdown + git, not databases and Docker.** Where we need versioning, state, or observability, prefer files and git over infrastructure.

---

## 1. The spine: Engine / Profile / Content split

One refactor makes everything else possible. Today identity ("Jay", "Vantaca", the Jira assignee UUID, Otter, Pendo/Databricks tenant IDs) is scattered through the engine. We separate three layers:

```
pm-os/
  engine/        ← shared, git-tracked. You improve it; teammates pull updates.
    scripts/ .claude/ ui/ adapters/ cardtypes/ packs/
  profile/       ← gitignored, per-person. The ONLY place "who am I" lives.
    profile.yaml         name, email, company, persona, timezone
    integrations.yaml    transcript: granola · project-mgmt: asana · calendar: m365 …
    config.yaml          model posture, paths, feature toggles, active skill packs
    voice/teams.md  voice/email.md
    capabilities.json    what the doctor has verified is present / authorized
  datasets/      ← per-person content (already gitignored)
```

**The rule:** the engine reads identity and integration facts *only* from `profile/`. No "Jay", no "Vantaca", no hardcoded tool IDs anywhere in `engine/`. This is the bulk of the work and it is mechanical — a sweep already mapped every hardcoded reference (see §10).

## 2. The profile layer (this is "settings")

Plain YAML and markdown — on-philosophy, human-readable, diffable. **Editable two ways:**
- **By hand** (you, power users).
- **Through the board's config room** (the *Engine* tab) for non-technical users, who never open a file.

The voice cards live here and are **exposed for editing in settings** so a user can adjust how the system sounds as them.

## 3. Onboarding — conversational, task-driven, in Claude Code

The teammate clones once, opens Claude Code in the folder, types **"onboard me."** Onboarding is itself a sequence of **tasks in the system**, so it doubles as a tutorial: the user learns the product by being chief-of-staff'd through their own setup.

Steps:

1. **Identity** — name, role/persona, company.
2. **Existing-install detection** — *"Already running a PM-OS with a `datasets/` folder and skills?"* If yes → locate that directory and **install congruent with it** (adopt/merge their content and custom skills rather than clobbering). If it can't auto-reconcile, **warn clearly and guide** rather than overwrite.
3. **Integrations interview** — *"Otter or Granola? Jira, Asana, Linear, or none? Teams/Outlook ready?"* → writes `integrations.yaml`, selects the adapters (§6).
4. **Doctor pass** (§4) — installs and authorizes what those choices require.
5. **System spin-up + persistence** (§4) — starts the local server, verifies it serves, **auto-opens (or hands over) the `localhost:<port>` URL**, installs the reboot-persistence mechanism, and teaches the on-switch.
6. **Voice discovery** — studies the user's meeting + message history, drafts `voice/teams.md` and `voice/email.md`, lets them tweak: *"Here's how you sound. Change anything?"*
7. **Pack selection** — activates core + their persona pack (§8).

Ships **Teams + Outlook ready to go** by default (M365), since that's the common case.

## 4. The Doctor / self-heal layer

A first-class subsystem, cross-platform (`brew` + Terminal on Mac; `winget`/`choco` + PowerShell on Windows). Pattern: **detect → guide → auto-remediate; the human does only the irreducible minimum.**

- **Detect** what's installed (qmd, pandoc, claude CLI, python deps) and what's authorized (each MCP).
- **Auto-remediate where possible** — opens the terminal, runs the install/command. The human only does what truly can't be automated: click "Authorize" in a browser, type a password, paste a token.
- **Graceful degradation** — a missing capability disables *only* its features; everything else runs. (LangFuse already degrades this way; generalize the pattern.)
- **Standing self-heal loop** — like Otter reauth today, it proactively surfaces *"Jira needs re-auth — walk you through it?"* as a recommendation when tokens expire. Not just a one-time setup gate.

### Server lifecycle + reboot persistence (part of doctor/onboarding)

The board only exists if the Python server is running. The doctor:
- **Starts** the task server and **verifies** it is serving locally.
- **Hands over / auto-opens** `localhost:<port>`.
- **Installs persistence** so it survives a restart: **LaunchAgent** on Mac (same pattern as the existing Ollama / Otter-sync agents), **Task-Scheduler-at-logon or a service wrapper** on Windows.
- **Teaches the on-switch** and provides a one-tap "is it running?" check.

Goal: the user opens `localhost:<port>` and it is simply *there*, forever.

## 5. Eval & judge substrate (drop Docker LangFuse)

LangFuse-via-Docker is a non-starter for non-technical teammates. Its four jobs move to native, zero-install homes:

| LangFuse did | Now |
|---|---|
| Prompt store + versions | **Files in `engine/prompts/`; git is the version history** |
| Execution traces | **Local JSONL** (already written today) |
| Scores + annotations | **Task markdown frontmatter** (`judge_score`, `judge_why`, `human_react`, optional note) |
| The UI | **Board → Quality tab** |

This is **more on-philosophy than today**, and there's a governance win: prompts/outputs (which may contain customer data) never leave the machine.

**This substrate is load-bearing, not logging.** It is the fuel for the two loops that make this a chief of staff — both ship **in the box** as default crons:

- **Weekly self-improvement cron (in box).** Reads low scores + free-text annotations, clusters failures *by step* (worker-match / a specific skill / voice / output shape), and creates a **review card** each week: *"Here's how I'll try to get better this week, and what I suggest,"* with the proposed diff attached. The user **accepts or rejects on the card.** Nothing auto-applies. The fix can be at any altitude — a skill edit, a shared `voice.md`, a worker scoping change, a new quality gate, a golden example, or a judge-rubric change.
- **Graduation cron (in box).** Recurring job that assesses, per task-type, whether the judge is ready to climb the ladder (**shadow → gated → autonomous / chief-of-staff**). When a type meets criteria (high human-approval rate + high judge↔human agreement over a rolling window), it creates a **graduation card** carrying the data + example runs + agreement %, with a one-tap **"graduate this"** action. **Reversible** — if scores later drop, the type auto-demotes back. A trust budget per task-type.

LangFuse remains a **silent opt-in for power users** (set `LANGFUSE_SECRET_KEY` and the existing graceful-degradation wiring lights up). Jay's current setup survives; teammates never see it.

## 6. The factory (self-extension)

The goal is the *feeling* of "the system built it for me, and it belongs" — achieved at **authoring time** (durable, reviewable, consistent), **not** at render time (which would be inconsistent, slow, costly, and against the calm design system). Three moves:

1. **Declarative card registry.** Replace hardcoded `if task_type === '…'` rendering with a card-type **schema** (head / title / context / signals / body-slots / actions). New card types need *zero* new rendering code and inherit the theme by construction (§9). This registry + the theme tokens **is the design system.**
2. **Pluggable adapters** behind common interfaces:
   - **`project-management`** (`jira | asana | linear | azure-devops`) — the *external* team system of record. *(Note: the internal task system is the user's personal ticketing / to-do; this adapter is explicitly for pushing work out to the team's tool. `jira_publish.py` becomes one adapter.)*
   - **`transcript`** (`otter | granola | …`) — how meeting transcripts arrive and trigger extraction.
   - **`calendar`** (`m365 | google`) — scheduling.
   The profile picks which are live.
3. **`meta-create-*` skills** — headless Claude scaffolds a new adapter / worker / card-type from templates, following the design system.

**Generated things just land and work** — presented as a **receipt** in the board's own language: *"Built you an Asana card type → [preview]. Keep / Undo."* Undo is a silent `git revert`. **Git is never a user-facing concept.** Anything that writes to the outside world is **Tier 2** (§ capability tiers) and gets exactly one plain-language confirm before its first external action: *"This can now post to your Asana — okay to let it?"* Blast-radius is visible in plain words; git is invisible.

## 7. Model cost tiering

Principle: **use the cheapest model that still does a great job.**

- Each **worker declares a tier** heuristically from its job: a meeting summarizer → Haiku, a routine draft → Sonnet, a deep product/strategy review → Opus.
- **Persona sets a baseline posture** (a PM's defaults sit lower than a product-reviewer's).
- Dispatch passes `--model` per task to `claude -p` — **enforced, not advice.** The user can override per task.
- *Deferred (not v1):* judge-driven downshift suggestions ("these Opus runs scored identically to Sonnet — downshift?"). Nice-to-have, inferred from already-collected scores, no double-running.

## 8. Skill packaging

- **Always-on core** (everyone): tasks, search, meetings, onboarding, doctor, the factory.
- **Persona packs** (`pm`, `exec`, …): curated sets of skill folders.
- A "pack" is just which skill folders are present/active — **auto-discovery does the rest** (skills are standard Claude Code; dropping a folder into `.claude/skills/` just works).
- **The active pack list lives in `profile/config.yaml`**, not only in onboarding. Packs are **swappable any time** — the profile page needs an **"add/swap skill pack"** affordance (one click, no terminal). Further extensible via the factory.

## 9. Design system

Not a new framework — it is **the declarative card schema (§6.1) + the existing theme tokens.**

- **Hard rule:** a card schema may reference theme tokens **only** — never a hardcoded color, radius, or transition. This guarantees every generated card is **100% theme-aware**: look, interactions, colors, and the subtle per-mood differences all "just work" across every existing and future theme.
- Themes themselves stay **static** (no runtime generation). The requirement is only that *new card types render through the theme system*, so adding schemas never breaks the moods.

## 10. De-personalization cleanup (from the code sweep)

- **Security (do now):** the `MOCHI_API_KEY` was tracked in `.claude/settings.local.json`. Scrubbed from the new repo's working copy; **rotate the key** (it remains in the original repo's history/remote).
- **Template reset:** strip *all* personal content (datasets, tasks, voice, profile values) so the shared template is a clean, fully-moldable blank a new user shapes from scratch — not Jay's system with the name changed.
- **Move to `profile/`:** `/Users/jayjenkins/` in `.mcp.json`; `LANGFUSE_INIT_USER_NAME=Jay`; Jira `JIRA_DEFAULT_ASSIGNEE` UUID + cloud/project/component constants; Pendo subId + app IDs; Databricks catalog + source mappings; SharePoint/OneDrive paths in `sync_config.yaml`; `jay-voice.md` path in `judge.py`.
- **Purge stale foreign paths** in `settings.local.json` (`raleon.io`, `/Users/jay/llm/...`, `Read(//Users/**)`).
- **De-Jay the skills** that assume the operator: `task-extract-from-meeting` ("does Jay own this") → "does *the operator* own this", driven by `profile.yaml`; `metric-quarterly-rocks` (Jay's specific Rocks) → generalized or moved to profile.

## 11. Build sequence

1. **Engine / profile split** — the foundation; unblocks everything.
2. **Doctor + onboarding** — incl. server spin-up, reboot persistence, existing-install detection, graceful degradation.
3. **Adapters + declarative card registry** — `project-management` + `transcript` first (Jira/Asana, Otter/Granola).
4. **Eval substrate off Docker** (files + git + board) + wire both in-box crons (weekly self-improvement, graduation ladder).
5. **★ Write the UI spec → commission the design (Claude Designer).** Happens here, once the profile schema, card registry, and new card kinds (recommendation, receipt, graduation) are all defined, so the spec is complete. Backend work on steps 4→8 continues in parallel while the design is built; the returned HTML/JS/CSS comes back for integration. *(The UI spec itself is written as part of this design pass — see companion doc.)*
6. **Integrate the returned frontend** — profile/config room, theme-aware card registry, the new card surfaces.
7. **Skill packs (profile + factory) + model tiering** — polish.
8. **`meta-create-*` factory skills** — self-extension; last, builds on 3+4.

## 12. Out of scope (for now)

- Packaged installer (`npx create-pm-os` / `.dmg`) — defer until more than a handful of users; the engine/profile split makes it a thin shell to add later.
- Runtime generative UI (LLM redraws cards live).
- Mobile / push notifications — the briefing is the notification surface.
- Multi-user / central server — conflicts with local-first.

## Open questions (carry into planning)

- Existing-install **merge strategy** — adopt-in-place vs. copy-engine-alongside; how to reconcile divergent custom skills.
- Windows **persistence mechanism** — Task Scheduler at logon vs. a service wrapper (NSSM-style); pick the least-fragile for non-technical users.
- Graduation **criteria thresholds** — global vs. per-tier (roadmap leans per-tier, Tier 2 stricter).
- Capability-**tier source of truth** — declared per worker in frontmatter, enforced in dispatch.
