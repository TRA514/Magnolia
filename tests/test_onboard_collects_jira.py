import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(ROOT, ".claude", "skills", "meta-onboard", "SKILL.md")

def test_onboard_collects_per_team_jira_fields():
    text = open(F, encoding="utf-8").read().lower()
    for field in ("cloud_id", "project_key", "board_id", "default_assignee", "component_id", "product_area"):
        assert field in text, f"onboarding must collect {field}"
    assert "project_management.jira" in text  # writes to the correct nested block
