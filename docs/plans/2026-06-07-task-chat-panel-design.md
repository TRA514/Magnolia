# Task-Aware Claude Chat Panel — Design

> Status: approved (brainstorm complete) · 2026-06-07
> Epic: a task-level chat panel that resumes the same headless Claude session the
> background worker used, and feeds every post-run follow-up into the
> self-improvement eval loop.

## 1. What this is

A right-pane chat in the task detail workspace. The user opens a task, sees the
left detail + execution history, and continues the **same Claude Code session**
the background worker ran — not a fresh chat. Replies read like Claude: a
thinking line → inline tool steps → streamed text, with actions visibly settling
the left detail. It is **not a terminal**: the backend drives `claude -p`
server-side and streams normalized events to the browser.

The second, equally-important goal: **every chat follow-up becomes input to the
self-improvement eval loop.** A user having to follow up is itself evidence the
first pass left something on the table; clustered follow-ups become proactive
"let's make this prompt change" recommendations.

## 2. PRD reconciliation — what we kept, fixed, and dropped

The source PRD assumed a stack we don't have. Decisions:

**Kept (good fit):**
- Resume an explicit Claude session by ID; never `--continue`.
- Claude Code owns session/context/tools; Magnolia owns task data, history,
  persistence, permissions. (This is our engine/profile split.)
- Server-driven `claude -p` with normalized events — not a browser terminal.
- One task → at most one primary session → the panel only uses that one.

**Fixed (PRD was wrong for us):**
- *The PRD assumed `claude -p` is already the dispatch path. It isn't.* Today
  `task_dispatch.py:760` runs **interactive** `claude` wrapped in `script -q`
  (pseudo-TTY), `bypassPermissions`, **no `--session-id`, no `--resume`, no
  stream-json**. So "resume the worker's session" first requires the worker to
  *mint a known session id* — net-new (small).
- External actions from chat **must** route through the existing Tier-2
  `publish()` gate (invariant #5). The chat is never a permission bypass.

**Dropped (YAGNI for a file-based engine):**
- The relational `AgentSession` / `AgentRun` / `AgentMessage` entity model and
  "multiple sessions per task" abstraction. Magnolia is markdown + YAML
  frontmatter + git, no DB. We use a `claude_session_id` field + a sidecar
  transcript file. A `run_id` stamped per event gives run-grouping without a run
  table.

## 3. Locked decisions

| Decision | Choice |
|---|---|
| Merge authority | Branch off `main`, build green, open a **PR** for the operator to merge. |
| Dispatcher | **Minimal**: keep interactive dispatch as-is, add `--session-id "$UUID"`, store it. Chat resumes via `claude -p --resume`. |
| Eval signal | **Persist-and-tag at chat time; mine in the existing eval pipeline. No new classifier, no Ollama.** |
| Process model | **Per-turn `claude -p --resume`** (stateless on our side), not a long-lived process. |
| 1h cache TTL | Documented follow-on, not v1. |

## 4. Data model

No new entities. Extend frontmatter + a sidecar file.

**Task frontmatter (new fields):**
```yaml
claude_session_id: "uuid"                      # minted at dispatch (or first chat for human tasks)
session_origin: background_agent | human_chat  # who created the session
chat_last_active: ISO-8601 | null
```

**Transcript — sidecar, not SQL tables:**
```
datasets/tasks/<queue>/<TASK-ID>.chat.jsonl
```
One normalized event per line:
```json
{"turn_id": "...", "role": "user|assistant", "kind": "think|tool_step|text|result",
 "text": "...", "steps": [...], "run_id": "...", "origin": "chat|background",
 "post_run": true, "ts": "ISO-8601"}
```
This is Magnolia's own durable UI history (the PRD's `AgentMessage`, file-style),
reloadable and greppable, independent of Claude Code's internal transcript. Claude
Code still owns the *real* session context; this is what the panel renders and
what the eval loop mines.

## 5. Backend

### (a) Session capture at dispatch — `task_dispatch.py` (minimal)
Generate a UUID; add `--session-id "$UUID"` to the existing interactive
invocation (everything else unchanged — still `script -q`, `bypassPermissions`,
same model resolution). Write `claude_session_id` + `session_origin:
background_agent` to frontmatter at run start. The session JSONL lands under
`~/.claude/projects/<cwd-hash>/<uuid>.jsonl`, resumable because chat runs in the
same cwd.

### (b) Chat runner — `scripts/chat_runner.py` (net-new)
Given task + user message:
- **Resume path** (session exists):
  `claude -p --resume "$SID" --output-format stream-json --verbose --model <resolved> "$MSG"`
- **New-session path** (human task, no prior run — PRD Case B): mint a UUID,
  `--session-id "$SID"`; the *first* prompt carries a structured task-context
  block (title/desc/status/priority/etc.) read **from the task + profile**, never
  hardcoded. Subsequent turns resume.
- Parses stream-json events; normalizes to four kinds — `think` (thinking) ·
  `tool_step` (tool_use) · `text` (assistant text) · `result`. Writes each to
  `.chat.jsonl` and yields it.

### (c) Streaming — SSE on the stdlib server
New route `POST /api/tasks/{id}/chat` opens a `text/event-stream`, runs the runner
as a subprocess, forwards each normalized event as an SSE frame.
`ThreadingHTTPServer` already gives a thread per request; we write+flush chunks.
The four kinds map 1:1 onto what `chat.js` renders.

