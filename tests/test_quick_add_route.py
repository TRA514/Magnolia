"""Quick Add route — POST /api/tasks/quick-add: NL-parse a line of free text,
create the task, optionally dispatch. The parser (call to the claude CLI) and the
dispatcher (subprocess.Popen) are monkeypatched; we assert on the created task
and the returned "face". Mirrors test_send_message_route's _FakeHandler pattern."""
import json

import pytest


class _FakeHandler:
    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")
        self.headers = {"Content-Length": str(len(self._body))}
        self.status = None
        self._chunks = []

    @property
    def rfile(self):
        import io
        return io.BytesIO(self._body)

    def send_response(self, s): self.status = s
    def send_header(self, *a): pass
    def end_headers(self): pass
    @property
    def wfile(self): return self
    def write(self, b): self._chunks.append(b)
    def json(self): return json.loads(b"".join(self._chunks).decode("utf-8"))


@pytest.fixture
def srv(tasks_root, monkeypatch):
    """task_server with task_lib on the temp tree and the parser/dispatcher stubbed."""
    import task_server
    # No real claude CLI call — return a deterministic parse.
    monkeypatch.setattr(task_server, "_parse_task_fields", lambda text: {
        "title": "Pull last week's Pendo numbers and draft the metrics brief",
        "queue": "agent", "priority": "medium", "domain": "metrics",
        "description": "Metrics brief from Pendo adoption data.", "tags": ["pendo"],
    })
    return task_server


def test_quick_add_creates_and_dispatches_agent_task(srv, monkeypatch):
    import task_lib
    spawned = []
    monkeypatch.setattr(srv, "_spawn_task_dispatch", lambda tid: spawned.append(tid))

    h = _FakeHandler({"text": "pull pendo numbers and draft the brief", "auto_dispatch": True})
    srv.handle_quick_add(h)

    assert h.status == 200
    resp = h.json()
    assert resp["ok"] is True
    tid = resp["task"]["id"]
    assert spawned == [tid]                       # dispatched once, for this task

    fm = task_lib.read_task(tid)["frontmatter"]
    assert fm["queue"] == "agent"
    assert fm["domain"] == "metrics"
    assert fm["creator"] == "human"
    assert "quick-add" in fm["tags"]              # tagged for provenance
    assert fm["title"].startswith("Pull last week's Pendo")


def test_quick_add_no_dispatch_when_flag_false(srv, monkeypatch):
    spawned = []
    monkeypatch.setattr(srv, "_spawn_task_dispatch", lambda tid: spawned.append(tid))

    h = _FakeHandler({"text": "draft the brief", "auto_dispatch": False})
    srv.handle_quick_add(h)

    assert h.status == 200
    assert spawned == []                          # left in the queue for the human


def test_quick_add_does_not_dispatch_human_lane(srv, monkeypatch):
    # A parse that lands in a non-agent lane must not be auto-dispatched.
    monkeypatch.setattr(srv, "_parse_task_fields", lambda text: {
        "title": "Call the vendor about the contract", "queue": "human",
        "priority": "high", "domain": "ops",
    })
    spawned = []
    monkeypatch.setattr(srv, "_spawn_task_dispatch", lambda tid: spawned.append(tid))

    h = _FakeHandler({"text": "call the vendor", "auto_dispatch": True})
    srv.handle_quick_add(h)

    assert h.status == 200
    assert spawned == []
    assert h.json()["task"]["queue"] == "human"


def test_quick_add_rejects_empty_text(srv):
    h = _FakeHandler({"text": "   ", "auto_dispatch": True})
    srv.handle_quick_add(h)
    assert h.status == 400
    assert "error" in h.json()


def test_quick_add_parse_failure_is_500(srv, monkeypatch):
    def _boom(text): raise RuntimeError("claude CLI failed")
    monkeypatch.setattr(srv, "_parse_task_fields", _boom)
    h = _FakeHandler({"text": "anything", "auto_dispatch": True})
    srv.handle_quick_add(h)
    assert h.status == 500
    assert "error" in h.json()


def test_quick_add_falls_back_to_text_title_when_parser_omits_it(srv, monkeypatch):
    monkeypatch.setattr(srv, "_parse_task_fields", lambda text: {"queue": "agent"})
    monkeypatch.setattr(srv, "_spawn_task_dispatch", lambda tid: None)
    h = _FakeHandler({"text": "a bare line with no parsed title", "auto_dispatch": True})
    srv.handle_quick_add(h)
    assert h.status == 200
    assert h.json()["task"]["title"] == "a bare line with no parsed title"
