# Magnolia — UI Design Commission Brief

**For:** Claude Designer
**From:** the Magnolia PM-OS team
**Deliverable wanted back:** drop-in **HTML / CSS / JS** for the surfaces below, built against the
existing **theme-token contract** (§2) so they inherit every mood. You build against a **mock API**
(shapes in §8); we reconcile the mock and integrate into the live backend on our side. This is
**not** expected to be copy-paste-clean — we expect mock-API seams and will run with the result.

**One hard rule, above everything:** every value you style must come from a **theme token**
(§2). **Never** hardcode a color, radius, or transition. This is what guarantees your surfaces look
correct across all five existing moods (Organic, Modafinil, Breathe, Zen Garden, Vantacan) and any
future one. A surface that hardcodes `#1a1a1a` or `border-radius: 8px` is a defect, not a style.

---

## 0. Read-me-first: what Magnolia is

Magnolia is a **chief of staff, not a task board you operate.** Its job is to **lower cognitive
load and anxiety** — surface what needs the user, in order, calmly, then get out of the way. AI is
frenetic; this is the calm place. **Every visual decision serves calm, focus, and trust.**

- **Calm > snappy.** Transitions are soft and brief; nothing flashes or demands attention. The
  existing "mood-meld" theme transition is the reference feel.
- **One thing at a time.** Whitespace and ordering do the triage. Avoid dense competing surfaces.
- **Plain language everywhere.** No jargon, no git, no model IDs surfaced unasked. Blast-radius and
  trust are explained in words a COO reads comfortably. The word "git" never appears in the UI —
  reverting a change is just **"Undo."**

**Stack constraints (must hold):** Vanilla **HTML + CSS + JS**. No SPA framework. You are
**evolving an existing board** (`ui/task-board/`), not rewriting it. CSS and JS stay cleanly
separated (the existing codebase does this well). The board is served by a small Python server;
all dynamic data comes from `/api/*` (mock these — §8).

---

## 1. What we need designed (scope)

Four things, all **drop-in** to the existing board:

1. **The card-registry renderer** — a generic card *shell* + *slot system* already drives the
   board. We need its **full visual treatment and every state** designed (§4).
2. **Three new card kinds** that ride that shell — **Recommendation**, **Receipt**, **Graduation**
   (§5). They are functionally wired in our backend but render as unstyled placeholders today.
3. **The Profile / Config room** — a new surface inside the existing **Engine** tab (§6). This is
   the only genuinely net-new screen.
4. **The Quality trust dashboard** — restyle an existing, real-data tab into a calm trust surface
   (§7).

**Explicitly NOT in scope:** the rest of the board (Now feed layout, Activity stream, Schedules,
the task-detail modal, the existing `task` card) is mature and stays. Onboarding has **no new
surface** (§9). Do not redesign what isn't listed above.

---

## 2. The design system you build against (the token contract)

The design system **is** the card schema (§3) + a set of **CSS custom properties** ("tokens"). You
do not invent a palette. You reference these tokens.

### How theming works

- Each **mood** is a stylesheet scoped to `[data-theme="<id>"]` that defines **only primitive
  tokens**. Switching moods swaps these tokens; **components never change.** Five moods ship today:
  `organic` (default), `modafinil`, `breathe`, `karesansui` (Zen Garden), `vantaca` (Vantacan).
- A small set of **derived tokens** is computed once in `:root` from the primitives — you use these
  freely and never redefine them:
  ```css
  --accent-soft:  color-mix(in oklab, var(--accent) 15%, transparent);
  --success-soft: color-mix(in oklab, var(--success) 14%, transparent);
  --warning-soft: color-mix(in oklab, var(--warning) 15%, transparent);
  --danger-soft:  color-mix(in oklab, var(--danger) 15%, transparent);
  /* legacy aliases used inline */
  --critical-bg: var(--danger-soft);  --high-bg: var(--warning-soft);
  --medium-bg: var(--accent-soft);    --low-bg: var(--surface-hover);
  ```
