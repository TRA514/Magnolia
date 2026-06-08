"""Task 1 — the mgc Graph seam for sending email + Teams messages.

Pure payload builders are asserted exactly; the impure mgc runner is exercised
only via dry-run and the missing-mgc guard. No real `mgc` is ever invoked.
Mirrors the calendar precedent (create_calendar_event.py).
"""
import json
import send_message_graph as g


# ── Pure payload builders ────────────────────────────────────────────────────

def test_email_payload_is_graph_sendmail_shape():
    p = g.build_email_payload(["a@x.com", "b@y.com"], "Subject here", "Hello body")
    assert p["saveToSentItems"] is True
    msg = p["message"]
    assert msg["subject"] == "Subject here"
    assert msg["body"] == {"contentType": "Text", "content": "Hello body"}
    assert msg["toRecipients"] == [
        {"emailAddress": {"address": "a@x.com"}},
        {"emailAddress": {"address": "b@y.com"}},
    ]


def test_email_payload_html_flag():
    p = g.build_email_payload(["a@x.com"], "S", "<b>hi</b>", html=True)
    assert p["message"]["body"]["contentType"] == "HTML"


def test_chat_create_payload_one_on_one():
    p = g.build_chat_create_payload("me@co.com", ["them@co.com"])
    assert p["chatType"] == "oneOnOne"
    binds = [m["user@odata.bind"] for m in p["members"]]
    assert "https://graph.microsoft.com/v1.0/users('me@co.com')" in binds
    assert "https://graph.microsoft.com/v1.0/users('them@co.com')" in binds
    # aadUserConversationMember with an owner role is required by Graph
    assert all(m["@odata.type"] == "#microsoft.graph.aadUserConversationMember"
               for m in p["members"])
    assert all("owner" in m["roles"] for m in p["members"])


def test_chat_create_payload_group_when_multiple_recipients():
    p = g.build_chat_create_payload("me@co.com", ["a@co.com", "b@co.com"])
    assert p["chatType"] == "group"
    assert len(p["members"]) == 3


def test_chat_message_payload_shape():
    assert g.build_chat_message_payload("ping") == {
        "body": {"contentType": "text", "content": "ping"}}
    assert g.build_chat_message_payload("<i>x</i>", html=True)["body"]["contentType"] == "html"


# ── Impure send paths: dry-run + missing-mgc guard ───────────────────────────

def test_send_email_dry_run_returns_payload_without_shelling():
    out = g.send_email(["a@x.com"], "S", "B", dry_run=True)
    assert out["dry_run"] is True
    assert out["payload"]["message"]["subject"] == "S"


def test_send_teams_dry_run_returns_payloads_without_shelling():
    out = g.send_teams("me@co.com", ["them@co.com"], "hi", dry_run=True)
    assert out["dry_run"] is True
    assert out["chat"]["chatType"] == "oneOnOne"
    assert out["message"]["body"]["content"] == "hi"


def test_missing_mgc_raises_actionable_error(monkeypatch):
    monkeypatch.setattr(g.shutil, "which", lambda _: None)
    try:
        g._run_mgc(["users", "send-mail", "post", "--body", "{}"])
        assert False, "expected RuntimeError when mgc is absent"
    except RuntimeError as e:
        assert "mgc" in str(e).lower()
        assert "login" in str(e).lower()  # points at the auth/login remedy


def test_unified_scopes_cover_email_and_teams_and_calendar():
    s = g.MGC_SCOPES
    assert "Mail.Send" in s
    assert "Chat.ReadWrite" in s
    assert "Calendars.ReadWrite" in s
