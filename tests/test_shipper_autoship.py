import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import shipper


def _patch_create(monkeypatch, state):
    def fake_create(title, **kw):
        state["created"] = {"title": title, **kw}
        return ("R-1", "/tmp/R-1.md")
    monkeypatch.setattr(shipper.task_lib, "create_task", fake_create)
    monkeypatch.setattr(shipper.task_lib, "update_task",
                        lambda tid, **kw: state.setdefault("updated", kw))
    monkeypatch.setattr(shipper.task_lib, "read_task",
                        lambda tid: {"frontmatter": {}, "body": ""})


def test_autoship_send_ok_emits_receipt(monkeypatch):
    state = {}
    _patch_create(monkeypatch, state)
    monkeypatch.setattr(shipper, "_message_draft_from_task",
                        lambda tid: {"channel": "teams", "to_display": "Alice"})
    monkeypatch.setattr(shipper, "_attempt_send_message",
                        lambda tid, draft: ("ok", ("mid", None)))
    assert shipper.autoship("T-1", "send-message") == "shipped"
    assert state["created"]["card_type"] == "receipt"
    assert state["updated"]["changes"]["receipt_kind"] == "autoship"


def test_autoship_needs_confirm_emits_confirm_card(monkeypatch):
    calls = {}
    monkeypatch.setattr(shipper, "_message_draft_from_task",
                        lambda tid: {"channel": "email", "to_display": "Bob"})
    monkeypatch.setattr(shipper, "_attempt_send_message",
                        lambda tid, draft: ("needs_confirm", None))
    monkeypatch.setattr(shipper, "_emit_confirm_card",
                        lambda family, src: calls.setdefault("confirm", (family, src)))
    assert shipper.autoship("T-1", "send-message") == "needs_confirm"
    assert calls["confirm"] == ("messaging", "T-1")


def test_autoship_already_sent_is_shipped(monkeypatch):
    monkeypatch.setattr(shipper, "_message_draft_from_task",
                        lambda tid: {"channel": "teams", "to_display": "X"})
    monkeypatch.setattr(shipper, "_attempt_send_message",
                        lambda tid, draft: ("already_sent", None))
    assert shipper.autoship("T-1", "send-message") == "shipped"


def test_autoship_error_status(monkeypatch):
    monkeypatch.setattr(shipper, "_message_draft_from_task",
                        lambda tid: {"channel": "teams", "to_display": "X"})
    monkeypatch.setattr(shipper, "_attempt_send_message",
                        lambda tid, draft: ("error", (502, "boom")))
    assert shipper.autoship("T-1", "send-message") == "error"


def test_autoship_unknown_type_errors():
    assert shipper.autoship("T-1", "prd") == "error"