### (d) Run lock — one active run per session
Guard the chat route on `agent_status: running` (existing field). If the session
is mid-run (background *or* chat), return `409`; the UI disables the composer with
"Agent is currently working." No queueing in v1.

### (e) Tier-2 — non-negotiable
External writes from chat (send message, publish Jira, create meeting) route
through the existing `publish(family, draft)` gate, which raises
`NeedsConfirmation` on first external action → surfaced as an inline confirm in
chat. The demo's free-firing handlers get rewired to the real gated path.

### Cost / rehydration note
Per-turn `claude -p --resume` pays: (1) local spawn + JSONL read (~1–2s, no
tokens); (2) token reprocessing of prior history, governed by the API prompt
cache (5-min TTL default). Cold-open first turn re-bills the whole prior
transcript (~20k–60k tokens estimate → a few cents–~15¢; verify via the
stream-json `result` event's `usage`); cache-warm follow-ups are cheap deltas. A
long-lived process would NOT reduce the token cost (same API-cache economics) — it
only saves the ~1–2s local spawn, at the price of process-lifecycle complexity.
Hence stateless per-turn. The 1h cache-TTL beta header is the real cost lever and
is a documented follow-on.

## 6. Eval integration

### (a) Persist-and-tag at chat time (the cheap guarantee)
Every user chat turn written to `.chat.jsonl` carries `origin: chat` +
`post_run: true`. This is the hard guarantee that post-run chat is *always*
included for feedback — just fields on a line we already write. No LLM, no latency.

### (b) `eval_digest.py` — one new signal bucket
Today it flags `judge_score < 7` and `human_react: down`. Add **post-run
follow-ups**: for each task, read `.chat.jsonl`, collect post-run user turns, emit
a `follow_ups` bucket (by domain / worker / task_type) alongside the existing
flagged set. Still fully deterministic — no model call.

### (c) `eval-analyst` worker — widened input + prompt
It already clusters failures and proposes changes (skill edit / voice.md / worker
scoping / quality gate / golden example) as `.patch` files + recommendation cards.
Widen its input + prompt to also read follow-up clusters and reason "users keep
asking us to X → propose this prompt change." Same recommendation-card + patch
artifacts → lands in the existing Quality tab with **Keep/Undo**. Precision lives
in the analyst (which already has judgment); capture stays dumb and complete.

**The two levers, realized:**
- Lever 1 (judge → human): unchanged — `judge.py` scores, operator 👍/👎 via `/react`.
- Lever 2 (mine follow-ups → propose prompt changes): chat follow-ups now flow into
  the digest; the existing analyst turns clustered corrections into concrete
  recommendation cards.

## 7. Frontend reconciliation

**Reusable asset (keep):** `chat.js`'s render layer (empty whisper, user bubble,
typing dots, thinking line, collapsible tool-step group folding at 5+, streamed
text, action notes) + the split-workspace markup/CSS in `index.html`. Chat styles
are **theme-token clean** (verified) — invariant #3 holds.

**Rewired (demo → real):**
- Delete the scripted `chatReply()` decision tree and the fake `setTimeout`
  streaming. Keep the render functions (`renderTurn`, `renderStepsInto`,
  `collapseGroup`, `streamText`, `actionNote`); change only their *event source*
  to real SSE frames from `POST /api/tasks/{id}/chat`.
- Rewire the demo's action handlers (`doSendMessage`, `doPublishJira`,
  `doCreateMeeting`) to the **real Tier-2-gated endpoints**; preserve the
  settle-the-left-detail effect by re-reading the task after the persisted change.
- Drop `mock-api.js` entirely (preview-only).

**Reconciliation gotcha:** the handoff branched from a base *older* than current
`main` — its `card-registry.js` and `magnolia.css` are **missing the `confirm`
Tier-2 card kind** that exists in live. Copying handoff files wholesale would
regress that gate. **Port the chat additions surgically onto current live files**
(workspace open/close/`revealWorkspace`/`markSourceCard` in `tasks.js` + `agents.js`,
split markup/CSS in `index.html`, new `chat.js`) — never overwrite.

**De-personalization:** the demo hardcodes "Jay Jenkins"/"Chief of Staff". The real
system prompt reads identity + voice from `profile/` via `profile_lib` (invariant
#1). The 👍/👎 "Your take" control posts to the existing `/api/tasks/{id}/react`.

## 8. Gates & verification

- Green gates before every code commit (invariant #2): `pytest` ·
  `card_schema.py` → `registry.json OK` · `test_engine_no_jay.py`.
- Live e2e on the **dev board `localhost:8743`** (invariant #7): dispatch a task
  so it mints a session, open the workspace, send a follow-up, watch real
  thinking → tool steps → streamed text; confirm a Tier-2 action surfaces the
  confirm; confirm the follow-up lands in `.chat.jsonl` with `post_run: true` and
  shows up in `eval_digest`'s `follow_ups` bucket.
- Verify `claude -p --resume` flags + stream-json event shapes empirically during
  the build (spike task) rather than assuming.

## 9. Out of scope (v1)

Forked conversations, visible multi-session UI, session tabs/picker, raw terminal,
message queueing, the 1h cache-TTL knob, slash-command exposure.
