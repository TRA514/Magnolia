# Magnolia Prioritized Roadmap v3 — consolidated after review

**Date:** 2026-06-10
**Status:** Supersedes `2026-06-10-prioritized-roadmap.md` (v2, retained per invariant #6). Incorporates the review rounds on R0 (honesty vs robustness), R3 (two learning loops), and R1 (derived state vs retrieval).
**Premise:** an AI team builds this; sequencing is by *when value can safely turn on*, not engineering cost.

---

## Sequencing principles (revised)

1. **Trust only spends down.** Honesty work precedes capability work; every unprompted capability lands reversible and judge-scored.
2. **Honesty ≠ robustness.** While every action is human-watched (Tier-2 gate + advisory ladder), the human *is* the error handler — the system's only duty is to never lie about what happened. Robustness machinery (retries, outboxes, validators) is earned at the autonomous rung. It rides the trust ladder like everything else.
3. **Store signals being destroyed today; defer actuators until the signal demands them.** Draft-vs-sent diffs are destroyed at send (`handle_update_message` overwrites the original); transcripts are kept forever. So diff capture is urgent; the binder is not.
4. **Derived state only where retrieval structurally fails** — reconciled current values, corpus-wide open/closed joins, out-of-corpus facts. Built regenerable from the corpus, validated blind against a retrieval-only baseline, deleted if it doesn't win. Membership rule: if a fact is verbatim in one transcript, it stays out.
5. **Two learning loops, never crossed.** The prompt loop improves *outputs* (generators); the judge loop improves the *gate* (rubric). The judge never edits generators; the prompt loop never edits the rubric. Both anchor to the same human ground truth: the diff store.
6. **Build and activation are decoupled.** Every phase carries a Monday-morning test — the observable change in the operator's day.

---

## N0 — This week (rides the judge PR; tiny, two items time-critical)

> **Monday test:** nothing visible yet — this is the ground truth starting to accumulate instead of being destroyed.

| # | Feature | Spec | Why now |
|---|---|---|---|
| N0.1 | Draft snapshot + diff store | Snapshot `message_draft_original` at `agent:complete`; at send compute diff + `sent_modified` flag; store the pair (~15 lines) | The agent's original is overwritten today on edit — every send loses irreplaceable ground truth for **both** learning loops |
| N0.2 | Honest passive approval | `sent_modified` excludes quiet rewrites from "clean accept" in `graduation_assess.py` | The promotion bar is "accepted *unmodified*" — currently unmeasurable; a silent rewrite counts as the strongest approval signal |
| N0.3 | Judge honest failure | `except` block in `judge.py` writes `judge_error`; card renders *unscored* (~10 lines) | Visibility, not retry machinery (principle 2) |
| N0.4 | Retrieval step in workers | One line per worker prompt: run qmd/context search before drafting | The actual fix for dispatch amnesia — the baseline the binder must beat |
| N0.5 | `corrections.md` | Hand-append file for out-of-corpus facts ("budget is $60k, said at the conference"; "don't pitch X until the lawsuit settles"), injected into worker context | Costs nothing; captures knowledge that exists in zero documents and can never be retrieved |

## R0 — Honest Engine *(slimmed ~4× from v2)*

> **Monday test:** when something breaks, you find out from the board with a next step — never from a blank field or a hunch.

| # | Feature | Spec |
|---|---|---|
| F0.1 | Dispatch sweep | ~25 lines on the existing daemon tick: re-dispatch anything `open`/`queued` older than ~10 min. The two seeded Monday-9:00 crons race the lock *weekly by default*; the loser strands silently |
| F0.2 | Board honesty batch | Inline `agent_error` first line + retry button (existing `/rerun`); Activity pagination + weekly summary line; Quick Add emits receipt-with-undo; cleared-lane celebration copy |
| F0.3 | Done-integrity test | Gate-style test asserting no agent code path writes `status: done` — pins the invariant the passive signal depends on, in the repo's native enforcement idiom |
| F0.4 | Beta gate *(time-driven)* | Scrub person names/quotes from skill examples; `workflow-jira-home` literals → `profile/integrations.yaml`; extend `DENY` list with teammate patterns; pack the two orphan skills |

**Cut from v2 (and why):** adapter outbox → moved to R5 preconditions (verified: interactive sends already fail loudly to the human and are idempotent — the human is the retry); judge retry sentinel → N0.3's honest write only; runtime state machine → F0.3 test (tasks are hand-editable markdown on purpose; a runtime guard fights the philosophy and can't protect against hand edits anyway).

