# Magnolia Prioritized Roadmap v2 — from task executor to chief of staff

**Date:** 2026-06-10
**Status:** Proposed (companion to the 2026-06-09 audit; supersedes nothing — `ROADMAP.md` remains the living doc until the operator merges this into it)
**Premise:** an AI team builds this, so build effort is cheap and parallelizable. The roadmap is therefore sequenced by **when value can safely turn on**, not by engineering cost.

---

## Prioritization rationale

With an AI team, the classic scarce resource — engineering hours — is nearly free. Three different resources become the binding constraints, and they drive every ordering decision below:

1. **Trust is the currency, and it only spends down.** Every silent failure, generic draft, or wrong unprompted action costs trust that takes weeks of receipts to rebuild. So *honesty work precedes capability work* (R0 before everything), and every unprompted capability lands reversible and judge-scored from day one.
2. **Some value compounds on wall-clock time, not build time.** The Binder gets richer with every transcript ingested; judge↔human calibration accrues with every reviewed card. A feature whose payoff depends on accumulated data must *start collecting* as early as possible, even if its consumer features come later. This is why the Binder (R1) activates before the headline anticipation features (R2) that read it, and why Graduation (R5) is late — it's gated on calibration volume, not on code.
3. **The operator's attention is the real budget.** Each phase must *reduce* net attention demanded, never add a new pile. Every phase ships with a "Monday morning test" — a sentence describing how the operator's actual day changed. If a phase can't state one, it isn't a phase.

**Scoring.** Using the house formula (`context-priority-scoring`): `0.2×Signal + 0.4×StrategicFit + 0.3×Impact − 0.1×Complexity`, 1–10 scales. Complexity keeps its small negative weight — with an AI team it proxies *integration risk*, not cost.

| Phase | Signal | Fit | Impact | Complexity | Score | Notes on inputs |
|---|---|---|---|---|---|---|
| R2 The Counterpart | 9 | 10 | 10 | 6 | **8.2** | Existing ROADMAP already marks the queue audit "highest QoL"; anticipation is the felt product |
| R1 The Binder | 7 | 10 | 9 | 5 | **7.6** | Impact is indirect but multiplies every other output |
| R0 Honest Engine | 8 | 10 | 7 | 3 | **7.4** | Audit found 4 concrete silent-failure seams |
| R3 The Learning Loop | 7 | 10 | 8 | 6 | **7.2** | The system's stated differentiator; payoff gated on reaction volume |
| R4 The Mirror | 6 | 9 | 9 | 5 | **7.0** | Aimed at the emotional goal directly; novel, lower external signal |
| R5 Graduation | 6 | 10 | 8 | 7 | **6.9** | The thesis payoff; gated on calibration data, not build |
| R6 The Team | 5 | 9 | 10 | 8 | **6.8** | Highest ceiling; gated on teammate #2 existing |

**Why activation order ≠ score order.** R2 scores highest but cannot hit its impact ceiling first: briefs and drafts generated without the Binder are generic (the exact failure of every AI tool the README criticizes), and unprompted work atop a silently-failing engine is worse than no anticipation. So: R0 makes it safe → R1 makes it *specific* → R2 makes it *felt*. R0 and R1 build in parallel from day one; phases mark when each capability switches on, not when an AI team starts typing.

---

## R0 — Honest Engine *(the license)*

> **Monday morning test:** when something breaks, you find out from a card with a next step — never from a blank field or a hunch.

