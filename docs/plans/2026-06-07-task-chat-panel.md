# Task-Aware Claude Chat Panel — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A task-level chat panel that resumes the same headless Claude session the background worker ran, streams normalized events into a calm UI, routes external actions through the existing Tier-2 gate, and feeds every post-run follow-up into the eval digest.

**Architecture:** Markdown + YAML frontmatter + git, no DB. A `claude_session_id` on the task + a sidecar `<TASK-ID>.chat.jsonl` transcript. Dispatch mints the session id (`--session-id`); a new `chat_runner.py` resumes it via `claude -p --resume … --output-format stream-json`; a new SSE route on the stdlib `task_server.py` streams normalized events; the existing `eval_digest.py` + `eval-analyst` worker mine post-run follow-ups; the frontend reuses the handoff's chat render layer wired to real SSE.

**Tech Stack:** Python 3 (stdlib `http.server`, `subprocess`), `claude -p` headless, vanilla JS + SSE (`EventSource`/`fetch` stream), theme-token CSS.

**Design doc:** `docs/plans/2026-06-07-task-chat-panel-design.md` (read it first).

**Reference files (current `main`):**
- `scripts/task_dispatch.py:758-792` — the interactive `claude` invocation (mint session id here).
- `scripts/task_server.py:1795+` — `_route_request` regex router; `_json_response` at ~77.
- `scripts/task_lib.py:218-305` (create_task defaults), `:382` read_task, `:550` update_task, `:407` list_tasks projection.
- `scripts/eval_digest.py` — deterministic digest; add `follow_ups` bucket.
- `scripts/workers/eval-analyst.md` — widen input/prompt.
- `scripts/profile_lib.py` — identity/voice getters for the system prompt (de-personalization).
- `scripts/adapters/__init__.py:54-62` — `publish()` Tier-2 gate.
- Frontend handoff (port FROM, do not copy): `~/Downloads/magnolia-chat-extract/magnolia-handoff/` → `js/chat.js`, `index.html`, `js/tasks.js`, `js/agents.js`, `js/card-registry.js`, `css/magnolia.css`.

