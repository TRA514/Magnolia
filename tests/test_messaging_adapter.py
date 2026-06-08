"""Task 2 — the messaging adapter family (m365 provider).

The provider dispatches by channel to the mgc seam (send_message_graph); here we
mock that seam so no real mgc runs, and assert dispatch + the (id, url) contract.
"""
import pytest

from adapters.messaging import m365
from adapters.messaging._contract import NotConfigured
import send_message_graph as graph


def test_is_configured_tracks_mgc_presence(monkeypatch):
    monkeypatch.setattr(m365.shutil, "which", lambda _: "/usr/bin/mgc")
    assert m365.is_configured() is True
    monkeypatch.setattr(m365.shutil, "which", lambda _: None)
    assert m365.is_configured() is False


def test_publish_email_dispatches_to_sendmail(monkeypatch):
    monkeypatch.setattr(m365.shutil, "which", lambda _: "/usr/bin/mgc")
    seen = {}
    monkeypatch.setattr(graph, "send_email",
                        lambda to, subj, body, **k: seen.update(to=to, subj=subj, body=body) or {"status": "sent"})
    draft = {"channel": "email", "to": ["a@x.com"], "subject": "Hi", "body": "Hello"}
    msg_id, url = m365.publish(draft)
    assert seen == {"to": ["a@x.com"], "subj": "Hi", "body": "Hello"}
    assert msg_id and url is None


def test_publish_teams_resolves_me_and_dispatches(monkeypatch):
    monkeypatch.setattr(m365.shutil, "which", lambda _: "/usr/bin/mgc")
    monkeypatch.setattr(m365, "_resolve_me_upn", lambda: "me@co.com")
    seen = {}
    monkeypatch.setattr(graph, "send_teams",
                        lambda me, to, body, **k: seen.update(me=me, to=to, body=body) or {"message_id": "MSG-1"})
    draft = {"channel": "teams", "to": ["them@co.com"], "body": "ping"}
    msg_id, url = m365.publish(draft)
    assert seen == {"me": "me@co.com", "to": ["them@co.com"], "body": "ping"}
    assert msg_id == "MSG-1" and url is None


def test_publish_unknown_channel_raises(monkeypatch):
    monkeypatch.setattr(m365.shutil, "which", lambda _: "/usr/bin/mgc")
    with pytest.raises(NotConfigured):
        m365.publish({"channel": "carrier-pigeon", "to": ["x"], "body": "y"})


def test_publish_without_mgc_raises_not_configured(monkeypatch):
    monkeypatch.setattr(m365.shutil, "which", lambda _: None)
    with pytest.raises(NotConfigured):
        m365.publish({"channel": "email", "to": ["a@x.com"], "body": "y"})
