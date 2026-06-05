import os
import sys
import textwrap
import pytest

# Make scripts/ importable as top-level modules (matches how scripts import each other)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


@pytest.fixture
def profile_root(tmp_path):
    """A temp PM-OS root containing a fully populated profile/ dir."""
    prof = tmp_path / "profile"
    (prof / "voice").mkdir(parents=True)
    (prof / "profile.yaml").write_text(textwrap.dedent("""\
        display_name: "Test User"
        email: "test@example.com"
        company: "Acme"
        persona: "pm"
        timezone: "America/New_York"
    """))
    (prof / "integrations.yaml").write_text(textwrap.dedent("""\
        project_management:
          provider: "jira"
          jira:
            cloud_id: "acme.atlassian.net"
            project_key: "ACM"
            component_id: "999"
            auto_label: "team_lane"
            default_assignee: "acct-123"
        transcript:
          provider: "granola"
        calendar:
          provider: "m365"
    """))
    (prof / "config.yaml").write_text(textwrap.dedent("""\
        models:
          judge: "claude-opus-4-8"
          parser: "claude-haiku-4-5"
          cost_posture: "balanced"
        active_skill_packs: ["core", "pm"]
    """))
    (prof / "voice" / "teams.md").write_text("# Teams voice\nTight, lowercase ok.\n")
    (prof / "voice" / "email.md").write_text("# Email voice\nWarm, polished.\n")
    return str(tmp_path)
