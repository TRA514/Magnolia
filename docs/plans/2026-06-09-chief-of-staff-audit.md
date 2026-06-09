# Chief-of-Staff Audit — highest-impact, philosophy-congruent improvements

**Date:** 2026-06-09
**Status:** Findings + recommendations (no code changes)
**Scope:** Full-system audit — engine scripts, board UI, skills layer, datasets/profile, docs — against the stated intent: a calm, low-anxiety, low-cognitive-load, local-files chief of staff that takes work off the team's plate.

> Method note: this audit ran against a fresh clone, where `profile/`, `datasets/*` content, `logs/`, and `cron/jobs.json` are gitignored per-person data. Findings about runtime behavior come from reading the code paths, not from observing a live install.

---

## Verdict

The architecture is unusually coherent and the vision docs (README / UX_VISION / ROADMAP) are honest about what's shipped vs. planned. The spine — judge scoring, trust ladder, Tier-2 gate, profile-driven de-personalization, factory self-extension, declarative card registry — is real and mostly built. The skills layer is well-formed (63 skills, clean format, minimal overlap). The plumbing is genuinely humble: markdown, git, stdlib Python, one HTTP server.

The gap is not architecture. It is three things:

1. **The system can fail silently, and trust is the product.** The whole design — ladder, receipts, "I handled it" — rests on the operator believing the machine. Several seams are fire-and-forget: a judge crash leaves a blank score forever, a lock-contended dispatch drops a task into permanent `queued`, a failed external write can vanish. Each silent failure spends trust the ladder can't earn back.
2. **The chief-of-staff verbs are the least built part.** The skill catalog is deep on PM *craft* (PRDs, metrics, strategy) and thin on the chief-of-staff *job* (triage my pile, chase what I'm waiting on, prep my 1:1, tell me what you did). The roadmap already knows this — the human-queue audit is marked "highest QoL priority" — and every primitive it needs now exists.
3. **The loop that makes it *learn* is half-wired.** Scores and reactions are captured; `eval_digest.py` clusters them; the improvement agent that turns a digest into a one-tap diff proposal is the missing half of the system's core differentiator ("capture ≠ learning").

The recommendations below are ranked by (impact × simplicity), filtered for congruence with the stated philosophy. Effort: **S** ≤ half a day · **M** 1–2 days · **L** multi-day.

---

## Part 1 — Ranked recommendations

### 1. Kill silent failure (the reliability pack) — **M**, highest impact

Trust is manufactured by the system being *predictably honest*, including about its own failures. Today four seams can fail without a card ever appearing:

- **Dropped dispatch on lock contention.** `task_dispatch.py:979-982` — if the lock is busy, the per-task dispatcher exits 0 and the task sits `open`/`queued` forever. Dispatch is event-triggered only (`task_server.py:964-994`, quick-add, cron); there is no periodic sweep that re-dispatches stranded tasks.
- **Judge dies blank.** `task_cli.py:255-274` spawns `judge.py` detached with failures explicitly swallowed. A judge crash/timeout = a completed card with no score, no error, no retry. This corrupts the calibration data the entire trust ladder depends on.
- **Agent failures hide.** `agent_status: failed` renders as a small mark on a card; the error is only visible by opening the modal. Nothing proposes a next step.
- **External writes don't retry.** Adapter calls run inline in route handlers; a transient Jira/Graph failure is lost. (The Tier-2 *confirm* is solid; it's the post-confirm execution that has no safety net.)

**The congruent fix is one idea applied four times: failure becomes a recommendation card.** The system already has the perfect vocabulary — the `recommendation` card type and the "system proposes, you dispose" principle. No alerting layer, no notification channel, no Celery/queue (all incongruent — see Part 3):

