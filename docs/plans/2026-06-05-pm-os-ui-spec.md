# PM-OS UI Spec — for Claude Designer

**Date:** 2026-06-05
**Purpose:** A self-contained brief to generate the new/changed frontend (HTML / CSS / JS) for the team-portable PM-OS. Hand this to Claude Designer; bring back the files for integration.
**Companion:** `2026-06-05-pm-os-portability-design.md` (the architecture this UI sits on).

---

## What this UI is

PM-OS is a **chief of staff**, not a task board you operate. The screen's job is to lower cognitive load and anxiety: surface what needs the user, in order, calmly — then get out of the way. AI is frenetic; this is the calm place. Every visual decision serves *calm, focus, and trust*.

**Stack constraints (must hold):**
- Vanilla **HTML + CSS + JS**. No SPA framework. Evolve the existing `ui/task-board/`, don't rewrite it as React.
- **Theme system is sacred.** All color/radius/spacing/transition come from CSS custom properties scoped to `:root[data-theme="<mood>"]`. **No component may hardcode a color or radius** — only reference tokens. New surfaces must look correct across *every* existing and future mood (Organic, Modafinil, Breathe, Zen Garden, Vantacan, …).
- CSS and JS stay cleanly separated (current codebase already does this well).

## Information architecture (already established — keep)

Five surfaces, sorted by *what they want from the user* and *cadence*:

- **Now** (daily, default) — Recommendations feed (top) · Review (artifacts you're accountable for) · People (human + waiting, communication-centric).
- **Activity** (daily skim) — the receipts stream; reverse-chron, filterable.
- **Quality** (weekly, read-only) — trust dashboard by task-type.
- **Engine** (rare config) — workers, prompts, skills **+ the new Profile/Config room (this spec)**.
- **Schedules** (rare config) — recurring job definitions.

**This spec focuses on the NEW or CHANGED pieces:** the Profile/Config room, the declarative card-registry renderer, and three new card kinds (Recommendation, Receipt, Graduation). The existing tabs stay; design these to drop into them.

---

## 1. The card-registry renderer (foundational)

Today card rendering branches on `task_type` in JS. Replace with a **single generic card component driven by a declarative schema**, so new card types need no new rendering code.

**A card schema declares these slots** (any may be absent):

| Slot | Contents |
|---|---|
| `head` | queue/kind glyph (left) · id + judge score chip (right) |
| `title` | one line, the thing |
| `context` | domain · source (origin meeting/cron) · customer · tier badge |
| `signals` | status, agent-running pulse, flags ("judge flagged", "needs re-auth") |
| `body` | kind-specific slot(s): a diff, a message draft, an artifact preview, a metric, a preview image |
| `actions` | 1–N buttons; the *primary* action is visually dominant |

Design the **generic card shell** + a **slot system**, then show how the three card kinds below fill it. The judge **score chip** (e.g. `8/10`) sits in the head with a tone class (good / ok / low) — tone maps to theme tokens, never raw color.

**States to design for every card:** default, hover, expanded (inline detail), agent-running (subtle pulse, not a spinner farm), error/degraded, success-after-action (gentle confirmation, then settle).

## 2. Three new card kinds

### a. Recommendation card (the chief-of-staff's standup)
The load-bearing surface at the top of **Now**. Each is a **proposal** the user disposes of in one tap. Sources: hygiene, judge flags, conversion audits, rubric changes, promotions.

- **Anatomy:** title is the proposal ("3 human tasks look like message drafts — let agents draft them?") · short rationale · body may show the affected items or a diff · actions: **Accept** (dominant) · **Reject** · optional **Snooze**.
- **Density:** default to a **digest** (one rollup card per audit) with expandable line-items; spawn individual cards only for high-confidence single actions.
- **Empty state matters** — an empty feed should feel like *calm/done*, not broken. Design the "all clear" state deliberately.

### b. Receipt card (past tense, "I already handled it")
What the machine already did. Default state is *fine*; wants a skim, then auto-archives (~7 days) unless flagged.

- **Anatomy — exactly three things:** *what it did* (the diff / what changed) · *how well* (judge score + one-line why) · *one reversible affordance* (**Undo** or **Flag**).
- Lives in **Activity**. This is also where a **generated-capability receipt** appears: *"Built you an Asana card type → [preview]. Keep / Undo."* (preview = a small rendered sample of the new card type). Undo is a friendly remove — never show git.

### c. Graduation card (trust, made visible)
Created by the graduation cron when a task-type is ready to climb **shadow → gated → autonomous**.

- **Anatomy:** title ("PRD-draft is ready to graduate to *gated*") · the **evidence**: score trend sparkline, judge↔you agreement %, rolling-window approval rate, and 2–3 **example runs** (linkable) · a plain-language explanation of *what changes* if graduated · actions: **Graduate** (dominant) · **Not yet**.
- Must feel **reassuring and reversible** — copy should note auto-demote if quality drops. This is a trust moment, design it with weight but not alarm.

## 3. The Profile / Config room (in Engine)

For non-technical users who never open a file. Everything writes to `profile/*.yaml|md` underneath. Calm, sectioned, form-light. Sections:

1. **Identity** — name, email, company, persona (PM / Exec / …), timezone.
2. **Integrations** — per category (Transcripts, Project management, Calendar), a chooser showing the available adapters and which is active, each with a **live capability/auth status** dot (✓ authorized · ⚠ needs re-auth · ✗ not set up) and a **"Fix / Authorize"** button that triggers the doctor's guided flow. *This is where the standing self-heal surfaces.*
3. **Voice** — editable `teams.md` and `email.md` shown as friendly editors with a "this is how you sound" framing and a regenerate-from-history option.
4. **Skill packs** — current packs as chips; an **"Add / swap pack"** affordance (one click) listing available packs (PM, Exec, …) with short descriptions. No terminal.
5. **Model posture** — a simple low↔high cost-posture control with plain-language explanation ("cheapest model that still does a great job"), plus per-worker tier visible read-only.
6. **System status** — server running indicator + `localhost:<port>` link, "restart server," and the doctor's overall health summary (what's installed/authorized, what's degraded and why).

**Degraded-feature treatment:** when an integration/tool is missing, the features that depend on it appear **present but quietly disabled with a one-line "why + fix,"** not hidden and not error-spewing. Mirror the graceful-degradation philosophy visually.

## 4. Onboarding presentation

Onboarding runs as **tasks/cards in the system** (it doubles as the tutorial). Design how an onboarding card looks and how the sequence progresses (a gentle step indicator, one focus at a time). The first-run experience should feel like being *welcomed and set up by a chief of staff*, not configuring software. Include the moment where the server spins up and the board first appears.

---

## Tone & motion

- **Calm > snappy.** Transitions are soft and brief; nothing flashes or demands. The existing "mood-meld" transition is the reference feel.
- **One thing at a time.** Whitespace and ordering do the triage; avoid dense competing surfaces.
- **Plain language everywhere.** No jargon, no git, no model IDs surfaced unasked. Blast-radius and trust are explained in words a COO reads comfortably.

## Deliverables

HTML / CSS / JS for: (1) the generic card-registry shell + slot system, (2) the three new card kinds, (3) the Profile/Config room, (4) the onboarding card flow — all **token-only** so they inherit every theme. Provide them as drop-in files referencing the existing token contract (`:root[data-theme="…"]`).
