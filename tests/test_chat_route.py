"""Tests for the SSE chat route + per-session run-lock in task_server.py.

SSE + sockets are awkward to unit-test end-to-end, so these tests focus on the
LOCK + GUARD logic and request-validation behavior — where bugs hide. We drive
the handler with a fake handler object rather than a real server socket.
"""

import io
import json

import pytest

import task_server
import task_lib
import chat_runner


# ─── Fake handler ──────────────────────────────────────────────────────────────

class FakeHandler:
    """Minimal stand-in for a BaseHTTPRequestHandler.

    Captures status, headers, and body writes; provides headers/rfile so
    _read_request_body works.
    """

    def __init__(self, body=None):
        raw = json.dumps(body or {}).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None
        self.sent_headers = {}
        # Ordered list of (key, value) so we can assert on duplicates — the
        # dict above collapses repeats and would hide a double-sent header.
        self.header_list = []
        self.ended = False

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.sent_headers[key] = value
        self.header_list.append((key, value))

    def end_headers(self):
        # Mirror the real handler's overridden end_headers(), which injects the
        # CORS header into EVERY response before the base class finalizes them.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.ended = True

    def written(self):
        return self.wfile.getvalue().decode("utf-8")


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_runs():
    """Reset the in-process chat-run set around every test."""
    task_server._CHAT_RUNS.clear()
    yield
    task_server._CHAT_RUNS.clear()


# ─── Lock primitives ───────────────────────────────────────────────────────────

def test_acquire_release_lock():
    assert task_server._try_acquire_chat_run("TASK-1") is True
    # Second acquire while held → rejected.
    assert task_server._try_acquire_chat_run("TASK-1") is False
    task_server._release_chat_run("TASK-1")
    # After release, acquirable again.
    assert task_server._try_acquire_chat_run("TASK-1") is True


# ─── handle_chat validation ─────────────────────────────────────────────────────

def test_handle_chat_rejects_empty_message(monkeypatch):
    called = {"run": False}

    def fake_run_turn(task_id, message):
        called["run"] = True
        yield {"kind": "text", "text": "x"}

    monkeypatch.setattr(chat_runner, "run_turn", fake_run_turn)

    handler = FakeHandler(body={"message": "   "})
    task_server.handle_chat(handler, "TASK-1")

    assert handler.status == 400
    assert called["run"] is False
    # Lock must not be acquired on a validation failure.
    assert "TASK-1" not in task_server._CHAT_RUNS


def test_handle_chat_409_when_chat_already_running(monkeypatch):
    called = {"run": False}

    def fake_run_turn(task_id, message):
        called["run"] = True
        yield {"kind": "text", "text": "x"}

    monkeypatch.setattr(chat_runner, "run_turn", fake_run_turn)
    monkeypatch.setattr(
        task_lib, "read_task",
        lambda tid: {"frontmatter": {"agent_status": "complete"}, "body": ""},
    )

    # Pre-occupy the lock as if another request is mid-run.
    task_server._CHAT_RUNS.add("TASK-1")

    handler = FakeHandler(body={"message": "hello"})
    task_server.handle_chat(handler, "TASK-1")

    assert handler.status == 409
    assert called["run"] is False
    # The pre-existing lock must remain held (we didn't acquire/release it).
    assert "TASK-1" in task_server._CHAT_RUNS


def test_handle_chat_409_when_agent_running(monkeypatch):
    called = {"run": False}

    def fake_run_turn(task_id, message):
        called["run"] = True
        yield {"kind": "text", "text": "x"}

    monkeypatch.setattr(chat_runner, "run_turn", fake_run_turn)
    monkeypatch.setattr(
        task_lib, "read_task",
        lambda tid: {"frontmatter": {"agent_status": "running"}, "body": ""},
    )

    handler = FakeHandler(body={"message": "hello"})
    task_server.handle_chat(handler, "TASK-1")

    assert handler.status == 409
    assert called["run"] is False
    # No lock acquired when the background agent is busy.
    assert "TASK-1" not in task_server._CHAT_RUNS