- A **dispatch sweep**: a tiny seeded cron (or a tick in the existing `cron_scheduler.py` daemon) that re-runs `task_dispatch.py` for anything `open + queued` older than N minutes. The lock is OS-level flock, auto-released on process death, so a sweep alone closes the gap.
- A **judge sentinel**: `agent:complete` stamps `judge_status: pending`; the sweep retries once, then writes `judge_status: failed` so the card honestly shows *unscored* instead of blank — and excludes it from graduation metrics.
- **Failed task → recommendation card**: "TASK-0123 failed: ‹first line of error› — retry / reassign / kill?" One tap each.
- A **file-based outbox** for adapter writes: record the pending external action in the task's frontmatter before attempting it; the sweep retries; after N failures it lands as a card. Plain files, no infra.

This is the cheapest unit of trust available anywhere in the system, and it's a precondition for ever flipping the ladder from advisory to enforcing.

### 2. Ship the human-queue audit + waiting-on nudges — **M**, the felt chief-of-staff moment

ROADMAP cron #2, already marked "highest QoL priority." This audit confirms it is now *pure wiring* — every primitive exists: the `recommendation` card type, the `message-writer` worker, judge scoring of drafts, the Tier-2 send path (proven end-to-end), the cron substrate, `waiting_on`/`waiting_expected` fields.

One weekly (or twice-weekly) cron + one worker that reads the human and waiting queues and emits one-tap recommendation cards:

- *"This has sat 9 days — kill / convert to agent / snooze?"*
- *"These 3 human tasks are really message drafts — let me draft them?"* (convert → message-writer runs → draft lands with review+send)
- *"Waiting on ‹person›, 5 days past expected — nudge? (draft attached)"*

This is the single feature that changes the *feeling* of the product from "a board I maintain" to "a counterpart who noticed." It also dissolves the People pile, which UX_VISION correctly identifies as the pile that actually hurts. The waiting-on nudge half doubles as the delegation dashboard the UI lacks — without building a dashboard.

### 3. Close the learning loop: the improvement agent — **M/L**

ROADMAP §1's missing half. `eval_digest.py` ships and the weekly cron is seeded; the `eval-analyst` worker exists but nothing converts a digest into a **collab card with an attached diff** that the operator can accept (Keep) or reject. The card registry already has the `diff` body renderer and accept/reject actions — the rendering and apply path exist (`/accept` applies a patch today).

Done-when stays exactly as the roadmap states: *a down-vote reliably produces a proposed change at the right altitude (skill edit / voice.md / worker scope / rubric) that you accept as a diff.* Include the **voice loop** here rather than as a separate feature: when the operator edits a drafted message before sending, the edit-diff is the highest-signal style data the system will ever get — feed it to the same improvement agent as a `voice.md` proposal. That's "learns how I'd say it" for free, inside an already-planned loop.

This is the system's core differentiator and the reason the architecture exists. Without it, the judge is a gauge, not a manager.

### 4. Surface failure and completion honestly on the board — **S**

The smallest calm-repair batch, all verified against the current UI:

- **Failed cards show the error inline** (first line of `agent_error` on the card face + tooltip). Today the operator must click to discover what went wrong — that's "did I break it?" anxiety by design (`board.js` status marks).
- **Activity gets pagination + a one-line summary** ("32 completed this week · 27 by agents"). 1,000 rows in one grid is the unbounded-pile feeling the philosophy forbids (`activity.js`).
- **Quick Add emits a receipt instead of asking confirmation.** Auto-dispatch on Enter is fine *if* the parse lands as a visible receipt-style toast with one-tap undo — reversibility over confirmation, per the README's own principle 5. Today there's neither confirm nor receipt.
- **Celebrate empty sections.** Suggestions already says "you're all caught up"; Decide/Review/People say "No tasks." A cleared lane is the product working — say so. Trivial, and it *is* the emotional product.

### 5. Pre-beta portability sweep — **S**, urgent only because beta is imminent

The denylist gate (`tests/test_engine_no_jay.py`) deliberately allows "Vantaca" (the engine is portable within the company — `test_vantaca_still_allowed`), so company references are fine. What the gate does **not** catch:

- **Real person names and verbatim meeting quotes in skill examples** — `context-search/SKILL.md` (real strategy-meeting quotes, named colleagues), `workflow-schedule-meeting` (named colleagues in code samples), plus scattered names in ~6 other skills. These ship to every teammate who pulls the engine.
- **`workflow-jira-home` hardcodes a component id (10011) and board specifics** that belong in `profile/integrations.yaml` per invariant #1's own mechanism.

