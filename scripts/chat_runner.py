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
import subprocess
import uuid

import profile_lib
import task_lib
import chat_transcript

# Repo root — the cwd `claude` runs in, mirroring task_dispatch.PM_OS_DIR.
PM_OS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A conservative read-only default for now. Task 7 replaces this with the
# locked-down allowlist constant CHAT_ALLOWED_TOOLS.
DEFAULT_ALLOWED_TOOLS = "Read,Grep,Glob"


def build_chat_cmd(session_id, message, model, new_session=False, allowed_tools=None):
    """Build the `claude` argv for a chat turn.

    The prompt MUST stay the first positional arg: --allowedTools is variadic
    and would otherwise swallow a trailing prompt (verified in the CLI spike,
    see docs/plans/notes/claude-cli-verification.md). --allowedTools therefore
    goes LAST so nothing trails it.

    new_session=True  -> start a fresh session with --session-id <id>.
    new_session=False -> resume an existing session with --resume <id>.
    """
    tools = allowed_tools or DEFAULT_ALLOWED_TOOLS
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


def _spawn(cmd):
    """Spawn `claude` and yield its stdout lines.

    Thin, monkeypatchable seam so run_turn's logic is testable without invoking
    the real CLI. stderr is discarded; we iterate stdout line-by-line so the SSE
    route can stream events as they arrive.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=PM_OS_DIR,
        env=_chat_env(),
    )
    yield from proc.stdout
    proc.wait()


def _persist_chat_session(task_id, session_id):
    """Best-effort: record the resumable chat session id on the task.

    Mirrors task_dispatch._persist_session_id — persistence must never crash a
    turn that is already streaming, so swallow everything.
    """
    try:
        task_lib.update_task(task_id, {
            "claude_session_id": session_id,
            "session_origin": "human_chat",
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
    for line in _spawn(cmd):
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
    # carried no session_id (fall back to the minted id).
    if new_session and not result_sid:
        _persist_chat_session(task_id, minted_sid)

    _touch_last_active(task_id)
