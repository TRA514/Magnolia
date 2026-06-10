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
    t = task_lib.create_task("Competitive landscape brief", queue="agent", domain="product")
    task_lib.update_task(t["id"], changes={"agent_output": rel_path})
    abspath = os.path.join(tasks_root, rel_path)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, "w", encoding="utf-8") as f:
        f.write(content)
    return t["id"]


def test_resolve_output_path_rejects_traversal(srv):
    assert srv._resolve_output_path("../../etc/passwd.md") is None
    assert srv._resolve_output_path("product/agent-output/note.txt") is None
    assert srv._resolve_output_path("") is None
    got = srv._resolve_output_path("product/agent-output/x.md")
    assert got is not None and got.endswith("product/agent-output/x.md")