**Gates (run before every code commit — invariant #2):**
```
python3 -m pytest
python3 scripts/card_schema.py        # expect: registry.json OK
python3 -m pytest tests/test_engine_no_jay.py
```

**Iron rules:** branch is `feat/task-chat-panel` (already created). Never commit to `main`. End commits with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer. Dev board only (`localhost:8743`). De-personalize: read identity from `profile/`, never literal "Jay". Subagents inspect history with `git show`/`git diff`, never `git checkout`.

---

## Milestone 0 — De-risk the CLI assumptions (spike)

### Task 0: Verify `claude -p` resume + stream-json shapes; capture a fixture

The entire feature rests on these flags and event shapes. Verify empirically before building on them.

**Files:**
- Create: `tests/fixtures/stream_json_sample.jsonl` (captured real events)
- Create: `docs/plans/notes/claude-cli-verification.md` (what was confirmed)

**Step 1: Confirm flags exist**
```bash
claude --help 2>&1 | grep -E -- '--session-id|--resume|--output-format|--verbose'
```
Expected: all four present. If `--session-id` or `stream-json` differ, STOP and report — the plan needs adjustment.

**Step 2: Create a session with a known id and capture stream-json**
```bash
SID=$(python3 -c "import uuid;print(uuid.uuid4())")
cd ~/dev/pm-os-team
claude -p --session-id "$SID" --output-format stream-json --verbose \
  --allowedTools "Read(*)" "Say hello and read README.md if present." \
  > /tmp/cc_create.jsonl 2>/tmp/cc_create.err; echo "exit=$?"
head -c 2000 /tmp/cc_create.jsonl
```

**Step 3: Resume it and capture again**
```bash
claude -p --resume "$SID" --output-format stream-json --verbose \
  "What did I just ask you?" > /tmp/cc_resume.jsonl 2>/tmp/cc_resume.err; echo "exit=$?"
head -c 2000 /tmp/cc_resume.jsonl
```
Expected: resume succeeds (exit 0), reply references the prior turn → continuity confirmed.

**Step 4: Save a representative fixture + note the shapes**
- Copy a handful of real event lines (one each of: system/init, assistant-with-text, assistant-with-tool_use, user/tool_result, result) into `tests/fixtures/stream_json_sample.jsonl`.
- Write `docs/plans/notes/claude-cli-verification.md`: the exact event `type`/`subtype` keys, where assistant text lives (`message.content[].text`), where tool calls live (`message.content[].type=="tool_use"` → `name`,`input`), where thinking lives (if a `thinking` block type appears), and where `usage`/`cost` lives on the `result` event.

**Step 5: Commit**
```bash
git add tests/fixtures/stream_json_sample.jsonl docs/plans/notes/claude-cli-verification.md
git commit -m "spike: verify claude -p resume + capture stream-json fixture"
```

> If any assumption fails, surface it before continuing — later tasks consume this fixture.

---

## Milestone 1 — Data layer: session id + transcript

### Task 1: Task frontmatter gains session fields

**Files:**
- Modify: `scripts/task_lib.py:218-305` (`create_task` defaults)
- Test: `tests/test_task_chat_fields.py`

**Step 1: Failing test**
```python
# tests/test_task_chat_fields.py
import task_lib

def test_new_task_has_session_fields(tmp_task_env):  # reuse existing task-env fixture
    tid = task_lib.create_task("chat field probe", queue="agent")
    fm = task_lib.read_task(tid)["frontmatter"]
    assert fm["claude_session_id"] is None
    assert fm["session_origin"] is None
    assert fm["chat_last_active"] is None

def test_update_roundtrips_session_id(tmp_task_env):
    tid = task_lib.create_task("rt", queue="agent")
    task_lib.update_task(tid, {"claude_session_id": "abc-123", "session_origin": "background_agent"})
    fm = task_lib.read_task(tid)["frontmatter"]
    assert fm["claude_session_id"] == "abc-123"
    assert fm["session_origin"] == "background_agent"
```
(If no `tmp_task_env` fixture exists, mirror the setup in the nearest existing `tests/test_task*.py`.)

**Step 2: Run → fail** `python3 -m pytest tests/test_task_chat_fields.py -v` → KeyError / None mismatch.

**Step 3: Implement** — in the base `frontmatter` dict in `create_task` (near `"agent_status": None,` at :264), add:
```python
        "claude_session_id": None,
        "session_origin": None,     # background_agent | human_chat
        "chat_last_active": None,
```
Confirm `update_task` (`:550`) already merges arbitrary keys (it does — generic `changes` dict). No change needed there.

**Step 4: Run → pass.** Then the gates.

**Step 5: Commit** `feat(tasks): session-id + chat fields on task frontmatter`

---

### Task 2: Transcript sidecar module

**Files:**
- Create: `scripts/chat_transcript.py`
- Test: `tests/test_chat_transcript.py`

**Step 1: Failing test**
```python
# tests/test_chat_transcript.py
import json, chat_transcript as ct

def test_append_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "_transcript_path", lambda tid: tmp_path / f"{tid}.chat.jsonl")
    ct.append_event("TASK-0001", {"role": "user", "kind": "text", "text": "hi",
                                  "run_id": "r1", "origin": "chat", "post_run": True})
    ct.append_event("TASK-0001", {"role": "assistant", "kind": "text", "text": "hello", "run_id": "r1"})
    events = ct.read_events("TASK-0001")
    assert len(events) == 2
    assert events[0]["text"] == "hi" and events[0]["post_run"] is True
    assert "turn_id" in events[0] and "ts" in events[0]   # stamped on append

def test_read_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "_transcript_path", lambda tid: tmp_path / f"{tid}.chat.jsonl")
    assert ct.read_events("TASK-NOPE") == []
```

**Step 2: Run → fail** (module missing).

**Step 3: Implement** `scripts/chat_transcript.py`:
```python
#!/usr/bin/env python3
"""Sidecar chat transcript: one normalized event per line at
datasets/tasks/<queue>/<TASK-ID>.chat.jsonl. Magnolia's own durable UI history,
independent of Claude Code's internal transcript. No LLM, no network."""
import json, uuid
from datetime import datetime, timezone
from pathlib import Path
import task_lib

def _now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _transcript_path(task_id):
    # Co-locate with the task .md so it travels with the task.
    md = Path(task_lib.task_path(task_id))   # use existing path resolver
    return md.with_suffix(".chat.jsonl")

def append_event(task_id, event):
    e = dict(event)
    e.setdefault("turn_id", uuid.uuid4().hex)
    e.setdefault("ts", _now())
    p = _transcript_path(task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(e, default=str) + "\n")
    return e

def read_events(task_id):
    p = _transcript_path(task_id)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try: out.append(json.loads(line))
            except json.JSONDecodeError: pass
    return out
```
> Verify `task_lib.task_path(task_id)` (or equivalent) exists; if the resolver has another name, use it. If none exists, add a small one rather than hardcoding the queue dir.

**Step 4: Run → pass.** Gates.

**Step 5: Commit** `feat(chat): sidecar transcript module (.chat.jsonl)`

---

## Milestone 2 — Dispatch mints the session id

### Task 3: Background dispatch creates a known, resumable session

**Files:**
- Modify: `scripts/task_dispatch.py:758-792`
- Test: `tests/test_dispatch_session_id.py`

**Step 1: Failing test** — assert the command carries `--session-id <uuid>` and the task gets `claude_session_id` written. Factor the command build so it's testable:
```python
# tests/test_dispatch_session_id.py
import re, task_dispatch as td

def test_build_claude_cmd_includes_session_id():
    cmd, sid = td.build_claude_cmd(prompt="x", model="m", tools_str="Read(*)", max_turns="30")
    assert "--session-id" in cmd
    assert cmd[cmd.index("--session-id") + 1] == sid
    assert re.match(r"[0-9a-f-]{36}", sid)
```

**Step 2: Run → fail** (no `build_claude_cmd`).

**Step 3: Implement** — extract the `claude_cmd` list (`:760`) into a helper and call it; write the session id to frontmatter right after spawn:
```python
def build_claude_cmd(prompt, model, tools_str, max_turns, session_id=None):
    sid = session_id or str(uuid.uuid4())   # import uuid at top
    cmd = ["claude", prompt, "--model", model, "--allowedTools", tools_str,
           "--max-turns", max_turns, "--permission-mode", "bypassPermissions",
           "--session-id", sid]
    return cmd, sid
```
At the call site (replacing the inline `claude_cmd = [...]`):
```python
    claude_cmd, claude_session_id = build_claude_cmd(prompt, model, tools_str, max_turns)
    cmd = ["script", "-q", output_file] + claude_cmd
```
After the successful `subprocess.Popen` (around `:792`), persist:
```python
    task_lib.update_task(task_id, {
        "claude_session_id": claude_session_id,
        "session_origin": "background_agent",
    })
```

**Step 4: Run → pass.** Gates. (The `--session-id` arg position is harmless to the existing interactive flow.)

**Step 5: Commit** `feat(dispatch): mint resumable --session-id and store on task`

---

## Milestone 3 — The chat runner

### Task 4: De-personalized system prompt + command builder

**Files:**
- Create: `scripts/chat_runner.py`
- Test: `tests/test_chat_runner_cmd.py`

**Step 1: Failing test**
```python
# tests/test_chat_runner_cmd.py
import chat_runner as cr

def test_resume_cmd_uses_resume_not_session_id():
    cmd = cr.build_chat_cmd(session_id="S1", message="hi", model="m", new_session=False)
    assert "--resume" in cmd and cmd[cmd.index("--resume")+1] == "S1"
    assert "--session-id" not in cmd
    assert "--output-format" in cmd and cmd[cmd.index("--output-format")+1] == "stream-json"

def test_new_session_cmd_uses_session_id():
    cmd = cr.build_chat_cmd(session_id="S2", message="hi", model="m", new_session=True)
    assert "--session-id" in cmd and "--resume" not in cmd

def test_system_prompt_is_depersonalized(monkeypatch):
    monkeypatch.setattr(cr.profile_lib, "identity", lambda: {"name": "Dana Cole", "role": "PM"})
    task = {"id": "TASK-9", "title": "T", "queue": "agent", "status": "open"}
    p = cr.build_context_prompt(task, "do the thing")
    assert "Jay" not in p
    assert "Dana Cole" in p          # pulled from profile, not literal
    assert "do the thing" in p
```

**Step 2: Run → fail.**

**Step 3: Implement** the two builders in `scripts/chat_runner.py`. `build_chat_cmd` mirrors the design's resume/new-session forms (always `--output-format stream-json --verbose`, restricted `--allowedTools` excluding external-write MCP — see Task 7). `build_context_prompt` reads `profile_lib.identity()` / voice and the task fields; **no string literals naming a person.** Excludes the full chat history (Claude Code owns resumed context); only the new-session path injects task context.

**Step 4: Run → pass + gates** (especially `test_engine_no_jay.py` — the prompt builder must stay denylist-clean).

**Step 5: Commit** `feat(chat): chat_runner command + de-personalized context prompt`

---

### Task 5: stream-json → normalized events

**Files:**
- Modify: `scripts/chat_runner.py`
- Test: `tests/test_chat_runner_normalize.py` (consumes `tests/fixtures/stream_json_sample.jsonl` from Task 0)

**Step 1: Failing test**
```python
import json, chat_runner as cr

def test_normalize_maps_event_kinds():
    lines = open("tests/fixtures/stream_json_sample.jsonl").read().splitlines()
    raw = [json.loads(l) for l in lines if l.strip()]
    events = [e for r in raw for e in cr.normalize(r)]
    kinds = {e["kind"] for e in events}
    assert "text" in kinds            # assistant prose
    assert "tool_step" in kinds       # a tool_use mapped
    # result carries usage so we can measure cost
    result = [e for e in events if e["kind"] == "result"]
    assert result and "usage" in result[0]
```

**Step 2: Run → fail.**

**Step 3: Implement** `normalize(raw_event)` per the *actual* shapes documented in Task 0: assistant `message.content[]` → `text` and `tool_step` (`{verb, target}` from `name`/`input`), thinking blocks → `think`, the terminal `result` event → `{kind:"result", usage, cost}`. Return a list (one raw event can yield several normalized rows).

**Step 4: Run → pass + gates.**

**Step 5: Commit** `feat(chat): normalize stream-json into think/tool_step/text/result`

---

### Task 6: Runner persists turns with eval tags; resolves resume-vs-new

**Files:**
- Modify: `scripts/chat_runner.py`
- Test: `tests/test_chat_runner_persist.py`

**Step 1: Failing test** — `run_turn(task_id, message)`:
- writes the user turn with `origin="chat"`, `post_run=True` when the task already completed a background run (i.e., `agent_status == "complete"` or a prior session exists), else `post_run=False`;
- chooses new-session when `claude_session_id` is empty (and writes it + `session_origin="human_chat"`), resume otherwise;
- writes each normalized assistant event to the transcript;
- stamps `chat_last_active`.
Mock the subprocess to emit fixture lines; assert transcript contents + frontmatter via the Task-1/2 seams.

**Step 2: Run → fail.**

**Step 3: Implement** `run_turn` as a generator that yields normalized events (so the SSE route can stream them) while side-effecting the transcript + frontmatter. Subprocess invocation isolated behind a `_spawn(cmd)` seam the test monkeypatches.

**Step 4: Run → pass + gates.**

**Step 5: Commit** `feat(chat): run_turn persists tagged turns + resolves session`

---

### Task 7: Constrain the chat toolset (Tier-2 safety)

**Files:**
- Modify: `scripts/chat_runner.py` (the `--allowedTools` for chat)
- Test: `tests/test_chat_runner_tools.py`

**Step 1: Failing test**
```python
import chat_runner as cr
def test_chat_tools_exclude_external_writes():
    tools = cr.CHAT_ALLOWED_TOOLS
    joined = ",".join(tools)
    # read/search/draft ok; external-write MCP NOT granted to the session
    assert "Read(*)" in joined
    for banned in ("createIssue", "sendMessage", "createEvent", "publish"):
        assert banned not in joined
    # broad mcp__* wildcard must NOT be present (it would grant external sends)
    assert "mcp__*" not in tools
```

**Step 2: Run → fail.**

**Step 3: Implement** a `CHAT_ALLOWED_TOOLS` allowlist (Read/Grep/Glob/Write/Edit on local artifacts + read-only MCP like `mcp__qmd__*`, `mcp__claude_ai_Pendo__*` queries) — and explicitly NOT the `mcp__*` wildcard nor any external-write tool. `build_chat_cmd` uses it. External actions are surfaced to the UI and routed to the gated board verbs (Task 12), never fired by the session.

**Step 4: Run → pass + gates.**

**Step 5: Commit** `feat(chat): restrict chat toolset; external writes stay board-gated`

---

## Milestone 4 — SSE chat endpoint

### Task 8: `POST /api/tasks/{id}/chat` streams events; run-lock guard

**Files:**
- Modify: `scripts/task_server.py` (add `_sse_*` helpers near `:77`; `handle_chat` handler; route in `_route_request` near `:1924`)
- Test: `tests/test_chat_route.py`

**Step 1: Failing tests**
- Route resolves: a `POST /api/tasks/TASK-0001/chat` dispatches to `handle_chat` (test the router mapping like existing route tests, or via a lightweight request).
- Run-lock: when the task's `agent_status == "running"`, `handle_chat` responds `409` and does NOT spawn a runner.

**Step 2: Run → fail.**

**Step 3: Implement**
- SSE helpers: `_sse_begin(handler)` sends `200` with `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`, CORS; `_sse_send(handler, obj)` writes `data: {json}\n\n` and `handler.wfile.flush()`; `_sse_end(handler)`.
- `handle_chat(handler, task_id)`: read JSON body (`{message}`) like `handle_react`; if running → `_error_response(409)`; else set `agent_status="running"`, `_sse_begin`, iterate `chat_runner.run_turn(...)` → `_sse_send` each; on completion clear the lock (`agent_status` back to prior/`complete`), `_sse_end`. Wrap in try/finally so the lock always clears.
- Route: regex `^/api/tasks/([^/]+)/chat$` + POST, mirroring the `react` block at `:1924`.

**Step 4: Run → pass + gates.**

**Step 5: Commit** `feat(server): SSE chat endpoint with per-session run lock`

---

## Milestone 5 — Eval integration

### Task 9: `eval_digest.py` gains a `follow_ups` bucket

**Files:**
- Modify: `scripts/eval_digest.py` (`build_digest` ~:68-126; `_write_markdown` ~:148)
- Test: `tests/test_eval_digest_followups.py`

**Step 1: Failing test** — seed a task whose `.chat.jsonl` has ≥1 `post_run: true` user turn; assert `build_digest(...)` payload has a `follow_ups` key clustering it by `domain`/`task_type`, with counts and sample texts, and that `digest.md` renders a "## Post-run follow-ups" section.

**Step 2: Run → fail.**

**Step 3: Implement** — after the `flagged` loop, scan tasks for transcripts via `chat_transcript.read_events`, collect `post_run` user turns, cluster by `task.get("task_type") or task.get("domain")`, add to `payload["follow_ups"]`. Deterministic — no LLM. Add the markdown section in `_write_markdown`. Keep existing keys unchanged (eval-analyst contract).

**Step 4: Run → pass + gates.**

**Step 5: Commit** `feat(eval): digest surfaces post-run chat follow-ups`

---

### Task 10: `eval-analyst` worker mines follow-up clusters

**Files:**
- Modify: `scripts/workers/eval-analyst.md` (the prompt body, not the frontmatter `match`)
- Test: `python3 -m pytest tests/test_engine_no_jay.py` (denylist) + `card_schema.py`

**Step 1:** Add a section to the worker prompt: read `digest.json`'s `follow_ups` alongside `flagged`; treat a recurring follow-up pattern (e.g., "users keep asking to tighten messages") as a first-class improvement signal; propose the matching altitude change (voice.md / skill / worker scoping / golden example) as a `.patch` + `recommendation` card — same artifacts it already emits. Make explicit: a single follow-up is weak signal; only *clustered* follow-ups warrant a proposal (precision lives here, not at capture).

**Step 2:** Run `test_engine_no_jay.py` (worker md is scanned) + `card_schema.py`. Expected: pass / `registry.json OK`.

**Step 3: Commit** `feat(eval): eval-analyst proposes prompt changes from follow-up clusters`

---

## Milestone 6 — Frontend reconciliation (port onto current `main`, never overwrite)

> No JS test harness — verification is visual/e2e (per the visual-pass technique: Chrome headless against `localhost:8743`). Each task: port, then load the board and confirm no console errors + the behavior.

### Task 11: Add `js/chat.js` (render layer kept, demo brain removed)

**Files:**
- Create: `ui/task-board/js/chat.js`

**Steps:**
1. Copy the handoff `js/chat.js` render layer: `buildChat`, `renderTurn`, `stepHtml`, `makeStepsGroup`, `collapseGroup`, `renderStepsInto`, `scrollThread`, `streamText`, `actionNote`, `pulse`, `setStatus`, `markFooterDone`, `addDetailActivity`.
2. **Delete** `chatReply`, `longRun`, `replyExplain`, `defaultLine`, and the scripted `_sleep`-driven branches in `sendChat`.
3. Rewrite `sendChat` to POST `{message}` to `/api/tasks/{id}/chat` and consume the **SSE stream** (`fetch` + `ReadableStream` reader, or `EventSource` via a GET variant — prefer `fetch` POST stream): for each frame, dispatch by `kind` to the existing renderers (`think`→thinking line, `tool_step`→step row in the live group with collapse-at-5, `text`→`streamText`, `result`→finalize). On a `409`, disable the composer with "Agent is currently working."
4. `buildSystemPrompt` is removed from the client (the server owns the prompt).
5. Reference `index.html` script order so `chat.js` loads with the others.

**Verify:** board loads, open a task → empty whisper renders, composer focuses. (Live streaming verified in Task 16.)

**Commit** `feat(ui): task-assistant chat panel wired to SSE`

---

### Task 12: Port the split-workspace markup + CSS into `index.html`

**Files:**
- Modify: `ui/task-board/index.html`

**Steps:**
1. Port the `.split-modal` / `.task-pane` / `.chat-pane` / `.chat-*` markup (handoff `index.html:1227+`) and styles (`:951-1162`) into the live `index.html`. **Theme tokens only** (already token-clean — keep it that way; no hex/rgb).
2. Add the `<script src="js/chat.js">` tag in the existing script block. **Do NOT** add `mock-api.js`.
3. Preserve everything already in live `index.html` (don't drop existing modal markup other tabs depend on).

**Verify:** board renders, layout correct at wide + narrow (stack) widths, no console errors.

**Commit** `feat(ui): split workspace markup + styles`

---

### Task 13: Port workspace open/close/reveal into `tasks.js` + `agents.js`

**Files:**
- Modify: `ui/task-board/js/tasks.js`, `ui/task-board/js/agents.js`

**Steps:**
1. Apply the handoff diffs surgically: in `tasks.js`, the `buildChat(task)` + `markSourceCard` + `revealWorkspace` calls on open, and the animated `closeModal` with `.closing`/`.visible`/`ws-open` teardown; add `revealWorkspace` + `markSourceCard`.
2. In `agents.js`, add the `no-chat`/`ws-open`/`revealWorkspace` open path for agent details.
3. **Verify the `confirm` Tier-2 card kind is intact** in `card-registry.js` and `magnolia.css` (live has it; handoff dropped it — do NOT regress). Run `card_schema.py`.

**Verify:** open/close animations work; opening a confirm/recommendation/receipt card still renders its actions.

**Commit** `feat(ui): linked-chat workspace open/close wiring`

---

### Task 14: Rewire chat actions to the gated board verbs

**Files:**
- Modify: `ui/task-board/js/chat.js`

**Steps:**
1. `doSendMessage` / `doPublishJira` / `doCreateMeeting` / `doMarkDone` call the **real** endpoints (`/api/tasks/{id}/send-message`, `/publish-jira`, `/schedule-meeting`, `/done`) — the same Tier-2-gated verbs the board already uses — then re-read the task to settle the left detail.
2. When the server signals a needed confirm (Tier-2), surface the inline confirm in chat before calling the verb. (Reuse the board's existing confirm affordance pattern.)
3. Keep `actionNote` for the settled-state feedback.

**Verify:** triggering an external action shows a confirm, not a silent send.

**Commit** `feat(ui): chat external actions route through Tier-2-gated verbs`

---

## Milestone 7 — Gates + live e2e

### Task 15: Final denylist + schema sweep

```bash
python3 -m pytest
python3 scripts/card_schema.py            # registry.json OK
python3 -m pytest tests/test_engine_no_jay.py
grep -rn "Jay" ui/task-board/js/chat.js scripts/chat_runner.py   # expect: no identity literals
```
**Commit** (if any cleanup) `chore: green gates + denylist clean`

### Task 16: Live e2e on the dev board (`localhost:8743`)

1. Start the dev board (port 8743 per `profile/config.yaml`).
2. Dispatch an agent task → confirm `claude_session_id` + `session_origin: background_agent` land on the task.
3. Open the task workspace → send a follow-up ("why this approach?") → watch **real** thinking → tool steps → streamed reply (collapses at 5+ steps).
4. Confirm `.chat.jsonl` has the user turn with `origin: chat`, `post_run: true`.
5. Trigger an external action ("send it") → confirm the **inline confirm** appears and routes to the gated verb.
6. Run `python3 scripts/eval_digest.py --all` → confirm a `follow_ups` bucket with the new turn; eyeball `digest.md`'s "Post-run follow-ups" section.
7. Capture the stream-json `result` `usage` to record real cold-open token cost (validates the design's estimate).
8. Note results in `docs/plans/notes/` or the PR body.

### Task 17: Finish the branch
Invoke **superpowers:finishing-a-development-branch** → push `feat/task-chat-panel` → `gh pr create --base main` with a summary (what shipped, the PRD reconciliation, the eval seam, e2e evidence + measured cost). Operator merges.

---

## Notes for the executor
- DRY/YAGNI/TDD; commit after every green task.
- Each backend task has real tests; frontend tasks verify visually + e2e (no JS harness).
- If Task 0 reveals different flags/shapes, STOP and adjust the plan before proceeding.
- Never copy handoff files wholesale — port onto current `main` (the `confirm` card regression trap).
- Keep the engine de-personalized: identity from `profile/`, never a literal.