## R1 — Derived-State Pilot *(the Binder, slimmed to what retrieval can't do)*

> **Monday test:** drafts stop being confidently wrong about your world — the renewal date is the current one, and nobody gets nudged about a promise they already kept.

| # | Feature | Spec |
|---|---|---|
| F1.1 | Commitments ledger | `datasets/binder/commitments.md` — open/closed promises both directions, every entry source-linked, closed entries cite the closing transcript. This is a corpus-wide join retrieval cannot express |
| F1.2 | Account current-facts | `datasets/accounts/<slug>.md` — reconciled values (renewal date, sponsor, seats) with supersession chains + sources. Fixes "semantic similarity ≠ recency" |
| F1.3 | World injection | Capped `## World` block in `build_prompt` / `chat_runner`: `corrections.md` + relevant ledger/facts slices, alongside N0.4's retrieval instructions. State answers "where things stand"; retrieval answers "what was said" — briefs read both |
| F1.4 | Weekly regeneration | One job rebuilds F1.1/F1.2 from scratch from the corpus — a materialized-view refresh. Idempotent, self-healing, no drift accumulation. `corrections.md` is overriding input that survives rebuilds |
| F1.5 | Kill criterion | Blind A/B on judge-scored briefs: retrieval-only vs retrieval+state. No measurable gain → delete the two generated files; keep `corrections.md` (irreplaceable either way) |

**Cut from v2:** person dossiers, threads, sentiment trajectories (apply later only if the pilot wins); the per-transcript binder-keeper worker and monthly hygiene cron (regeneration replaces both with less machinery).

## R2 — The Counterpart *(the headline: anticipation + the pile dissolves)*

> **Monday test:** a brief is waiting before every meeting; the stale pile triages itself; nudges arrive pre-drafted — and never about a promise already kept.

| # | Feature | Spec |
|---|---|---|
| F2.1 | Calendar adapter | `adapters/calendar/_contract.py` + M365 provider; read-only Tier-0 `list_events(window)` |
| F2.2 | Pre-meeting briefs | T-30min per event: current-facts + open commitments + last-meeting retrieval + suggested pushes, on a meeting card. 1:1s = same feature, persona lens. **Activates after F1.3** — the first brief you ever see must be specific |
| F2.3 | Human-queue audit cron | Weekly recommendation cards over human+waiting: stale (kill / convert / **snooze** — ships `snoozed_until`), message-shaped (draft offer). Existing ROADMAP cron #2, now pure wiring |
| F2.4 | Waiting-on nudges | Overdue `waiting_expected` → nudge card with `message-writer` draft → existing Tier-2 send. Reads the commitments ledger so closed loops never get nagged |
| F2.5 | Post-meeting follow-through | Extracted "I'll send that over" commitments arrive with drafts attached where message-shaped |
| F2.6 | Trigger table | `datasets/triggers/` — *condition → worker* on the daemon tick (meeting-in-N-hours, no-contact-in-N-weeks, renewal-in-N-days, waiting-overdue). The event-shaped sibling of cron; F2.2/F2.4 are its first rows |
| F2.7 | Weekly chief-of-staff letter | Receipt in Activity: what got done, scores, ladder motion, pile delta. Not a count-readout atop Now |

## R3 — Two Learning Loops *(restructured; consumes the N0.1 store)*

