# PM-OS UX Vision

> The design philosophy. Companion to [`ROADMAP.md`](./ROADMAP.md) (where the **system** goes) and [`README.md`](./README.md) (how it works for a new user): this document says how the **experience** should *feel*, and why. It is deliberately timeless — it argues for the principles and the emotional state we're building toward, and changes far less often than the roadmap underneath it.

**Last updated:** 2026-06-08

---

## Thesis: the system is a chief of staff

Everything below serves one relationship. PM-OS is not a task board you operate; it is a **chief of staff** that does the legwork, triages the inbox, drafts the messages, watches quality, and walks into your office with only two kinds of things:

- **"Here's what I need you to decide or own."**
- **"Here's what I already handled, FYI."**

A good chief of staff is measured by how little of your attention they waste and how much you trust what crosses your desk. That is the whole design goal — and every UX decision below is downstream of it.

---

## The emotional state we're designing for

Software for busy people usually trades in a single feeling: **low-grade dread.** The unread badge, the growing column, the nagging sense that something important is buried in the pile. Most "productivity" tools make this *worse* — they're one more inbox to fall behind in. Even AI tools tend to add to the pile: they generate more output and hand all of it back to you, equally, for you to sort.

Magnolia is designed for the opposite feeling: **the relief of a desk that someone you trust has already tidied.**

The target emotional arc, every time you sit down:

- **Not anxiety, but orientation.** You open the board and immediately know the shape of your day — what truly needs you, and what's already handled. No scanning four columns to reconstruct the state of the world.
- **Not obligation, but trust.** When the system says "I handled this," your honest reaction is *good, I believe you* — because it has earned that, visibly, over time. Trust is the feeling we are actually manufacturing.
- **Not a fuller plate, but a lighter one.** The pile shrinks week over week. The things you used to do by hand get noticed, drafted, and quietly taken off your plate. The system's job is to make itself the reason you have *less* to hold.
- **Not noise, but calm.** A quiet board is the system working, not the system idle. Silence means the machine handled the handleable and is holding only what genuinely wants you.

If a design choice adds a feeling of dread, obligation, or noise — even a clever one — it is wrong, regardless of how much it can technically do. **Calm is the feature.**

---

## The core reframe: organize by demand on you, not by who executes

A division-of-labor model — Human / Supervised / Agent / Waiting — answers *who does the work.* It was the right lens while **building** the system. It is the wrong lens for **living in** it.

When you sit down, you never think "let me check the agent queue." You think: *what needs me, what did the machine already handle, and can I trust it.* The pile-up is the symptom; the cause is a board that makes everything compete for your attention equally, whether or not it actually wants anything from you.

**The reframe:** make *"what does this want from me?"* the primary axis. The four queues stay exactly as they are in the **data** (they model who executes, which is real). They stop being how you **look** at the work. The board derives your attention-state from (queue + status + tier + score + kind), instead of showing a fixed four-column map of the queues.

---

## Two kinds of work

There are only two, and they are different animals:

1. **Machine work** — the agent already did it. By the time you look, it is past tense. Your relationship to it is *after the fact*.
2. **People work** (human + waiting) — depends on a person doing something in the real world, and that something is almost always **a message**: send a follow-up, ask for help, make a request, chase a reply. This is the work that actually *lives in time and piles up.*

There is no meaningful "in flight" lane. Agents run near-real-time; "running" is a transient micro-state on a card, not a place you visit. The only genuinely live, temporal work is People work.

---

## Inside machine work: accountability is the gate

Not all agent work is a receipt. It splits by **what you are on the hook for**:

- **Artifacts you are accountable for** — research, plans, PRDs, docs, memos, analysis. These are **Review, always.** Your name is on the PRD; it becomes real software downstream; you must read it before it counts. This is not an exception stream — it is the *core of your day* on the machine side.
- **Actions already taken** — published to Jira, sent a message, refreshed a metric, wrote a file. These are **Receipts.** Past tense, reversible, confirm-or-undo.

The dividing rule:

- **Accountability** decides whether something can *ever* be a receipt. Artifacts you sign → **permanent Review**. No quality score retires that read. **Trust can automate the *doing*; it cannot transfer the *accountability*.**
- **Blast radius + reversibility** decides receipt *eligibility* among actions.
- **The judge** routes *attention depth* (skim a 9, scrutinize a 5), never *whether* you look.