| # | Feature | Spec | Done when |
|---|---|---|---|
| F0.1 | Dispatch sweep | Periodic tick (ride the existing `cron_scheduler.py` daemon) re-runs `task_dispatch.py` for anything `open`/`queued` older than ~10 min — closes the lock-contention drop at `task_dispatch.py:979-982` | A task created during lock contention runs with zero human action |
| F0.2 | Judge sentinel | `agent:complete` stamps `judge_status: pending`; sweep retries once; terminal failure renders honestly as *unscored* and is excluded from `graduation_assess.py` metrics | Killing the judge mid-run yields a visible unscored card + one retry |
| F0.3 | Failure-as-card | `agent:fail` emits a `recommendation` card: "TASK-X failed: ‹first error line› — retry / reassign / kill?" | A failed dispatch lands in Suggestions with three one-tap dispositions |
| F0.4 | Adapter outbox | `publish()` records intent in task frontmatter before the external call; sweep retries; 3 failures → escalation card. Files only — no queue infra | Jira down → pending state visible → auto-recovers or escalates |
| F0.5 | State-machine validation | Allowed `status`×`agent_status` transition table inside `task_lib.update_task` — protects the `status: done` integrity the passive-approval signal now depends on | Impossible combos can't be written via CLI or server |
| F0.6 | Board honesty batch | Inline `agent_error` first line on card faces; Activity pagination + weekly summary line; Quick Add emits receipt-with-undo (not silent dispatch); cleared-lane celebration copy | — |
| F0.7 | Beta gate *(time-driven, not score-driven)* | Scrub person names/verbatim quotes from skill examples; `workflow-jira-home` literals → `profile/integrations.yaml`; extend the `DENY` list in `test_engine_no_jay.py` with teammate-name patterns; pack the two orphan skills | Denylist gate catches a planted teammate name |

## R1 — The Binder *(the multiplier — start day one, in parallel with R0)*

> **Monday morning test:** agent output stops being generic — a draft mentions the renewal date you never told it about.

