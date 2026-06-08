"""Task-aware Claude chat panel runner.

Built incrementally across Tasks 4-7:
  - Task 4 (this file): pure builders — the `claude -p` argv and the
    de-personalized task-context system prompt for a NEW session's first turn.
  - Task 5: stream-json normalization.
  - Task 6: run_turn persistence (subprocess + file writes).
  - Task 7: locked-down tool allowlist (CHAT_ALLOWED_TOOLS).

The builder functions here are PURE: no subprocess, no file writes. Identity is
read ONLY through profile_lib (invariant #1) — never a hardcoded person literal.

`run_turn` (Task 6) is the impure orchestration seam: it reads the task, resolves
resume-vs-new, spawns `claude` behind the mockable `_spawn` seam, normalizes each
stdout line, persists tagged turns to the sidecar transcript, updates task
frontmatter, and yields each normalized event for the SSE route to stream.
"""
import datetime
import json
import os
import signal
import subprocess
import uuid

import profile_lib
import task_lib
import chat_transcript

# Reuse dispatch's process-group teardown verbatim so chat and background runs
# share one battle-tested kill path (SIGTERM → wait(timeout=5) → SIGKILL the
# whole group). The import is side-effect-free: task_dispatch's module body is
# only imports + constant assignments, and the server already imports it.
from task_dispatch import _kill_process_group

# Repo root — the cwd `claude` runs in, mirroring task_dispatch.PM_OS_DIR.
PM_OS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── Tier-2 safety boundary: the chat session's tool allowlist ───────────────
#
# This is the load-bearing Tier-2 gate for the chat panel (invariant #5).
# The dispatcher runs `claude` with bypassPermissions, so Claude's permission
# MODE is NOT the gate — the gate is that the chat session is simply never
# GRANTED any external-write tool. The chat can read/search/draft/edit LOCAL
# artifacts; when the operator says "send it", the FRONTEND surfaces a confirm
# and calls the existing gated board endpoint (e.g. /api/tasks/{id}/send-message),
# which runs the Tier-2 publish() confirm. So: chat prepares/drafts, the board
# publishes. The headless session can NEVER itself fire an external write.
#
# Therefore this allowlist DELIBERATELY EXCLUDES:
#   - the broad `mcp__*` wildcard (would grant every MCP write — Jira/Teams/
#     Slack/M365/calendar/Asana sends),
#   - every external-write MCP tool (createIssue, sendMessage, createEvent, …),
#   - `Bash(*)` / unrestricted Bash (could `curl`/`gh`/`mail` an external send).
# Bash is scoped to read-only git inspection subcommands only.
#
# Err on the side of fewer tools. To add a tool, prove it cannot write to the
# outside world.
CHAT_ALLOWED_TOOLS = [
    # Local artifact read / search / draft / edit — the whole point of the panel.
    "Read", "Grep", "Glob", "Write", "Edit",
    # Read-only git inspection only — narrowly scoped so Bash cannot shell out
    # to send (no plain `Bash`, no `Bash(*)`).
    "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)", "Bash(git status:*)",
    # Read-only semantic search over the local PM-OS corpus (qmd). These query/
    # fetch only — qmd has no write surface.
    "mcp__qmd__query", "mcp__qmd__get", "mcp__qmd__multi_get", "mcp__qmd__status",
]


def build_chat_cmd(session_id, message, model, new_session=False, allowed_tools=None):
    """Build the `claude` argv for a chat turn.

    The prompt MUST stay the first positional arg: --allowedTools is variadic
    and would otherwise swallow a trailing prompt (verified in the CLI spike,
    see docs/plans/notes/claude-cli-verification.md). --allowedTools therefore
    goes LAST so nothing trails it.

    new_session=True  -> start a fresh session with --session-id <id>.
    new_session=False -> resume an existing session with --resume <id>.
    """
    tools = allowed_tools or ",".join(CHAT_ALLOWED_TOOLS)
    session_flag = "--session-id" if new_session else "--resume"
    return [
        "claude",
        message,
        "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--model", model,
        session_flag, session_id,
        "--allowedTools", tools,
    ]