Fix: scrub examples to placeholders, move Jira specifics to profile lookups with graceful fallback, and **extend the `DENY` list with teammate names** so the gate enforces this class of leak going forward. Also: add `quality-content-style` and `workflow-landing-page-creator` to a pack (or document that pack-less = always-available is intended for them).

### 6. Align the Quality tab with the ladder's unit: task-type — **S/M**

The ladder, rubrics, graduation, and promotion are all **per task-type**; the Quality tab scoreboard is **per worker** (`quality.js`). That's a real data-model misalignment: the screen meant to answer "can I trust this *type* more than last week" can't show the thing that graduates. Pivot the scoreboard rows to task-type (worker as a secondary facet). While there, make "task-type" an explicitly declared, documented field rather than a derivation — it is the system's central unit and deserves first-class status.

### 7. Add the missing chief-of-staff skills — **M**, after #2

The catalog's gap pattern is consistent: deep PM craft, thin personal-leverage verbs. Highest-value additions, in order:

1. **`workflow-weekly-review`** — the chief-of-staff's letter: what got done (and by whom), ladder motion, what stalled, what's waiting, this week's three decisions. Lands as a *receipt in Activity* — a report card you skim, not a readout at the top of the board (UX_VISION explicitly bans counting-noise there). This is the surface that makes "the pile shrinks week over week" *felt*.
2. **`workflow-1on1-prep`** — gather a person's recent meeting mentions, open waiting-on items, and shared tasks into a one-page brief. All the data sources exist (qmd search, meetings frontmatter, task fields).
3. **`task-snooze` / defer** — "snooze until ‹date›" as a real verb (frontmatter field + board filter). The hygiene audit (#2) needs it as a disposition anyway.

Honor ROADMAP §5 discipline while adding these: prune first. The audit found ~1,500 lines of duplicated North Star/framework tables across the five `metric-*` skills that could collapse into one shared reference, and 8 framework-heavy skills that would benefit from an explicit step checklist plus a standardized "When NOT to use" section (only 2 of 63 have one).

### 8. Validate task state transitions — **S**

`task_lib.update_task()` accepts any frontmatter combination; impossible states (`status: done` + `agent_status: running`) can accumulate and quietly poison the graduation metrics that read these fields (`graduation_assess.py` treats `status: done` as human acceptance — the passive signal makes state integrity load-bearing now). A small allowed-transitions table inside `update_task`, rejecting or logging invalid combos, protects the calibration data cheaply.

---

## Part 2 — Architectural notes (watch, don't rewrite)

- **`task_server.py` (2,567 lines) and `tasks.js` (1,149 lines, 25+ hand-wired verbs)** are past "basic Python / simple files" in feel. Congruent response: not a framework, just extraction — a route table for the server, a small action-dispatcher keyed off the card registry's action ids for the modal. Do it opportunistically when next touching those files.
- **Card-registry composition is split across files with no enforcer.** Adding a signal touches `card-registry.js`, `board.js`/`tasks.js`, and `signal-ids.txt` with nothing checking agreement. Cheap fix: extend `card_schema.py` to assert every registry-referenced signal/action id has a registered JS handler name (a generated manifest is fine).
- **Archive and logs grow unbounded** (`_archive/YYYY-MM/`, `logs/dispatch*.log`, per-task judge logs). Not urgent; congruent fix is a yearly tarball + log rotation inside the same hygiene sweep as recommendation #1, never a database.
- **In-memory chat run-lock** (`task_server.py` `_CHAT_RUNS`) loses state on restart; mirror the dispatch lockfile pattern if double-runs are ever observed in practice. Low priority.
- **Doctor detects but doesn't propose.** It already runs weekly via the seeded cron; make its findings land as recommendation cards ("Granola token expired — fix it? (workflow-doctor)") instead of an artifact someone must read. Same failure-as-proposal idea as #1.

## Part 3 — What *not* to do (congruence guardrails)

These came up as "obvious" fixes during the audit and should be declined:

- **No job queue / Celery / RQ / DB** for retries or outbox. Plain files + a sweep cron is the Magnolia-shaped answer.
- **No notification channels** (email/Slack/push). The board and its recommendation feed are the notification surface; failures and nudges become cards. UX_VISION already commits to this.
- **No SPA rewrite, no framework** for the modal/registry cleanups — extraction only.
- **No standing dashboard of counts** at the top of Now. The weekly review is a receipt you skim, not a readout that competes with Suggestions.
- **No auto-applying improvement proposals**, ever — including voice.md changes. Accept/reject only, per the governance line the README draws.

---

## Appendix — layer-by-layer findings (condensed)

**Engine (`scripts/`, ~15.8K LOC, 393 tests).** Strong: atomic task writes with YAML validation, profile seam (`profile_lib.py`) with enforced denylist, platform seam for Windows, worker matching with LLM→regex fallback, graceful LangFuse degradation. Weak: fire-and-forget judge spawn (`task_cli.py:255-274`); lock-contention drops single-task dispatch with no sweep (`task_dispatch.py:979-982`); no retry on transient claude/adapter failures; silent LLM-matcher fallback (`task_dispatch.py:359-418`); no state-machine validation in `update_task`; unbounded logs/archive; free-form `agent_error` with no failure taxonomy.

**Board UI (`ui/task-board/`, ~4.3K LOC JS + 2.6K server).** Strong: vanilla stack, token-only theming across 6 Moods, declarative card registry, Now-surface attention routing, SSE task chat. Weak: failures surfaced only inside the modal; Activity is a 1,000-row wall; Quality pivots by worker not task-type; modal verbs hand-wired; registry composition unenforced; no snooze; quick-add dispatches with neither confirm nor receipt; proximity-hover effect recomputes against all cards per frame (perf + busyness on large boards).

**Skills (`.claude/`, 63 skills, 37 commands).** Strong: 63/63 format-compliant, trigger-first descriptions, minimal true overlap, lightweight session-start bootstrap (~3.3K tokens, well-designed). Weak: person-name/quote leaks in ~8–15 skill example sections (not covered by the denylist, which only blocks "jay"); `workflow-jira-home` embeds component/board literals; 61/63 lack "When NOT to use"; ~1,500 LOC of duplicated metric framework tables; 2 packs are empty stubs; 2 skills pack-less; catalog thin on chief-of-staff verbs (weekly review, 1:1 prep, delegation/nudges, snooze).

**Data/profile/automation.** Per-person layers are gitignored, so live usage was unverifiable from this clone; structurally, the memory loops are designed but not yet closed: reactions are captured but produce no proposals (ROADMAP §1's missing half), voice files have no update path from real edits, archives are never synthesized, and the three seeded crons (doctor, self-improvement, graduation) are the only recurring jobs of the ~11 the roadmap names. The passive-approval signal (2026-06-09) makes `status: done` integrity load-bearing for graduation — see recommendation #8.

**Suggested sequencing:** #1 + #4 + #8 (one "honesty" release) → #2 (the felt chief-of-staff release) → #5 (before beta invites) → #3 (the learning release) → #6 + #7 alongside.

---

# Part 4 — The capability leap (v2, added same day)

Parts 1–3 harden the current frame. This part names the next frame. The diagnosis: **Magnolia's unit of work is the task, and a task is by definition something already known to need doing.** Every byte of agent work today is downstream of a human trigger or a clock tick. The judge, the ladder, the receipts all measure execution of *assigned* work. A chief of staff's defining property is being **upstream** of you — they hold your world, notice what's missing, and the work exists before you asked. In one line: **stop waiting to be asked.**

Four frontiers, each grounded in primitives that already exist.

## Frontier 1 — The Binder: a compounding world model

A small set of living, git-versioned markdown files the system itself maintains and **every worker reads before acting**: person dossiers (`datasets/people/` exists, empty — this is its purpose), account dossiers, an active-threads file, a priorities file, a decision journal. Updated as a side-effect of every transcript ingestion and task completion — as append *proposals*, judge-scored, riding the existing trust machinery.

Why this is the multiplier: `build_prompt` / `build_prompt_for_worker` (`task_dispatch.py:519-651`) injects worker + task + skills catalog and nothing else — **every dispatch starts amnesiac**, so output quality is capped at "smart contractor with no context." With a `## World` block injected from the binder, every output starts already knowing the renewal date, the thread history, the person's style. System value compounds with corpus size instead of staying linear in tasks executed. It is also the durable moat over any SaaS copilot: the binder is local, yours, portable. And it *is* simple files + git — the human chief of staff's literal binder, made of markdown.

**First build:** person + account dossiers auto-maintained from meeting frontmatter (`participants` / `customer` are already structured fields) + the `## World` injection block in dispatch and chat prompts.

## Frontier 2 — The calendar becomes the spine: anticipation, not reaction

Event-shaped triggers, not just cron's clock. The defining deliverable: **a pre-meeting brief before every meeting, unprompted** — who you're meeting, what was said last time, open loops in both directions, what to push for; sitting on the meeting's card 30 minutes before it starts. Post-meeting: the follow-through drafts are ready before you're back at your desk. Pattern triggers beyond the calendar: "QBR Friday → `workflow-cs-prep` runs Wednesday," "no contact with a top account in 6 weeks," "renewal in 30 days."

The reframe that makes this the natural next step: **the trust ladder is over-built for reactive work and exactly right for unprompted work.** Unprompted output is only tolerable because shadow scoring, receipts, and undo exist — the safety system was built for a capability that hasn't been switched on. Calendar is already a named future adapter family (`architecture.md` §4) and the M365 seam already exists (`find_meeting_times.py`).

**First build:** calendar adapter + one trigger — T-30min brief per meeting, generated from binder + qmd, landing as a card. Then the trigger table (`datasets/triggers/`?) as a sibling of cron: *condition → worker*, same dispatch pipeline.

## Frontier 3 — The Mirror: the chief of staff manages you, not just your work

The system holds your **stated** priorities (rocks, roadmap) and your **revealed** behavior (calendar hours, decision latency, reschedule patterns, commitments *you* owe others going stale) and reconciles them — gently, as proposals: *"You said Home WAU is the rock; it got 40 minutes last week — decline these two recurring meetings?"* A decision journal closes the longest loop in knowledge work: *"30 days ago you decided X expecting Y — here's what actually happened."* Boundary-keeping: flag the 80%-meeting week before it happens, protect focus blocks.

This is the only frontier aimed squarely at the stated emotional goal — be your best self at work. No commercial tool does priorities-vs-attention reconciliation; the data (meeting frontmatter + a priorities file) already exists locally. Tone is everything: weekly, accept/reject, never a nag — the system as the boundary-keeper *you* don't have to be.

**First build:** a weekly priorities-vs-calendar reconciliation card.

## Frontier 4 — Magnolia-to-Magnolia: the team protocol

`waiting_on` stops being a string and becomes a handshake. My "waiting on ‹teammate›" files a card on the teammate's board; their completion flows back and closes my loop. A shared team commitments ledger (one markdown file in a shared `team/` repo) is read and written by every instance. The chiefs of staff coordinate so the humans never have to chase each other — nobody has to be the nag.

This is the leap **only this architecture can make**: the engine was made identity-free from day one (invariant #1), so instances are protocol-compatible by construction, and git — already the transport for everything — is the bus. No server, no SaaS. First cross-board write is Tier-2, naturally.

**First build:** when teammate #2 onboards — a shared repo with the commitments ledger; nudges become machine-to-machine cards.

## Sequencing and the relationship to Parts 1–3

Binder first (it multiplies every existing and future output), calendar spine second (the felt leap), mirror third, protocol when the second teammate onboards. Part 1 is not displaced — the reliability work is the *license* for anticipation: unprompted work that silently fails is worse than no anticipation at all.