- Need a *softer/stronger* shade of a token? Use `color-mix(in oklab, var(--token) N%, transparent)`
  — the same mechanism the board already uses. **Never** drop to a literal color.

### The complete primitive token set (every mood defines all of these)

```
Type:       --font-sans   --font-serif
Surfaces:   --bg  --bg-deep  --surface  --surface-hover  --card-bg  --border  --border-soft
Text:       --text  --text-muted  --text-dim
Accents:    --accent  --accent-ink (ink that sits ON an accent fill)  --success  --warning  --danger
Queue hues: --q-agent  --q-collab  --q-human  --q-waiting
Priority:   --prio-critical  --prio-high  --prio-medium  --prio-low
Shape:      --r-card  --r-lane  --r-badge  --r-btn          (radii)
Motion:     --ease     (the ONE shared transition timing, e.g. 0.42s cubic-bezier(...))
Background: --app-bg  --paper  --paper-opacity
```

Reference example (the default `organic` mood — values are **illustrative**; never copy literals
into a component, reference the token name):

```css
[data-theme="organic"] {
  --accent:     oklch(0.748 0.046 140);
  --accent-ink: oklch(0.205 0.020 140);
  --success:    oklch(0.738 0.048 150);
  --warning:    oklch(0.770 0.052 74);
  --danger:     oklch(0.706 0.055 46);
  --card-bg:    oklch(0.220 0.015 124);
  --border-soft:oklch(0.272 0.013 118);
  --text:       oklch(0.902 0.014 92);
  --r-card: 12px; --r-btn: 9px; --r-badge: 6px;
  --ease: 0.42s cubic-bezier(0.22, 0.61, 0.36, 1);
}
```

### Existing component vocabulary to match