The promotion ladder applies **only to the action class**. A PRD-drafting task-type can become fully trusted to *produce well* and still land in Review forever, because you own the outcome. That is not a gap in automation — it is the line automation should not cross.

---

## Tasks vs. Receipts (the two card kinds)

A first-class distinction in the data, not just the display:

- **A Task** is *future tense*: "Do X." It demands you. It may legitimately pile up — each one wants something.
- **A Receipt** is *past tense*: "Did X. Here's what changed. Here's the score. Confirm / Undo." Its default state is *fine*. It wants a skim, then auto-archives unless flagged.

A receipt carries exactly three things: **what it did** (the diff / what changed), **whether it's done well** (judge score + one-line why), and **one reversible affordance** (Undo / Flag). As a task-type graduates report → scored report → autonomous action, its card *changes tense* — from Review (artifact you bless) or Decide (action you pre-approve) to a Receipt you confirm after. **The promotion ladder is literally visible as where a card-kind lands on your screen.**

---

## The judge is the attention router

The judge is not only a quality gauge; it is what keeps the machine pile from forming. Because it scores *everything* — agent artifacts, message drafts, approval recommendations — it decides **how much of your attention each item deserves**:

- **Action, high score, low risk** → auto-Receipt. You never had to touch it.
- **Anything low-scored** → pulled into your lane with "judge flagged this." *This* wants your eyes.
- **Artifact you're accountable for** → Review regardless of score; the score sets *depth*, not *whether*.
- **Tier 2 external action** → always surfaces for approval; blast radius trumps confidence.

So Review stays the heavyweight daily lane (artifacts you must bless, depth-sorted by the judge), and Activity is the skim lane (actions that already happened). The eval work and the UX work are the same project: **the judge is the thing that makes the board calm.**

---

## People work is communication — so draft it or convert it

Human and Waiting are one category: *things involving other people that aren't done*, executed through Teams or email. This is the pile that actually hurts, and most of it is human **by habit, not necessity.** Two attacks:

1. **Convert.** Many "human" tasks — draft a follow-up, research X, summarize, write the request — were never human tasks. An agent owns them.
2. **Assist the ones that stay human.** If it's "send a message," the agent **drafts it** (Teams / email via the M365 MCP), the judge scores the draft, and your action collapses to *review + send*. Sending is a Tier-2 external action, so it routes through a confirm.

A People-work card should rarely be a naked "go do this." It arrives with a draft attached and a one-tap send, or it has already been promoted to an agent task. The planned weekly **human-queue audit** (see `ROADMAP.md`) is the engine that keeps this pile from forming.

---

## The briefing is a recommendation feed, not a readout

Counting what you can already see is noise. The top of the board is the chief-of-staff's morning standup: **a short stack of proposed actions, each one-tap.**

- *"TASK-0123 (human) has sat 7 days — kill it · convert to agent · snooze?"*
- *"3 human tasks look like message drafts — let agents draft them?"*
- *"Waiting on Priya, 5 days past expected — send a nudge? (draft ready)"*
- *"Judge scored TASK-0098's output 4/10 — review before it ships."*

Every recommendation has the same shape: it is a **proposal** — from hygiene, the judge, a conversion audit, calibration drift, or an improvement-loop diff. They all empty into one surface where **the system proposes and you dispose.** That is the chief of staff made literal.

---

## Information architecture

Sort surfaces by **what they want from you** and by **cadence** (daily / weekly / rare).

**Daily — where you live:**

1. **Now** (default)
   - **Suggestions** (top) — the action feed. Least time, most leverage.
   - **Decide** — collab items where an agent prepped something external and needs your go-ahead.
   - **Review** — machine artifacts you're accountable for, plus judge-flagged exceptions. Verbs: review / approve / annotate / delete. Judge score + one-line why on each, depth-sorted.
   - **People** — human + waiting, unified and communication-centric. Most items carry an agent-drafted message + send, or a convert-to-agent option. Verbs: send / ask / follow up / chase.
   - **Agent queue** — collapsed by default; a pulse when something is running. Not a place you work.

2. **Activity** — the receipts stream. Auto-archived actions, completed sends, what cron did. Reverse-chron, filterable by area / customer / source. Skim, don't work. **This is where completed cron output lands** — not siloed, not clogging a to-do lane.