def test_handle_chat_404_when_task_missing(monkeypatch):
    def fake_read_task(tid):
        raise FileNotFoundError(tid)

    monkeypatch.setattr(task_lib, "read_task", fake_read_task)

    handler = FakeHandler(body={"message": "hello"})
    task_server.handle_chat(handler, "TASK-9999")

    assert handler.status == 404
    assert "TASK-9999" not in task_server._CHAT_RUNS


def test_handle_chat_streams_events(monkeypatch):
    events = [
        {"kind": "think", "text": "pondering"},
        {"kind": "text", "text": "done"},
    ]

    def fake_run_turn(task_id, message):
        for ev in events:
            yield ev

    monkeypatch.setattr(chat_runner, "run_turn", fake_run_turn)
    monkeypatch.setattr(
        task_lib, "read_task",
        lambda tid: {"frontmatter": {"agent_status": "complete"}, "body": ""},
    )

    handler = FakeHandler(body={"message": "hello"})
    task_server.handle_chat(handler, "TASK-1")

    out = handler.written()
    assert handler.status == 200
    assert handler.sent_headers.get("Content-Type") == "text/event-stream"
    # Two data frames + a terminal done event.
    assert out.count("data: ") >= 2
    assert "pondering" in out
    assert "done" in out
    assert "event: done" in out
    # Lock released after the stream completes.
    assert "TASK-1" not in task_server._CHAT_RUNS


def test_handle_chat_releases_lock_on_disconnect(monkeypatch):
    """A client disconnect (write raising) must not crash and must release the lock."""

    def fake_run_turn(task_id, message):
        yield {"kind": "text", "text": "first"}
        yield {"kind": "text", "text": "second"}

    monkeypatch.setattr(chat_runner, "run_turn", fake_run_turn)
    monkeypatch.setattr(
        task_lib, "read_task",
        lambda tid: {"frontmatter": {"agent_status": "complete"}, "body": ""},
    )

    class BrokenWfile:
        def write(self, data):
            raise BrokenPipeError("client gone")

        def flush(self):
            pass

    handler = FakeHandler(body={"message": "hello"})
    handler.wfile = BrokenWfile()

    # Must not raise.
    task_server.handle_chat(handler, "TASK-1")

    # Lock released despite the disconnect.
    assert "TASK-1" not in task_server._CHAT_RUNS


def test_handle_chat_emits_single_cors_header(monkeypatch):
    """The SSE response must carry EXACTLY ONE Access-Control-Allow-Origin
    header — _sse_begin must NOT send it (end_headers injects it)."""

    def fake_run_turn(task_id, message):
        yield {"kind": "text", "text": "hi"}

    monkeypatch.setattr(chat_runner, "run_turn", fake_run_turn)
    monkeypatch.setattr(
        task_lib, "read_task",
        lambda tid: {"frontmatter": {"agent_status": "complete"}, "body": ""},
    )

    handler = FakeHandler(body={"message": "hello"})
    task_server.handle_chat(handler, "TASK-1")

    cors = [
        (k, v) for (k, v) in handler.header_list
        if k == "Access-Control-Allow-Origin"
    ]
    assert len(cors) == 1, f"expected exactly one CORS header, got {cors}"
    assert cors[0] == ("Access-Control-Allow-Origin", "*")


def test_handle_chat_emits_error_frame_on_mid_stream_failure(monkeypatch):
    """A non-disconnect exception after the stream began must NOT escape, must
    emit a terminal error frame, and must release the lock."""

    def fake_run_turn(task_id, message):
        yield {"kind": "text", "text": "partial"}
        raise RuntimeError("boom mid-stream")

    monkeypatch.setattr(chat_runner, "run_turn", fake_run_turn)
    monkeypatch.setattr(
        task_lib, "read_task",
        lambda tid: {"frontmatter": {"agent_status": "complete"}, "body": ""},
    )

    handler = FakeHandler(body={"message": "hello"})

    # (a) Must not raise.
    task_server.handle_chat(handler, "TASK-1")

    out = handler.written()
    # The first (normal) event still made it out.
    assert "partial" in out
    # (b) A terminal error frame was written.
    assert '"kind": "error"' in out or '"kind":"error"' in out
    # (c) Lock released afterward.
    assert "TASK-1" not in task_server._CHAT_RUNS