| # | Feature | Spec | Done when |
|---|---|---|---|
| F1.1 | Binder schema | `datasets/people/<slug>.md`, `datasets/accounts/<slug>.md`, `datasets/binder/{threads,priorities,decisions}.md` — YAML frontmatter + dated observation sections, documented in `docs/reference/` | Schema doc + validator exist |
| F1.2 | Dossier maintainer | Post-ingest hook on the transcript seam dispatches a `binder-keeper` worker: appends dated observations (commitments both directions, preferences, facts, sentiment) with source links. Writes land as receipts — reversible, judge-scored, never a confirm | Ingesting a transcript updates the right dossiers with cited entries |
| F1.3 | World injection | `build_prompt` / `build_prompt_for_worker` / `chat_runner` select relevant binder slices (match task `participants`/`customer`/`domain` frontmatter; qmd fallback) into a capped `## World` block (~1–2K tokens) | A/B on the same task shows judge-scored specificity gain |
| F1.4 | Binder hygiene cron | Monthly compaction: dedupe, expire stale facts, roll observations into summaries (versioned, append-only per invariant #6) | — |
| F1.5 | Priorities capture | `priorities.md` written at onboarding + a lightweight update flow; feeds F1.3 now and R4 later | — |

## R2 — The Counterpart *(the headline release: anticipation + the pile dissolves)*

> **Monday morning test:** a brief is waiting before every meeting; your stale pile triages itself; nudges arrive pre-drafted. The system did things before you asked.

| # | Feature | Spec | Done when |
|---|---|---|---|
| F2.1 | Calendar adapter family | `adapters/calendar/_contract.py` + M365 provider (the seam `architecture.md` §4 already names); read-only Tier-0: `list_events(window)` | Board can see today's meetings |
| F2.2 | Pre-meeting briefs | T-30min trigger per event: attendee dossiers + last-meeting summary + open loops (tasks matching `waiting_on`/participants) + suggested pushes, landing on a meeting card. 1:1s are the same feature with a persona lens — subsumes the separate 1:1-prep skill | Every meeting has an unprompted brief before it starts. **Activates after F1.3** |
| F2.3 | Human-queue audit cron | Weekly worker over human+waiting queues → recommendation cards: stale (kill/convert/**snooze** — ships the `snoozed_until` verb), message-shaped (draft offer). ROADMAP cron #2, now pure wiring | A stale task produces a one-tap triage card |
| F2.4 | Waiting-on nudges | `waiting_expected` overdue → nudge card with `message-writer` draft attached → existing Tier-2 send path | "Waiting on ‹person›, 5 days past — send? (draft ready)" |
| F2.5 | Post-meeting follow-through | Extend meetings-to-backlog: extracted "I'll send that over" commitments arrive with drafts already attached where message-shaped | Follow-ups are review+send, not write-from-scratch |
| F2.6 | Trigger table | `datasets/triggers/` — *condition → worker*, evaluated on the daemon tick; first conditions: meeting-in-N-hours, no-contact-in-N-weeks, renewal-in-N-days, waiting-overdue. The event-shaped sibling of cron; F2.2/F2.4 become its first two rows | A new trigger is a file drop, like skills |
| F2.7 | Weekly chief-of-staff letter | A receipt in Activity: what got done and by whom, scores, ladder motion, pile delta. The trust narrative R5 will draw on; explicitly *not* a count-readout atop Now (UX_VISION rule) | — |

## R3 — The Learning Loop *(capture becomes learning; payoff gated on reaction volume R2 generates)*

> **Monday morning test:** a thumbs-down on Tuesday becomes a proposed diff by Monday.

| # | Feature | Spec |
|---|---|---|
| F3.1 | Improvement agent | `eval-analyst` converts `eval_digest.py` clusters → collab card with a diff at the right altitude (skill / voice.md / worker scope / rubric / golden example). The missing half of ROADMAP §1; the diff renderer + accept path already exist |
| F3.2 | Voice loop | Capture draft-vs-sent edit diffs at send time; cluster into proposed `voice.md` changes — the highest-signal style data the system will ever get, free |
| F3.3 | Task-type first-class | One declared taxonomy across judge / ladder / quality; Quality tab pivots from per-worker to per-task-type (the unit that actually graduates) |
| F3.4 | Golden-set confirm flow | Judge proposes exemplars; a confirm card adds them — the judge never writes its own ground truth |

## R4 — The Mirror *(the chief of staff manages you; parallel-buildable, activates after calendar adapter)*

> **Monday morning test:** a weekly letter shows where your time actually went vs. what you said mattered — with one-tap fixes.

| # | Feature | Spec |
|---|---|---|
| F4.1 | Attention reconciliation | Weekly card: calendar hours by category vs `priorities.md`; proposals attached (decline / shorten / delegate / convert) |
| F4.2 | Decision journal | Extract decisions + expected outcomes from transcripts into `decisions.md`; a T+30d trigger (an F2.6 row) compares expectation vs evidence and reports |
| F4.3 | Boundary keeper | Week-ahead scan: overload and zero-focus-time flags, proposed as moves — the system is the boundary-keeper so the human doesn't have to be |

## R5 — Graduation *(the thesis payoff; activates on calibration thresholds, not build completion)*

Matches existing ROADMAP §2 Phase B + §3 — included here because R0–R2 are what make it reachable: honest scoring data (F0.2), reaction volume (R2 usage), and the trust narrative (F2.7).

- **F5.1** Supervised gating: inline `generate → critique → revise` (1–2 bounded passes) for graduated types; traces keep draft-v1/critique/draft-v2.
- **F5.2** Promotion flip always lands as one collab card you approve. **F5.3** Auto-demotion on score drop.

> **Monday morning test:** the first task-type runs without you and lands receipts you skim.

## R6 — The Team *(gated on teammate #2 onboarding, which F0.7 unblocks)*

The leap only this architecture can make: identity-free engine (invariant #1) ⇒ protocol-compatible instances; git ⇒ the bus. No server.

- **F6.1** Shared `team/` repo + commitments ledger every instance reads/writes.
- **F6.2** Waiting handshake: my `waiting_on` card files a linked task card on the teammate's board; their completion closes my loop. First cross-board write is Tier-2.
- **F6.3** Machine-to-machine nudges — nobody on the team has to be the nag.
- **F6.4** Team binder slice (shared accounts/threads, per-person dossiers stay local).

> **Monday morning test:** you stop chasing teammates; your systems chase each other.

---

## Dependency spine (activation order)

```
R0 Honest Engine ──────────┐ (license: unprompted work must fail loudly)
R1 Binder (parallel) ──────┼──► R2 Counterpart ──► R3 Learning Loop ──► R5 Graduation
        │                  │         │
        └─► F1.5 priorities┘         └─► R4 Mirror (needs F2.1 calendar only)
F0.7 Beta gate ────────────────────────────────────────► R6 Team
```

**Guidance for the AI team:** build R0+R1 in parallel immediately; R2 features can be built behind them but **activate** in order (F2.2 only after F1.3, so the first brief the operator ever sees is specific, not generic — first impressions are trust). R3/R4 are parallel-buildable; their *activation* waits for reaction volume and the calendar adapter respectively. R5 flips on thresholds in `ladder.json`, never on a build date. R6 starts the day a second profile exists.
