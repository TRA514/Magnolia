import pytest
import task_lib


def test_validate_rejects_non_editable_field():
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("id", "X")
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("queue", "agent")
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("created", "2026-01-01")


def test_validate_priority_enum():
    assert task_lib.validate_field_edit("priority", "high") == "high"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("priority", "urgent")


def test_validate_status_excludes_done_and_cancelled():
    assert task_lib.validate_field_edit("status", "in-progress") == "in-progress"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("status", "done")
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("status", "cancelled")


def test_validate_domain_enum():
    assert task_lib.validate_field_edit("domain", "product") == "product"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("domain", "nonsense")


def test_validate_date_format():
    assert task_lib.validate_field_edit("due", "2026-07-01") == "2026-07-01"
    assert task_lib.validate_field_edit("due", "") == ""
    assert task_lib.validate_field_edit("waiting_expected", "2026-07-01") == "2026-07-01"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("due", "07/01/2026")


def test_validate_text_strips_and_bounds():
    assert task_lib.validate_field_edit("waiting_on", "  Acme Corp  ") == "Acme Corp"
    assert task_lib.validate_field_edit("title", "Ship it") == "Ship it"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("title", "x" * 201)


def test_validate_tags_coerces_list():
    assert task_lib.validate_field_edit("tags", ["a", " b ", ""]) == ["a", "b"]
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("tags", "a,b")


import io
import json
import task_server


class FakeHandler:
    """Minimal stand-in for BaseHTTPRequestHandler for unit-testing handlers."""
    def __init__(self, body_dict):
        raw = json.dumps(body_dict).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None
    def send_response(self, status): self.status = status
    def send_header(self, *a): pass
    def end_headers(self): pass
    def response(self):
        return json.loads(self.wfile.getvalue().decode("utf-8"))


def test_update_field_persists_priority(tasks_root):
    tid, _ = task_lib.create_task("probe", queue="human", priority="medium")
    h = FakeHandler({"field": "priority", "value": "high"})
    task_server.handle_update_field(h, tid)
    assert h.status == 200
    assert task_lib.read_task(tid)["frontmatter"]["priority"] == "high"


def test_update_field_rejects_protected_field(tasks_root):
    tid, _ = task_lib.create_task("probe", queue="human")
    h = FakeHandler({"field": "id", "value": "HACK"})
    task_server.handle_update_field(h, tid)
    assert h.status == 400
    assert task_lib.read_task(tid)["frontmatter"]["id"] == tid


def test_update_field_rejects_bad_enum(tasks_root):
    tid, _ = task_lib.create_task("probe", queue="human")
    h = FakeHandler({"field": "priority", "value": "urgent"})
    task_server.handle_update_field(h, tid)
    assert h.status == 400


def test_update_field_unknown_task_404(tasks_root):
    h = FakeHandler({"field": "title", "value": "x"})
    task_server.handle_update_field(h, "TASK-9999")
    assert h.status == 404


def test_update_field_waiting_on_text(tasks_root):
    tid, _ = task_lib.create_task("probe", queue="waiting")
    h = FakeHandler({"field": "waiting_on", "value": "Acme Corp"})
    task_server.handle_update_field(h, tid)
    assert h.status == 200
    assert task_lib.read_task(tid)["frontmatter"]["waiting_on"] == "Acme Corp"
