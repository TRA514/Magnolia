import importlib


def test_jira_constants_come_from_profile(profile_root, monkeypatch):
    import profile_lib
    # Force jira_publish to resolve config against the temp profile.
    monkeypatch.setattr(profile_lib, "PM_OS_DIR", profile_root)
    import jira_publish
    importlib.reload(jira_publish)
    assert jira_publish.JIRA_CLOUD_ID == "acme.atlassian.net"
    assert jira_publish.JIRA_PROJECT_KEY == "ACM"
    assert jira_publish.JIRA_COMPONENT_ID == "999"
    assert jira_publish.JIRA_DEFAULT_ASSIGNEE == "acct-123"