> **Monday test:** a correction you keep making stops being needed — and the gate's bar visibly tracks yours.

**Prompt loop — improves outputs.** The prompt-eval cron consumes draft→final pairs by task-type and proposes generator changes (voice.md line, skill edit, worker scope) as collab cards with diffs, plus candidate golden examples (human-confirmed). The diff is its primary input — the answer key, not commentary. *Activation trigger: a recurring correction pattern in the store (same class of edit ~3 weeks running), not a build date.*

**Judge loop — improves the gate.** Dimension-tagged diff drift ("judge scored tone 9; human rewrote tone") → rubric version proposals, accept/reject only. Plus the golden-set confirm flow (the judge never writes its own ground truth). Conservative cadence — rubric changes are governance.

**Shared substrate:** task-type as a first-class declared field; Quality tab pivots from per-worker to per-task-type (the unit that actually graduates).

**Cut from v2:** sophisticated failure clustering — `eval_digest.py`'s crude clustering + a capable model reading it suffices at this volume.

## R4 — The Mirror *(activates after F2.1)*

> **Monday test:** a weekly letter shows where your time went vs. what you said mattered — with one-tap fixes.

| # | Feature | Spec |
|---|---|---|
| F4.1 | Attention reconciliation | Weekly card: calendar hours by category vs `priorities.md` (captured at onboarding); proposals attached (decline / shorten / delegate / convert) |
| F4.2 | Decision journal | Decisions + expected outcomes extracted to `decisions.md`; a T+30d trigger compares expectation vs evidence |
| F4.3 | Boundary keeper | Week-ahead scan: overload and zero-focus-time flags, proposed as moves |

## R5 — Graduation + Earned Robustness *(activates on `ladder.json` thresholds, never a build date)*

> **Monday test:** the first task-type runs without you and lands receipts you skim.

- **F5.1** Supervised gating: inline `generate → critique → revise` (1–2 bounded passes); traces keep draft-v1 / critique / draft-v2.
- **F5.2** Promotion flip always lands as one collab card you approve. **F5.3** Auto-demotion on score drop.
- **Preconditions — the robustness cut from R0, now due because the watcher leaves the room:**
  - **F5.4** Adapter outbox + retry for autonomous external writes (file-based, sweep-driven).
  - **F5.5** Hard per-task wall-clock timeouts on dispatch.
  - **F5.6** Sampled human review rate for autonomous types, set deliberately in `ladder.json` — the diff stream dries up at autonomy by construction, so sampling is the only remaining ground-truth regenerator.

## R6 — The Team *(gated on teammate #2, which F0.4 unblocks)*

> **Monday test:** you stop chasing teammates; your systems chase each other.

- **F6.1** Shared `team/` repo; the commitments ledger (F1.1) becomes the shared object — the pilot artifact graduates into the protocol.
- **F6.2** Waiting handshake: my `waiting_on` card files a linked task on the teammate's board; their completion closes my loop. First cross-board write is Tier-2.
- **F6.3** Machine-to-machine nudges — nobody has to be the nag.
- **F6.4** Team binder slice (shared accounts/threads; per-person files stay local).

---

## Dependency spine

```
N0 this week (judge PR + trivia) ─► R0 ∥ R1 (parallel) ─► R2 Counterpart ─► R3 Loops ─► R5 Graduation
                                            │                  │
                                            │                  └─► R4 Mirror (needs F2.1 only)
F0.4 Beta gate ─────────────────────────────┴──────────────────────────────► R6 Team
```

**For the AI team:** N0 lands now (two items lose data daily). R0 and R1 build in parallel. R2 builds behind them but activates in order — F2.2 after F1.3. R3's prompt loop activates on observed correction patterns; the judge loop rides the judge workstream. R5 flips on thresholds; its F5.4–F5.6 preconditions must be green before any type's first autonomous external write. R6 starts the day a second profile exists.
