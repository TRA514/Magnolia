import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(ROOT, ".claude", "skills", "workflow-jira-home", "SKILL.md")

def test_jira_home_no_person_or_board_literals():
    text = open(F, encoding="utf-8").read()
    assert "712020:aeec48b7-3829-433b-9125-c8c2a4c84e6f" not in text
    assert not re.search(r"\bJay\b", text)
    assert "board 1096" not in text and "board `1096`" not in text
    assert "~/pm-os" not in text

def test_jira_home_keeps_vantaca_field_mechanics():
    text = open(F, encoding="utf-8").read()
    assert "Vantaca" in text
    assert "profile/integrations.yaml" in text          # assignee/board now sourced from profile
    assert "customfield_10300" in text                   # shared custom-field IDs preserved
    assert "<!-- JIRA_DRAFT -->" in text                 # draft format preserved
    assert "Regression Defect" in text and "Unit" in text
