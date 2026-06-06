import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_session_start_has_no_hardcoded_repo_path():
    text = (REPO / ".claude/hooks/session-start.sh").read_text()
    assert "/Users/jayjenkins/pm-os" not in text


def test_hooks_json_command_is_relative_or_resolved():
    data = json.loads((REPO / ".claude/hooks/hooks.json").read_text())
    cmd = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "/Users/jayjenkins/pm-os" not in cmd
