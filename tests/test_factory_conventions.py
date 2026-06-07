"""Phase 9 PR1 — free-form team conventions captured into profile, never the artifact."""
import os

import profile_lib


def _profile(tmp_path):
    """A throwaway live profile dir with a minimal integrations.yaml."""
    pdir = tmp_path / "profile"
    pdir.mkdir()
    (pdir / "integrations.yaml").write_text(
        "project_management:\n"
        '  provider: "jira"\n'
        "  jira:\n"
        '    project_key: "ABC"\n'
        '    conventions: ""\n'
    )
    return str(tmp_path)


def test_set_and_read_jira_conventions(tmp_path):
    root = _profile(tmp_path)
    profile_lib.set_integration_conventions(
        "project_management", "Always set Sprint; titles prefixed [Area].",
        provider="jira", root=root)
    cfg = profile_lib.jira_config(root=root)
    assert cfg["conventions"] == "Always set Sprint; titles prefixed [Area]."


def test_set_conventions_preserves_siblings(tmp_path):
    root = _profile(tmp_path)
    profile_lib.set_integration_conventions(
        "project_management", "note", provider="jira", root=root)
    cfg = profile_lib.jira_config(root=root)
    assert cfg["project_key"] == "ABC"  # sibling field untouched


def test_set_conventions_without_provider_writes_at_category_level(tmp_path):
    """provider=None writes <category>.conventions directly (the documented dual mode)."""
    root = _profile(tmp_path)
    profile_lib.set_integration_conventions(
        "project_management", "category-level note", root=root)
    cat = profile_lib.integration("project_management", root=root)
    assert cat["conventions"] == "category-level note"
    assert cat["jira"]["project_key"] == "ABC"  # provider sub-block untouched


def test_example_integrations_has_conventions_field():
    """The template documents the slot so users/onboarding can see it."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(repo, "profile.example", "integrations.yaml")).read()
    assert "conventions:" in text
