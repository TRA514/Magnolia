"""Task-aware Claude chat panel runner.

Built incrementally across Tasks 4-7:
  - Task 4 (this file): pure builders — the `claude -p` argv and the
    de-personalized task-context system prompt for a NEW session's first turn.
  - Task 5: stream-json normalization.
  - Task 6: run_turn persistence (subprocess + file writes).
  - Task 7: locked-down tool allowlist (CHAT_ALLOWED_TOOLS).

The functions here are PURE: no subprocess, no file writes. Identity is read
ONLY through profile_lib (invariant #1) — never a hardcoded person literal.
"""
import profile_lib

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