def build_context_prompt(task, user_message):
    """Build the first-turn system/context prompt for a NEW chat session.

    Only the FIRST turn of a new session gets this prompt: it frames the
    assistant and embeds the task context plus the operator's message. Resumed
    sessions send the user message alone — Claude Code owns the resumed context,
    so we never replay chat history here.

    Identity is read ONLY via profile_lib (display_name / company / persona) —
    never a hardcoded person literal (invariant #1).
    """
    name = profile_lib.display_name()
    company = profile_lib.company()
    persona = profile_lib.persona()

    # Task-context block. Always-present fields first, then any optional ones.
    lines = [
        "## Task context",
        f"- id: {task.get('id', '(none)')}",
        f"- title: {task.get('title', '(untitled)')}",
        f"- status: {task.get('status', '(unknown)')}",
        f"- priority: {task.get('priority', '(unset)')}",
        f"- queue: {task.get('queue', '(unset)')}",
    ]
    optional = [
        ("project", task.get("project")),
        ("domain", task.get("domain")),
        ("due", task.get("due")),
        ("description", task.get("description") or task.get("body")),
    ]
    for label, value in optional:
        if value:
            lines.append(f"- {label}: {value}")
    task_block = "\n".join(lines)

    where = f" at {company}" if company else ""
    return (
        f"You are the task execution assistant for {name}{where} inside Magnolia, "
        f"acting as their {persona}. Continue as the task execution assistant for "
        f"the task below: help move it forward, ask only when genuinely blocked, "
        f"and keep replies concise.\n\n"
        f"{task_block}\n\n"
        f"## {name}'s message\n"
        f"{user_message}"
    )


# Order in which we probe a tool_use's input dict for a human-readable target.
_TARGET_KEYS = ("file_path", "path", "pattern", "command", "query", "url", "description")


def normalize(raw_event):
    """Map one raw `claude --output-format stream-json` event to a list of
    normalized UI events.

    The four UI kinds are: ``think``, ``tool_step``, ``text``, ``result``.
    An ``assistant`` event with multiple content blocks yields multiple rows,
    in order. Uninteresting or unknown events (``system``, ``user``/tool_result,
    ``rate_limit_event``, anything else) yield ``[]``. Pure: no I/O, never
    raises on missing/malformed ``message``/``content``.
    """
    if not isinstance(raw_event, dict):
        return []

    etype = raw_event.get("type")

    if etype == "assistant":
        out = []
        message = raw_event.get("message") or {}
        content = message.get("content") or []
        if not isinstance(content, list):
            return []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                out.append({
                    "kind": "text",
                    "role": "assistant",
                    "text": block.get("text", ""),
                })
            elif btype == "thinking":
                out.append({
                    "kind": "think",
                    "role": "assistant",
                    "text": block.get("thinking", ""),
                })
            elif btype == "tool_use":
                tool_input = block.get("input") or {}
                target = ""
                for key in _TARGET_KEYS:
                    value = tool_input.get(key)
                    if value:
                        target = str(value)
                        break
                out.append({
                    "kind": "tool_step",
                    "role": "assistant",
                    "verb": block.get("name", ""),
                    "target": target,
                })
        return out

    if etype == "result":
        return [{
            "kind": "result",
            "usage": raw_event.get("usage", {}),
            "cost": raw_event.get("total_cost_usd"),
            "session_id": raw_event.get("session_id"),
        }]

    # system, user/tool_result, rate_limit_event, and anything else: noise.
    return []


# ─── Task 6: orchestration seam ──────────────────────────────────────────────

def _now_iso():
    """Current UTC time as an ISO-8601 'Z' string (mirrors task_lib._now_iso)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chat_env():
    """Env for the claude subprocess.

    Mirrors task_dispatch's handling: strip every CLAUDE*/CMUX_CLAUDE* var so the
    child doesn't detect a nested session, and prepend ~/.local/bin (where
    `claude` lives) + /opt/homebrew/bin to PATH so it resolves under cron/headless.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLAUDE", "CMUX_CLAUDE"))}
    env["PATH"] = (
        os.path.join(os.path.expanduser("~"), ".local", "bin")
        + ":/opt/homebrew/bin"
        + ":" + env.get("PATH", "/usr/bin:/bin")
    )
    return env


