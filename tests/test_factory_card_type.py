"""Phase 9 PR2 — factory_lib.validate_card_type: the registry-composition gate."""
import json
import pytest

# A registry that mirrors the real one's shape, with a known-good composed type.
_BASE = {
    "slotOrder": ["head", "title", "context", "signals", "body", "actions"],
    "signals": {"due": {"icon": "due", "variant": "due"},
                "cron": {"icon": "cron", "variant": "cron"}},
    "actions": {"mark_done": {"label": "Mark done", "handler": "quickDone", "primary": True},
                "keep": {"label": "Keep", "handler": "cardKeep", "primary": True},
                "undo": {"label": "Undo", "handler": "cardUndo"}},
    "cardTypes": {
        "task": {"signals": "auto", "actions": ["mark_done"], "body": None},
    },
}


def _write(tmp_path, reg):
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(reg))
    return str(p)


def test_validate_card_type_accepts_composed_entry(tmp_path):
    import factory_lib
    reg = json.loads(json.dumps(_BASE))
    reg["cardTypes"]["note"] = {"signals": [], "actions": ["mark_done"], "body": None}
    assert factory_lib.validate_card_type("note", registry_path=_write(tmp_path, reg)) == []


def test_validate_card_type_flags_unknown_signal(tmp_path):
    import factory_lib
    reg = json.loads(json.dumps(_BASE))
    reg["cardTypes"]["bad"] = {"signals": ["nonexistent"], "actions": ["mark_done"], "body": None}
    problems = factory_lib.validate_card_type("bad", registry_path=_write(tmp_path, reg))
    assert any("nonexistent" in p for p in problems)


def test_validate_card_type_flags_unknown_body_renderer(tmp_path):
    import factory_lib
    reg = json.loads(json.dumps(_BASE))
    reg["cardTypes"]["bad"] = {"signals": [], "actions": ["mark_done"], "body": "sparkly"}
    problems = factory_lib.validate_card_type("bad", registry_path=_write(tmp_path, reg))
    assert any("sparkly" in p for p in problems)


def test_validate_card_type_flags_missing_type(tmp_path):
    import factory_lib
    problems = factory_lib.validate_card_type("ghost", registry_path=_write(tmp_path, _BASE))
    assert any("ghost" in p and "not found" in p for p in problems)


def test_real_registry_passes_validate_card_type():
    """The live registry's existing 'task' type passes the gate unchanged."""
    import factory_lib
    assert factory_lib.validate_card_type("task") == []


def test_validate_card_type_reports_malformed_json(tmp_path):
    """The factory hand-edits JSON; a malformed registry returns a clean problem,
    not a raw traceback."""
    import factory_lib
    p = tmp_path / "registry.json"
    p.write_text('{ "cardTypes": { "note": }')  # invalid JSON
    problems = factory_lib.validate_card_type("note", registry_path=str(p))
    assert any("not valid JSON" in p for p in problems)
