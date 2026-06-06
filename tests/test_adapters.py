import pytest
import adapters
from adapters.project_management import jira as jira_adapter


def test_loader_returns_jira_module_for_jira_provider(profile_root):
    mod = adapters.get("project_management", root=profile_root)
    assert mod is jira_adapter


def test_loader_returns_none_when_provider_none(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text(
        "project_management:\n  provider: none\n")
    assert adapters.get("project_management", root=str(tmp_path)) is None


def test_jira_is_configured_true_for_populated_profile(profile_root):
    assert jira_adapter.is_configured(root=profile_root) is True


def test_jira_publish_delegates_to_publish_to_jira(profile_root, monkeypatch):
    captured = {}
    def fake_publish(draft):
        captured["draft"] = draft
        return ("ACM-1", "https://acme.atlassian.net/browse/ACM-1")
    import jira_publish
    monkeypatch.setattr(jira_publish, "publish_to_jira", fake_publish)
    key, url = jira_adapter.publish({"summary": "x", "type": "Bug"}, root=profile_root)
    assert key == "ACM-1"
    assert captured["draft"]["summary"] == "x"