def _spawn(cmd, exit_holder=None):
    """Spawn `claude` and yield its stdout lines, owning the process lifecycle.

    Thin, monkeypatchable seam so run_turn's logic is testable without invoking
    the real CLI. stderr is discarded; we iterate stdout line-by-line so the SSE
    route can stream events as they arrive.

    Lifecycle ownership (C1): the child is launched in its OWN session/process
    group (start_new_session=True) so the whole `claude` process TREE can be
    killed as a unit. A try/finally guarantees teardown even when the consumer
    closes the generator early — the normal SSE case, where the browser
    disconnects and the generator receives GeneratorExit at the `yield`. On any
    exit we close the pipe and, if the process is still running, SIGTERM →
    wait → SIGKILL the group via the shared dispatch helper. This is what
    prevents orphaned/zombie `claude` trees under the long-lived server.

    The subprocess return code is written into ``exit_holder['returncode']``
    (when a dict is supplied) so run_turn can detect abnormal termination (I1).
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=PM_OS_DIR,
        env=_chat_env(),
        start_new_session=True,  # own process group for clean kill (C1)
    )
    try:
        yield from proc.stdout
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        # Normal end-of-stream: reap. Early close / mid-stream: kill the group.
        if proc.poll() is None:
            _kill_process_group(proc)
        if exit_holder is not None:
            exit_holder["returncode"] = proc.returncode


def _persist_chat_session(task_id, session_id):
    """Best-effort: record the resumable chat session id + last-active on the task.

    Mirrors task_dispatch._persist_session_id — persistence must never crash a
    turn that is already streaming, so swallow everything. Folds the
    chat_last_active stamp into the SAME read-modify-write as the session fields
    (I2): on the new-session path we already know we're rewriting frontmatter,
    so there's no reason to do a second full cycle just to touch last-active.
    """
    try:
        task_lib.update_task(task_id, {
            "claude_session_id": session_id,
            "session_origin": "human_chat",
            "chat_last_active": _now_iso(),
        })
    except Exception:
        pass


def _touch_last_active(task_id):
    """Best-effort: stamp chat_last_active after a turn completes."""
    try:
        task_lib.update_task(task_id, {"chat_last_active": _now_iso()})
    except Exception:
        pass


def run_turn(task_id, message):
    """Run one chat turn for a task: resolve session, run claude, persist, yield.

    Generator. Yields normalized event dicts (think / tool_step / text / result)
    in stream order. Each yielded non-result event is also appended to the task's
    sidecar transcript, stamped with this turn's run_id and origin="chat".

    Session resolution:
      - new session (no claude_session_id): send the full first-turn context
        prompt, mint a fresh session id, pass new_session=True. On the result
        event, persist the session id + session_origin="human_chat" so the next
        turn resumes.
      - resume: send the message as-is against the existing session id.

    The user message is persisted FIRST (its original text, not the context
    wrapper), tagged post_run — True once the agent has already had a first pass
    on this task (a session exists OR agent_status == "complete").
    """
    task = task_lib.read_task(task_id)
    fm = task["frontmatter"] or {}

    existing_sid = fm.get("claude_session_id")
    new_session = not existing_sid
    # post_run marks the user msg as a follow-up AFTER the agent's first pass.
    post_run = bool(fm.get("agent_status") == "complete" or existing_sid)

    run_id = uuid.uuid4().hex

    # Resolve the chat model the same way dispatch does (model > tier override).
    model = profile_lib.resolve_model(None, task_override=fm.get("model") or fm.get("tier"))

    if new_session:
        minted_sid = uuid.uuid4().hex
        sid = minted_sid
        sent_message = build_context_prompt(fm, message)
    else:
        minted_sid = None
        sid = existing_sid
        sent_message = message

    # 1) Persist the USER turn first — the operator's ORIGINAL message.
    chat_transcript.append_event(task_id, {
        "role": "user",
        "kind": "text",
        "text": message,
        "run_id": run_id,
        "origin": "chat",
        "post_run": post_run,
    })

    cmd = build_chat_cmd(
        session_id=sid,
        message=sent_message,
        model=model,
        new_session=new_session,
    )

    result_sid = None
    saw_result = False
    exit_holder = {}
    for line in _spawn(cmd, exit_holder):
        if not line or not line.strip():
            continue
        try:
            raw = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        for event in normalize(raw):
            kind = event.get("kind")

            # Drop blank thinking rows — never persist or yield empty think.
            if kind == "think" and not (event.get("text") or "").strip():
                continue

            if kind == "result":
                # Metadata: yield it for the UI, but do not append as a message.
                saw_result = True
                result_sid = event.get("session_id") or result_sid
                if new_session and result_sid:
                    _persist_chat_session(task_id, result_sid)
                yield event
                continue

            # think / tool_step / text: stamp, persist, yield.
            event["run_id"] = run_id
            event["origin"] = "chat"
            chat_transcript.append_event(task_id, event)
            yield event

    # New session: ensure the resumable id is on the task even if the result
    # carried no session_id (fall back to the minted id). This call also stamps
    # chat_last_active in the SAME write (I2), so the new-session path needs no
    # separate _touch_last_active.
    if new_session and not result_sid:
        _persist_chat_session(task_id, minted_sid)

    # I1: a clean run ALWAYS ends with a `result` event. If we never saw one —
    # claude died, was killed, or the stream ended abnormally (a non-zero exit
    # is a strong corroborating signal but not required) — surface a final,
    # recoverable error event so the SSE layer can emit an error frame and the
    # frontend can offer retry. Persist it too so a transcript reload shows it.
    if not saw_result:
        error_event = {
            "kind": "error",
            "role": "error",
            "text": "The assistant run ended unexpectedly. You can retry.",
            "run_id": run_id,
            "origin": "chat",
        }
        try:
            chat_transcript.append_event(task_id, dict(error_event))
        except Exception:
            pass
        yield error_event

    # Resume path: stamp last-active on its own (the new-session path already
    # folded this into _persist_chat_session, I2).
    if not new_session:
        _touch_last_active(task_id)
