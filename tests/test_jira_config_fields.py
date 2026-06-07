import os
from ruamel.yaml import YAML

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "profile.example", "integrations.yaml")


def test_template_jira_block_has_board_and_product_area():
    """The tracked schema template must carry board_id + product_area so prompts
    can read the team's Jira target from profile instead of hardcoding it. Pinned
    to profile.example/ (the git artifact) so a local profile/ can't mask a
    template regression."""
    with open(TEMPLATE, encoding="utf-8") as f:
        data = YAML(typ="safe").load(f)
    jira = data["project_management"]["jira"]
    assert "board_id" in jira
    assert "product_area" in jira
