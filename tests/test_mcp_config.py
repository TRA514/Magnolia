import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_mcp_json_is_valid_and_portable():
    """`.claude/mcp.json` must carry no per-operator absolute paths.

    cwd is not a supported .mcp.json field (Claude Code passes the project root
    to the server via CLAUDE_PROJECT_DIR and defaults the working dir to the
    launch dir), and the command must be PATH-resolved — the engine already
    probes qmd via shutil.which("qmd"). A hardcoded /Users/... or
    /opt/homebrew path would break any teammate who clones the repo.
    """
    data = json.loads((REPO / ".claude/mcp.json").read_text())
    qmd = data["mcpServers"]["qmd"]
    assert qmd["command"] == "qmd"          # PATH-resolved, not an absolute brew path
    assert "cwd" not in qmd                  # unsupported + was a production pointer

    blob = (REPO / ".claude/mcp.json").read_text()
    assert "/Users/jayjenkins" not in blob
    assert "/opt/homebrew" not in blob
