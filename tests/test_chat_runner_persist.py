"""Task 6 — chat_runner.run_turn persistence + session resolution.

Exercises the orchestration seam with REAL task_lib + chat_transcript against
the tmp `tasks_root` (the transcript path derives from task_lib.TASKS_DIR, which
the fixture redirects), and a monkeypatched `_spawn` that replays the committed
stream-json fixture. We avoid faking persistence so the test proves real
frontmatter + transcript writes, and only stub the subprocess seam + model
resolution (no real `claude`).
"""
import json
import subprocess
import time

import pytest

import chat_runner as cr
import task_lib
import chat_transcript


def _fixture_lines():
    """Raw stdout lines from the committed stream-json sample.

    The sample contains: a tool_use (Read), an EMPTY thinking block, a text
    block ("PONG-7"), and a result event — exactly the mix we need to assert
    on (tool_step persisted, empty-think skipped, text persisted, result
    yielded-not-persisted, session_id captured).
    """
    with open("tests/fixtures/stream_json_sample.jsonl") as f:
        return [line for line in f if line.strip()]


@pytest.fixture
def stub_spawn(monkeypatch):
    """Replay the fixture lines instead of spawning claude."""
    monkeypatch.setattr(cr, "_spawn", lambda cmd, exit_holder=None: iter(_fixture_lines()))


@pytest.fixture
def stub_model(monkeypatch):
    """Pin the resolved chat model so we never touch profile config."""
    monkeypatch.setattr(cr.profile_lib, "resolve_model", lambda *a, **k: "test-model")


def _make_task(**fm):
    """Create a task then patch in extra frontmatter, return its id."""
    task_id, _ = task_lib.create_task(title="Chat me", queue="agent")
    if fm:
        task_lib.update_task(task_id, fm)
    return task_id


def test_new_session_tags_post_run_false_and_persists_session(
    tasks_root, stub_spawn, stub_model, monkeypatch
):
    # Capture the argv handed to _spawn so we can assert new_session=True.
    seen = {}
    monkeypatch.setattr(cr, "_spawn", lambda cmd, exit_holder=None: seen.setdefault("cmd", cmd) or iter(_fixture_lines()))

    task_id = _make_task()  # brand-new: no session, agent_status None
    events = list(cr.run_turn(task_id, "ping"))

    # User turn persisted first, tagged as a fresh (pre-agent-run) message.
    persisted = chat_transcript.read_events(task_id)
    user = [e for e in persisted if e.get("role") == "user"]
    assert user and user[0]["text"] == "ping"
    assert user[0]["post_run"] is False
    assert user[0]["origin"] == "chat"
    assert user[0]["run_id"]

    # New session -> --session-id (not --resume) in the built argv.
    assert "--session-id" in seen["cmd"]
    assert "--resume" not in seen["cmd"]
    # The minted session id MUST be a canonical hyphenated UUID — `claude
    # --session-id` rejects a bare uuid4().hex ("Must be a valid UUID").
    # (Regression guard for a bug only live e2e caught; mocked _spawn never
    # validated the format.)
    import re as _re
    sid_arg = seen["cmd"][seen["cmd"].index("--session-id") + 1]
    assert _re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", sid_arg), sid_arg

    # Session id + origin written to frontmatter so future turns resume.
    fm = task_lib.read_task(task_id)["frontmatter"]
    assert fm["claude_session_id"]
    assert fm["session_origin"] == "human_chat"
    assert fm["chat_last_active"]


def test_resumed_session_tags_post_run_true(tasks_root, stub_spawn, stub_model, monkeypatch):
    seen = {}
    monkeypatch.setattr(cr, "_spawn", lambda cmd, exit_holder=None: seen.setdefault("cmd", cmd) or iter(_fixture_lines()))

    task_id = _make_task(claude_session_id="EXISTING-SID", session_origin="background_agent")
    list(cr.run_turn(task_id, "follow up"))

    persisted = chat_transcript.read_events(task_id)
    user = [e for e in persisted if e.get("role") == "user"]
    assert user[0]["post_run"] is True
    assert user[0]["origin"] == "chat"

    # Resume path uses --resume with the existing sid; sid is NOT overwritten.
    assert "--resume" in seen["cmd"]
    assert "EXISTING-SID" in seen["cmd"]
    fm = task_lib.read_task(task_id)["frontmatter"]
    assert fm["claude_session_id"] == "EXISTING-SID"


def test_post_run_true_when_agent_complete_without_session(
    tasks_root, stub_spawn, stub_model
):
    # agent_status complete but no session id -> still a follow-up.
    task_id = _make_task(agent_status="complete")
    list(cr.run_turn(task_id, "hi"))
    user = [e for e in chat_transcript.read_events(task_id) if e.get("role") == "user"]
    assert user[0]["post_run"] is True


def test_assistant_text_and_tool_step_persisted_and_yielded(
    tasks_root, stub_spawn, stub_model
):
    task_id = _make_task()
    events = list(cr.run_turn(task_id, "ping"))

    # Yielded events include a tool_step and a text row.
    yielded_kinds = [e.get("kind") for e in events]
    assert "tool_step" in yielded_kinds
    assert "text" in yielded_kinds
    assert "result" in yielded_kinds  # result is yielded for the UI to finalize

    # Persisted transcript has the assistant text + tool_step, stamped origin/run_id.
    persisted = chat_transcript.read_events(task_id)
    text_rows = [e for e in persisted if e.get("kind") == "text" and e.get("role") == "assistant"]
    tool_rows = [e for e in persisted if e.get("kind") == "tool_step"]
    assert text_rows and text_rows[0]["text"] == "PONG-7"
    assert tool_rows and tool_rows[0]["verb"] == "Read"
    for row in text_rows + tool_rows:
        assert row["origin"] == "chat"
        assert row["run_id"]