Your new surfaces must look native beside these (already in the board's CSS):

- **Cards** — `--card-bg` face, `--border-soft` hairline, `--r-card` radius. A **proximity-hover**
  effect lifts the nearest card (border/bg interpolate toward `--accent`/`--surface-hover` via a
  `--prox` variable). New cards inherit this for free if they use the same outer `.card` shell.
- **Chips** — small rounded pills: `<span class="chip chip-due">`, `.chip-overdue`, `.chip-waiting`,
  `.chip-meeting`, `.chip-cron`. Each maps a tone to `var(--X)` text on `var(--X-soft)` fill.
- **Score chip** — `.card-score` with tone classes `.good` / `.mid` / `.low` →
  `--success` / `--warning` / `--danger` (+ their `-soft`). Used for the judge score (e.g. `8/10`).
- **Actions row** — `.card-actions` (top hairline `--border-soft`); buttons are `.card-action`,
  the primary one is `.card-action.primary` (hover tints toward `--accent-soft`); a destructive one
  is `.card-action.danger` (hover tints toward `--danger-soft`).
- **Lanes / sections** — `.now-section` panels with `--r-lane` radius and `--border-soft` headers.
- **Modal** — `.modal-*` (header / body / actions footer); form controls `.field-input`,
  `.desc-textarea`. The Profile room (§6) should feel like this family.

---

## 3. The card model (how cards are described as data)

The board renders cards from a **declarative registry** (`cardtypes/registry.json`) — *no
per-type rendering code.* A generic renderer walks a fixed **slot order** and fills each slot. You
are designing **how each slot looks** and **how each new card type fills its `body` and `actions`**.

**Slot order (fixed):** `head · title · context · signals · body · actions`

| Slot | Contents |
|---|---|
| `head` | queue/kind glyph + label (left) · judge **score chip** + status mark + task id (right) |
| `title` | one line: a priority dot + the title text |
| `context` | source (origin meeting/cron) · domain — small, muted |
| `signals` | status chips (due / overdue / waiting / schedule / message / jira draft / cron) |
| `body` | **kind-specific** — empty for plain tasks; a diff / preview / agreement block for the new kinds |
| `actions` | 1–N buttons; the **primary** action is visually dominant |

A card declares its type via a `card_type` field (default `"task"`). The registry entry names which
`signals`, which `body` renderer, and which `actions` a type uses. Example (real, current):

```jsonc
"cardTypes": {
  "task":           { "signals": "auto", "actions": ["mark_done", "open_output"], "body": null },
  "recommendation": { "signals": [],     "actions": ["accept", "reject"],         "body": "diff" },
  "receipt":        { "signals": [],     "actions": ["keep", "undo"],             "body": "preview" },
  "graduation":     { "signals": [],     "actions": ["graduate"],                 "body": "agreement" }
}
```

**Important constraint for the body slot:** a card **face** (what shows on the board) is rendered
from a **projection** of the task — it does **NOT** include the task's long-form body text. Faces
get only the small set of fields in §8.3. Full detail lives in the **task-detail modal** (out of
scope — already exists). So your body renderers for the three kinds use **only the projected fields
listed per-kind in §5** — design them to be informative within that small field set.

---

## 4. The card shell — states to design

Design the **generic card shell** (the `.card` outer + the six slots) and, critically, **every
state** below. Most apply to the existing `task` card too; designing them well is what makes the
whole board (incl. onboarding, §9) feel calm.

1. **Default** — resting card on a lane.
2. **Hover / proximity** — the nearest card gently lifts (border + bg interpolate toward accent).
   Keep it subtle; this is ambient, not a click affordance.
3. **Expanded** — optional inline detail reveal (if you choose to support it); soft height ease.
4. **Agent-running** — a subtle **pulse**, *not* a spinner farm. Conveys "working in the
   background" calmly. (Field: `agent_status === 'running'`.)
5. **Needs-human** — the agent paused and needs input. A quiet, inviting "needs you" mark — never
   alarming. (`agent_status === 'needs-human'`.)
6. **Complete / ready-to-review** — agent finished; gently surfaces "ready for you."
   (`agent_status === 'complete'`.)
7. **Failed / stopped** — the agent stopped before producing output. Honest, low-drama.
   (`agent_status === 'failed'`.)
8. **Error / degraded** — an action failed (e.g. a conflict). Plain-language inline message, no
   stack traces, no partial-state ambiguity. (Our backend returns a friendly reason — §8.)
9. **Success-after-action** — after the user disposes of a card, a **gentle confirmation, then it
   settles** (the card leaves the lane on the next refresh). We **suppress success toasts** — the
   board updating *is* the confirmation. Design the quiet "done" beat, not a notification.

**Score chip:** the judge score (e.g. `8/10`) sits in `head`, tone class `good` / `mid` / `low`
mapped to `--success` / `--warning` / `--danger`. Absent when unscored.

---

## 5. The three new card kinds

For each: its **purpose**, the **exact projected fields** it receives on the face, what its **body**
should communicate, and its **actions → real verbs/endpoints** (full shapes in §8). All three
currently render as unstyled placeholder divs; you are giving them their real form.

### 5a. Recommendation card — *the chief-of-staff's standup*

**Purpose.** The load-bearing surface at the top of **Now**. Each is a **proposal** the user
disposes of in **one tap**: *"Here's a change I suggest — Accept or Reject."* Created by the weekly
self-improvement loop (e.g. a tweak to a skill, a worker scope, a voice file). Most carry a concrete
proposed change (a "diff"); some are prose-only (manual-apply guidance).

**Projected face fields available:** `id`, `title`, `priority`, `domain`, `source_meeting`,
`judge_score` (+ tone), `card_type: "recommendation"`, `patch_path` (string path or absent),
`agent_status`.

**Body (`diff`).** Communicate *what change is being proposed* compactly. If `patch_path` is
present, surface the **filename** of the change (the last path segment) framed as
*"Proposed change · `<filename>`"*. If `patch_path` is **absent**, this is a prose-only
recommendation — frame it as a **manual change** (e.g. *"Proposed change (manual)"*). Keep it to a
glanceable line or two on the face; the full diff lives in the modal. (Note: a card face never
receives the raw patch text — only `patch_path`. Design for the filename + framing, not a rendered
diff on the face.)

**Actions:** **Accept** (primary, dominant) · **Reject**.
- **Accept** → `POST /api/tasks/{id}/accept`. Applies the change and **spawns a Receipt card**
  (§5b). On success the recommendation leaves the board. **Failure modes you must design for:**
  - **Prose-only / no auto-apply** → backend returns **409** with a plain message like *"No patch
    to apply automatically — apply this change by hand per the card's notes, then dismiss it."*
    Show this calmly inline; the card stays so the user can read it and reject when done.
  - **Conflict / won't apply** → **409** with a plain reason. Same calm inline treatment.
- **Reject** → `POST /api/tasks/{id}/reject`. Dismisses it (no change applied); card leaves the board.

**Density & empty state.** Default to a **calm single proposal per card.** The **empty state
matters** — an empty recommendations feed should feel like *calm / all-clear / done for now*, not
broken or empty-error. Design that "all clear" state deliberately (it is the most common state for a
healthy system).

### 5b. Receipt card — *past tense, "I already handled it"*

**Purpose.** What the machine **already did.** Default state is *fine*; the user skims and moves on.
Lives in **Activity**. Spawned when a Recommendation is accepted (and, in future, when a capability
is generated). Auto-archives after a while unless flagged.

**Projected face fields available:** `id`, `title` (e.g. *"Applied: <recommendation title>"*),
`judge_score` (+ tone, if any), `card_type: "receipt"`, `revert_commit` (opaque id — **never
shown**), `source_recommendation` (id of the recommendation it came from).

**Body (`preview`).** Exactly three things, no more: **what it did** (a one-line summary of the
change) · optionally **how well** (judge score + a one-line why, if present) · the framing that it's
reversible. Current copy: *"Applied — Undo reverts this change."* Keep it skimmable and reassuring.

**Actions:** **Keep** (primary) · **Undo**.
- **Keep** → `POST /api/tasks/{id}/keep`. Dismisses the receipt, keeping the change. Card leaves
  the board.
- **Undo** → `POST /api/tasks/{id}/undo`. Reverses the change. **Git is invisible** — the button
  says **"Undo,"** never "revert." **Failure mode:** if a later change conflicts, backend returns
  **409** with *"Couldn't undo automatically — later changes conflict; revert by hand."* — show
  calmly inline.

### 5c. Graduation card — *trust, made visible*

**Purpose.** Created by the graduation cron when a task-type has earned a climb up the trust ladder
**shadow → gated → autonomous.** This is a **trust moment**: design it with **weight but not alarm**,
and make its **reversibility** legible (the system auto-demotes if quality later drops — say so).

**Projected face fields available:** `id`, `title` (e.g. *"PRD-draft is ready to graduate to
gated"*), `card_type: "graduation"`, and the evidence block:
- `grad_task_type` (e.g. `"prd-draft"`)
- `grad_current_tier` (e.g. `"shadow"`) → `grad_proposed_tier` (e.g. `"gated"`)
- `grad_approval_pct` (number, e.g. `88`) — rolling human-approval rate
- `grad_agreement_pct` (number, e.g. `82`) — judge↔human agreement
- `grad_n` (number) — sample size in the rolling window
- `grad_examples` (list of task ids — link targets into the modal/detail)

**Body (`agreement`).** Present the **evidence** clearly and reassuringly: the tier transition
(`current → proposed`), the three numbers (**approval %**, **agreement %**, **n**), and a
plain-language line on **what changes if graduated** and that it **auto-demotes if quality drops.**
If you want to show a small **score-trend sparkline**, the Quality API exposes a per-type `history`
array (§8.4) you can reference for the visual language — but the graduation face fields above are
the authoritative data for this card. The `grad_examples` ids should read as linkable example runs.

**Actions:** **Graduate** (primary, dominant) · (a quiet **Not yet** / dismiss is acceptable; today
only **Graduate** is wired — see note).
- **Graduate** → `POST /api/tasks/{id}/graduate`. Advances the task-type to its proposed tier;
  card leaves the board.
- *Note for us (not the Designer's problem):* a "Not yet" dismiss verb isn't wired server-side yet;
  design the button, we'll wire it. Keep it visually secondary.

---

## 6. The Profile / Config room (new surface, in the Engine tab)

The one genuinely **new screen.** For **non-technical users who never open a file.** Everything here
reads/writes plain `profile/*.yaml` and `profile/voice/*.md` files underneath — but the user only
ever sees a **calm, sectioned, form-light** room. Think of it as **settings for a chief of staff**,
not a config panel. Match the modal/form vocabulary from §2.

> **API status:** there is **no profile HTTP API today** — these endpoints are **proposed** (§8.5).
> Build against the mock shapes; we implement the real endpoints during integration. Design the room
> as if the data simply loads and saves.

### Sections (in order)

1. **Identity** — name, email, company, **persona** (PM / Exec / …), timezone. Simple labeled
   fields. Saves to `profile/profile.yaml`.
2. **Integrations** — the heart of the room. Grouped by **category**: *Transcripts* (Otter /
   Granola), *Project management* (Jira / Asana / Linear), *Calendar* (M365 / Google). For each
   category, a **chooser** showing the available adapters and **which is active**, each with a
   **live capability/auth status dot**:
   - **✓ authorized** (`--success`) · **⚠ needs re-auth** (`--warning`) · **✗ not set up** (`--danger`/dim)
   - …and a **"Fix / Authorize"** button that triggers a guided setup flow ("the Doctor"). **This
     is where the standing self-heal surfaces** — e.g. *"Jira needs re-auth — walk you through it?"*
     Design the status dot + Fix button states; the flow itself is conversational on our side.
3. **Voice** — two friendly editors for `teams.md` and `email.md`, framed as **"this is how you
   sound."** Include a **"regenerate from my history"** affordance. These are markdown text areas
   with a warm framing, not a code editor.
4. **Skill packs** — current packs shown as **chips** (e.g. `PM`, `Exec`); an **"Add / swap pack"**
   affordance (one click) listing available packs with short descriptions. **No terminal.**
5. **Model posture** — a simple **low ↔ high** cost-posture control with plain-language explanation
   (*"the cheapest model that still does a great job"*), plus a **read-only** per-worker tier view.
6. **System status** — a **server-running indicator** + the `localhost:<port>` link, a **"Restart
   server"** action, and the Doctor's **overall health summary** (what's installed/authorized,
   what's degraded and why).

### Degraded-feature treatment (important, recurring pattern)

When an integration/tool is missing or unauthorized, the features that depend on it appear
**present but quietly disabled, with a one-line "why + fix"** — **not hidden, not error-spewing.**
This mirrors Magnolia's graceful-degradation philosophy *visually.* Design this disabled-with-reason
treatment as a reusable pattern (it appears across Integrations and any dependent control).

---

## 7. The Quality trust dashboard (restyle existing surface)

The **Quality** tab already exists and reads **real data** from `GET /api/quality` (§8.4). Today it
renders as a bare list. Restyle it into a **calm, weekly, read-only trust dashboard** — *"how much
do I trust the machine, by task-type, and is that trust trending the right way?"*

Per task-type **row/card**, design with this real data:
- `task_type`, `count` (judged), `avg_score`, `trend` (delta, +/−), `history` (last-8 scores → a
  **sparkline**), per-`dimensions` averages.
- **`phase`** — the real ladder tier; map to friendly labels: `shadow` → **"observe-only,"**
  `gated` → **"gated,"** `autonomous` → **"autonomous / trusted."** Design these as a **trust badge.**
- **`agreement_pct`** — judge↔you agreement (or *"no ratings from you yet"* when `reacted` is 0 /
  `agreement_pct` is null).
- A **disagreements** section (`disagreements` list): where the judge and the human diverged — each
  row links into the task. Frame as *learning signal*, calm and non-judgmental.

This is a **read-only** surface — no actions, no buttons. It is a mirror, not a control panel. Tone:
reassuring, weekly-skim, never a dashboard that demands action.

---

## 8. API & data appendix (build your mock against this)

All dynamic data is JSON over `/api/*`. Mock these. Endpoints are marked **[exists]** (live in our
backend today — match the shape exactly) or **[proposed]** (we'll build it; you define a sensible
mock from the description).

### 8.1 Card action verbs — all **[exists]**

`POST` with empty body unless noted. Success → `200 {"ok": true, ...}`. Operator-actionable
failures → **409** with `{"error": "<plain-language message>"}`; unexpected → 500. **Display the
409 message verbatim, calmly, inline on the card.**

| Verb | Endpoint | Success body | 409 cases (design for these) |
|---|---|---|---|
| Accept (recommendation) | `POST /api/tasks/{id}/accept` | `{"ok":true,"receipt_id":"TASK-…"}` | prose-only (no patch); patch won't apply / nothing to commit |
| Reject (recommendation) | `POST /api/tasks/{id}/reject` | `{"ok":true}` | — |
| Keep (receipt) | `POST /api/tasks/{id}/keep` | `{"ok":true}` | — |
| Undo (receipt) | `POST /api/tasks/{id}/undo` | `{"ok":true}` | later changes conflict — "revert by hand" |
| Graduate (graduation) | `POST /api/tasks/{id}/graduate` | `{"ok":true}` | — |
| React (in modal) | `POST /api/tasks/{id}/react` | `{"ok":true,"task_id":"…","react":"up"}` | body: `{"react":"up"|"down","note":"…"?}` |

After any successful action, the board refreshes and the card leaves its lane — **no success toast.**

### 8.2 List / read — all **[exists]**

- `GET /api/tasks` → `{ "tasks": [ <face projection>, … ] }` — the cards on the board.
- `GET /api/activity` → recent receipts/events stream (Activity tab).
- `GET /api/quality` → the trust dashboard data (§8.4).
- `GET /api/tasks/{id}` → full task detail (modal — out of scope, but exists).
- `GET /cardtypes/registry.json` → the card registry (§3) — served as a static file.

### 8.3 The card **face projection** (every field a card face receives)

A card on the board is this dict (fields are absent/null when not set). **Your body/face renderers
may use only these.** (The long-form task body is **not** here — it's modal-only.)

```jsonc
{
  "id": "TASK-0123", "title": "…", "queue": "human|agent|collab|waiting",
  "priority": "critical|high|medium|low", "status": "open|in_progress|done|blocked|…",
  "domain": "ops|product|…", "due": "YYYY-MM-DD"|null,
  "created": "…", "updated": "…",
  "agent_status": "running|needs-human|complete|failed"|null,
  "agent_output": "…"|null, "sharepoint_path": "…"|null,
  "waiting_on": "…"|null, "waiting_expected": "YYYY-MM-DD"|null,
  "source_meeting": "…"|null, "task_type": "…"|null,
  // judge
  "judge_score": 8|null, "judge_why": "…", "judge_dimensions": {"k": v, …},
  "judge_rubric_version": "…", "judge_scored_at": "…", "judge_kind": "document|message|meeting",
  // human react
  "human_react": "up|down"|null, "human_react_note": "…", "human_reacted_at": "…",
  // card-kind
  "card_type": "task|recommendation|receipt|graduation"|null,
  "patch_path": "datasets/…/x.patch"|null,        // recommendation
  "revert_commit": "<opaque>"|null,               // receipt — NEVER displayed
  "source_recommendation": "TASK-…"|null,         // receipt
  "grad_task_type": "prd-draft"|null,             // graduation ↓
  "grad_current_tier": "shadow"|null, "grad_proposed_tier": "gated"|null,
  "grad_n": 12|null, "grad_approval_pct": 88|null, "grad_agreement_pct": 82|null,
  "grad_examples": ["TASK-…", …]|null,
  "file": "human/TASK-0123.md"
}
```

### 8.4 `GET /api/quality` response — **[exists]**

```jsonc
{
  "groups": [
    { "task_type": "prd-draft", "count": 14, "avg_score": 7.8, "trend": 0.6,
      "history": [7.0, 7.5, 8.0, 8.0, …],          // up to last 8, oldest→newest (sparkline)
      "phase": "shadow|gated|autonomous",            // the real ladder tier
      "dimensions": { "clarity": 8.1, "completeness": 7.4, … },
      "agreement_pct": 82|null, "reacted": 9 }       // null/0 → "no ratings from you yet"
  ],
  "disagreements": [
    { "task_id": "TASK-…", "title": "…", "task_type": "prd-draft",
      "judge_score": 4.0, "judge_why": "…", "human_value": 1, "human_comment": "…" }
  ],
  "total_judged": 37, "langfuse": false
}
```

### 8.5 Profile / Config room — **[proposed]** (define a sensible mock)

No HTTP API exists yet; design the room and mock these. Suggested shapes:

- `GET /api/profile` → `{ identity: {name, email, company, persona, timezone},
  integrations: { transcripts: {active, options:[{id,label,status:"ok|reauth|unset"}]},
  project_management: {…}, calendar: {…} }, voice: {teams: "<md>", email: "<md>"},
  packs: {active:["pm"], available:[{id,label,description}]},
  model_posture: {level: "low|balanced|high", workers:[{name, tier}]},
  system: {server_running: true, port: 8743, health:[{name, status, detail}]} }`
- `PUT /api/profile/identity`, `PUT /api/profile/voice`, `POST /api/profile/integrations/{category}`
  (set active provider), `POST /api/doctor/fix/{capability}` (kick the guided flow),
  `POST /api/profile/packs` (add/swap), `PUT /api/profile/model-posture`,
  `POST /api/system/restart`. All return `{"ok": true, …}`.

Don't over-engineer the mock — enough to make the room feel alive and exercise the status-dot,
degraded, and save states.

---

## 9. Onboarding — no new surface (context only)

You do **not** design an onboarding flow. Onboarding is a conversational concierge in our CLI that
**creates ordinary tasks** which render through the **existing `task` card** and dispatch through
the **existing modal** (e.g. *"Draft your voice profile"* = an agent task the user starts and
approves; *"Set up Otter or Granola"* = a collab task). The user learns the system by disposing of
their first real cards.

**The only thing this asks of you:** the **card-shell states in §4** — especially **agent-running**,
**needs-human**, **complete**, and the **collab "needs your action"** feel — are what make that
first-run experience calm and welcoming. Design those states with that first-run moment in mind.

---

## 10. Deliverables checklist

Drop-in **HTML / CSS / JS**, all **token-only** (§2), for:

1. The **card shell + slot system** with **all states** (§4).
2. The **three new card kinds** — Recommendation, Receipt, Graduation — bodies + actions + their
   empty/error/409 states (§5).
3. The **Profile / Config room** with all six sections + the degraded-feature pattern (§6).
4. The **Quality trust dashboard** restyle (§7).

Reference the existing token contract (`:root` / `[data-theme="…"]`) and the component vocabulary in
§2 so everything inherits all five moods. When in doubt, choose **calm** over clever.
