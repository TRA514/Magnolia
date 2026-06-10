"""GET/PUT /api/tasks/{id}/output — read & write a task's .md artifact for the
inline editor. Mirrors test_quick_add_route's _FakeHandler pattern. The output
file lives under a temp PM_OS_DIR (monkeypatched) so writes never touch the real tree."""
import io
import json
import os
import pytest


class _FakeHandler:
    def __init__(self, body=None):
        self._body = json.dumps(body).encode("utf-8") if body is not None else b""
        self.headers = {"Content-Length": str(len(self._body))}
        self.status = None
        self._chunks = []

    @property
    def rfile(self):
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
    """task_server with task_lib + PM_OS_DIR pointed at the temp tree."""
    import task_server
    monkeypatch.setattr(task_server, "PM_OS_DIR", tasks_root)
    return task_server


def _seed_task_with_output(tasks_root, rel_path, content):
    """Create an agent task whose agent_output points at rel_path, and write that file."""
    import task_lib
    tid, _ = task_lib.create_task("Competitive landscape brief", queue="agent", domain="product")
    task_lib.update_task(tid, changes={"agent_output": rel_path})
    abspath = os.path.join(tasks_root, rel_path)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, "w", encoding="utf-8") as f:
        f.write(content)
    return tid


def test_resolve_output_path_rejects_traversal(srv):
    assert srv._resolve_output_path("../../etc/passwd.md") is None
    assert srv._resolve_output_path("product/agent-output/note.txt") is None
    assert srv._resolve_output_path("") is None
    got = srv._resolve_output_path("product/agent-output/x.md")
    assert got is not None and got.endswith("product/agent-output/x.md")


def test_get_output_returns_content(srv, tasks_root):
    tid = _seed_task_with_output(tasks_root, "product/agent-output/comp.md",
                                 "# Competitive Landscape\n\nFour vendors dominate.\n")
    h = _FakeHandler()
    srv.handle_get_output(h, tid)
    assert h.status == 200
    resp = h.json()
    assert resp["format"] == "markdown"
    assert resp["path"] == "product/agent-output/comp.md"
    assert "Four vendors dominate." in resp["content"]


def test_get_output_404_when_no_agent_output(srv, tasks_root):
    import task_lib
    tid, _ = task_lib.create_task("No output yet", queue="agent")
    h = _FakeHandler()
    srv.handle_get_output(h, tid)
    assert h.status == 404


def test_get_output_404_when_not_markdown(srv, tasks_root):
    import task_lib
    tid, _ = task_lib.create_task("Link output", queue="agent")
    task_lib.update_task(tid, changes={"agent_output": "https://example.com/x"})
    h = _FakeHandler()
    srv.handle_get_output(h, tid)
    assert h.status == 404


def test_put_output_roundtrips_to_disk(srv, tasks_root):
    tid = _seed_task_with_output(tasks_root, "product/agent-output/comp.md", "# Old\n")
    h = _FakeHandler({"content": "# New title\n\nEdited body.\n"})
    srv.handle_save_output(h, tid)
    assert h.status == 200
    resp = h.json()
    assert resp["ok"] is True
    assert "savedAt" in resp
    import os
    with open(os.path.join(tasks_root, "product/agent-output/comp.md"), encoding="utf-8") as f:
        assert f.read() == "# New title\n\nEdited body.\n"


def test_put_output_400_when_content_missing(srv, tasks_root):
    tid = _seed_task_with_output(tasks_root, "product/agent-output/comp.md", "# Old\n")
    h = _FakeHandler({})
    srv.handle_save_output(h, tid)
    assert h.status == 400


def test_put_output_404_when_not_markdown(srv, tasks_root):
    import task_lib
    tid, _ = task_lib.create_task("Link output", queue="agent")
    task_lib.update_task(tid, changes={"agent_output": "https://example.com/x"})
    h = _FakeHandler({"content": "nope"})
    srv.handle_save_output(h, tid)
    assert h.status == 404


def test_output_routes_registered_before_generic_get():
    import re
    src = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "task_server.py"),
               encoding="utf-8").read()
    out_idx = src.index('/api/tasks/([^/]+)/output$')
    generic_idx = src.index('^/api/tasks/([^/]+)$')
    assert out_idx < generic_idx, "output route must be matched before the generic task GET"