def test_empty_think_is_skipped(tasks_root, stub_spawn, stub_model):
    task_id = _make_task()
    events = list(cr.run_turn(task_id, "ping"))
    # The fixture's only thinking block is empty -> no think row anywhere.
    assert not [e for e in events if e.get("kind") == "think"]
    persisted = chat_transcript.read_events(task_id)
    assert not [e for e in persisted if e.get("kind") == "think"]


def test_result_not_persisted_as_assistant_message(tasks_root, stub_spawn, stub_model):
    task_id = _make_task()
    list(cr.run_turn(task_id, "ping"))
    persisted = chat_transcript.read_events(task_id)
    # result is metadata: yielded but never written to the transcript.
    assert not [e for e in persisted if e.get("kind") == "result"]


# ─── M3: regression coverage for C1 (lifecycle) and I1 (error event) ─────────

def test_spawn_kills_process_on_early_generator_close():
    """C1: closing the generator early must terminate the real subprocess.

    This is the test that proves the fix. We spawn a REAL short-lived process
    via `_spawn` — it emits one line then sleeps 30s — consume exactly ONE line,
    then close the generator (the GeneratorExit path the SSE consumer triggers
    on disconnect). The finally-block must SIGTERM→SIGKILL the process group, so
    the process must be dead shortly after. Without the lifecycle ownership the
    `sleep 30` would linger as an orphan.
    """
    # Bypass the real `claude` argv builder — feed _spawn a plain shell command.
    cmd = ["sh", "-c", "printf '%s\\n' '{\"type\":\"system\"}'; sleep 30"]
    holder = {}
    gen = cr._spawn(cmd, holder)

    first = next(gen)  # consume one line, leaving the process alive (sleeping)
    assert first.strip() == '{"type":"system"}'

    gen.close()  # GeneratorExit -> finally -> _kill_process_group

    # The process must die promptly (well under the 30s sleep). Poll briefly.
    deadline = time.time() + 5
    while time.time() < deadline:
        if holder.get("returncode") is not None:
            break
        time.sleep(0.05)
    assert holder.get("returncode") is not None, "process was not reaped (orphaned)"
    # A SIGTERM/SIGKILL of the group yields a negative (signal) return code.
    assert holder["returncode"] != 0


def test_no_result_event_yields_and_persists_error(
    tasks_root, stub_model, monkeypatch
):
    """I1: a stream that ends without a `result` event surfaces an error.

    Replay a couple of assistant lines but NO result event (claude died mid-run).
    run_turn must yield a final normalized error event AND persist it to the
    transcript so a reload shows the failure with a retry affordance.
    """
    no_result_lines = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "working on it"}]}}) + "\n",
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "x.md"}}]}}) + "\n",
        # no result event — stream just ends
    ]
    monkeypatch.setattr(
        cr, "_spawn",
        lambda cmd, exit_holder=None: iter(no_result_lines),
    )

    task_id = _make_task()
    events = list(cr.run_turn(task_id, "ping"))

    # The LAST yielded event is the recoverable error event.
    err = [e for e in events if e.get("kind") == "error"]
    assert err, "expected an error event when no result was seen"
    assert events[-1]["kind"] == "error"
    assert err[0]["role"] == "error"
    assert err[0]["origin"] == "chat"
    assert err[0]["run_id"]
    assert "retry" in err[0]["text"].lower()
    # No result event should have been yielded.
    assert not [e for e in events if e.get("kind") == "result"]

    # And it's persisted to the transcript (reload shows the error bubble).
    persisted = chat_transcript.read_events(task_id)
    persisted_err = [e for e in persisted if e.get("kind") == "error"]
    assert persisted_err and persisted_err[0]["role"] == "error"


# ─── Blocked-tool notice: the graceful dead-end ──────────────────────────────

def test_blocked_tool_yields_and_persists_notice(tasks_root, stub_model, monkeypatch):
    """When a tool is denied (headless can't prompt for approval), run_turn must
    surface a human `notice` that explains it and points to the board buttons —
    instead of leaving the user with the model's misleading "approve in terminal"
    narration. Driven off the result event's `permission_denials` (verified shape).
    """
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash",
             "input": {"command": "curl https://example.com/send"}}]}}) + "\n",
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True,
             "content": "This command requires approval"}]}}) + "\n",
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "This requires your approval to run."}]}}) + "\n",
        json.dumps({"type": "result", "subtype": "success", "session_id": "s",
                    "usage": {}, "permission_denials": [
                        {"tool_name": "Bash", "tool_use_id": "t1",
                         "tool_input": {"command": "curl https://example.com/send"}}]}) + "\n",
    ]
    monkeypatch.setattr(cr, "_spawn", lambda cmd, exit_holder=None: iter(lines))

    task_id = _make_task()
    events = list(cr.run_turn(task_id, "send it"))

    notice = [e for e in events if e.get("kind") == "notice"]
    assert notice, "expected a notice event when a tool was blocked"
    n = notice[0]
    assert n["role"] == "notice"
    assert n["origin"] == "chat" and n["run_id"]
    # The message steers the user to the task-detail action buttons.
    assert "button" in n["text"].lower()
    # The result event is still yielded for the UI to finalize.
    assert [e for e in events if e.get("kind") == "result"]

    # Persisted so a transcript reload shows the notice (parallels error path).
    persisted = chat_transcript.read_events(task_id)
    assert [e for e in persisted if e.get("kind") == "notice"]


def test_no_notice_when_nothing_blocked(tasks_root, stub_spawn, stub_model):
    """A clean turn (the committed fixture has no denials) yields no notice."""
    task_id = _make_task()
    events = list(cr.run_turn(task_id, "ping"))
    assert not [e for e in events if e.get("kind") == "notice"]
