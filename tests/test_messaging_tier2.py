"""Task 3 — Tier-2 gating for the messaging family + the shipped config arming it."""
import os

import pytest

import adapters
from adapters.messaging import m365


def _root(tmp_path, yaml_text):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text(yaml_text)
    return str(tmp_path)


_DRAFT = {"channel": "email", "to": ["a@x.com"], "body": "y"}


def test_publish_none_when_provider_none(tmp_path):
    root = _root(tmp_path, "messaging:\n  provider: none\n")
    assert adapters.publish("messaging", _DRAFT, root=root) is None


def test_publish_needs_confirmation_when_unconfirmed(tmp_path):
    root = _root(tmp_path, "messaging:\n  provider: m365\n  m365:\n    confirmed: false\n")
    with pytest.raises(adapters.NeedsConfirmation):
        adapters.publish("messaging", _DRAFT, root=root)


def test_publish_delegates_to_provider_when_confirmed(tmp_path, monkeypatch):
    root = _root(tmp_path, "messaging:\n  provider: m365\n  m365:\n    confirmed: true\n")
    monkeypatch.setattr(m365, "publish", lambda draft, root=None: ("MSG-9", None))
    assert adapters.publish("messaging", _DRAFT, root=root) == ("MSG-9", None)


def test_shipped_integrations_yaml_arms_messaging_gate():
    """The engine ships messaging present-but-off, with the Tier-2 confirm armed
    (m365.confirmed: false) so enabling m365 can't silently send on first use.

    Reads the TRACKED template (profile.example/) DIRECTLY, not via profile_lib
    (which prefers a live, gitignored profile/) — the template is what a fresh
    clone actually ships."""
    from profile_lib import _yaml
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo, "profile.example", "integrations.yaml"), encoding="utf-8") as f:
        integ = _yaml.load(f) or {}
    assert "messaging" in integ, "messaging family missing from shipped integrations.yaml"
    msg = integ["messaging"]
    assert msg.get("provider") == "none"           # off by default (degrade gracefully)
    assert msg.get("m365", {}).get("confirmed") is False  # gate armed