**Weekly — the machine's report card:**

3. **Quality** — a **read-only** trust dashboard organized by task-type. Calibration itself happens per-card on the board, not here; this is where you *understand* drift and watch types climb toward graduation.

**Rarely — config rooms:**

4. **Engine** — workers, prompts, skills, profile. How it's wired.
5. **Schedules** — recurring job *definitions only*. Their runs live in Activity.

No "In Flight" lane. No four-column scan. The whole thing reduces to a sentence: **the judge triages the machine pile down to what you're accountable for, a weekly audit plus message-drafting dissolves the people pile, and whatever's left the system proposes as one-tap actions at the top of your day.**

---

## The Quality tab

Its own room, split from **Engine**: Engine is *how the machine is wired* (workers, prompts, skills), Quality is *how well it's doing and whether it's learning*. The organizing unit is the **task-type**.

**Calibration is a free byproduct of review, not a chore.** The judge scores everything; its verdict (score + per-dimension breakdown + one-line why) rides on the card. When you review an artifact you're accountable for, your normal reaction — good / needs-work, plus an optional note — *is* the calibration signal. Agreement is the delta between your read and the judge's. You never sit down to "calibrate"; it accrues from the review you already owe the artifact. This is why calibration is **per-card and real-time**, and why the Quality tab can stay read-only.

**Three surfaces, one job each — no competing action surfaces:**

| Surface | Role | What you do |
|---|---|---|
| **Card** (on the board) | calibration input, in context | react to the output (the free signal) |
| **Quality tab** | trust dashboard, read-only | understand where and why it's drifting |
| **Now / Suggestions** | control | accept / reject rubric and promotion changes |

**What the Quality tab shows** (all read-only):
- **Scoreboard / promotion board** — a row per task-type: score trend, judge↔you agreement %, rung (Shadow / Supervised / Autonomous), and trajectory toward graduate-or-demote. Answers "can I trust it more or less than last week" at a glance.
- **Drill into a type** — its score distribution; the **disagreement list** (the biggest judge-vs-you divergences, each linking back to the card where it happened). This is the *evidence behind the agreement %*, not a place you work.
- **The judge itself** — current rubric version + history, the draft → critique → revise traces when inline gating fires, and any **pending rubric change** shown as status ("PRD-draft: v4→v5 proposed → act on Now").

**Governance is accept/reject only.** You never hand-edit the judge prompt. When divergences cluster, the improvement loop drafts a rubric change (or a promotion / demotion) and it lands as a Suggestion on **Now**, with the diff. The judge improves through your accept/reject plus your passive per-card reactions — never through manual tuning.

---

## The trust ladder is not the card types

The most important distinction in the whole system, and the easiest to blur:

- **Card types** describe *what a piece of work is* — task vs receipt, the queue it routes to, whether it's an artifact you own or an action that was taken.
- **The trust ladder** describes *how much the judge inserts itself into producing that work* — and it changes the **judge's role**, not the work's identity.

The same card type sits at every rung as trust grows; what changes is the judge's posture:

- **Shadow** — the judge watches and scores, and **does not interject.** A new hire taking notes, touching nothing.
- **Supervised** — the judge **reviews before the work lands** and can **kick it back** for revision (inline generate → critique → revise). A manager who can say "not yet."
- **Autonomous** — the judge becomes the **chief of staff**: it does the work to the level it needs to be and **finishes it on its own**, landing a receipt you confirm or undo.

This is a separate axis from the **blast-radius tier** (how far a mistake could reach — the Tier-2 external-write gate). The ladder is about the judge's involvement; the tier is about safety. A card can be high on the trust ladder and still hit the Tier-2 gate before it touches the outside world. (See `README.md` for the full walk-through.)

---

## What we deliberately don't do

Restraint is a design principle, not an omission:

- **No rebuilding the board as a SPA framework.** The reframe is information architecture, not a rewrite of `index.html`. Evolve the existing vanilla UI.
- **No mobile / push notifications.** The briefing is the notification surface. We don't add another channel to be interrupted on.
- **No hand-tuning the judge.** Governance is accept/reject only. The moment you're editing the judge's prompt by hand, the loop has failed.
- **No piling output back on you.** If a surface counts what you can already see, or makes the calm things compete with the urgent ones, it's working against the thesis.
