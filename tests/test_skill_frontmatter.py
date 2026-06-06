import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent


def _frontmatter(path):
    text = path.read_text()
    assert text.startswith("---\n"), f"{path} missing YAML frontmatter"
    fm = text.split("---\n", 2)[1]
    return fm


def test_workflow_doctor_frontmatter():
    fm = _frontmatter(REPO / ".claude/skills/workflow-doctor/SKILL.md")
    assert "name: workflow-doctor" in fm
    assert "description:" in fm
    assert "Use when" in fm  # trigger-led description


def test_meta_onboard_frontmatter_and_persona():
    path = REPO / ".claude/skills/meta-onboard/SKILL.md"
    fm = _frontmatter(path)
    assert "name: meta-onboard" in fm
    body = path.read_text()
    assert "Magnolia" in body          # the host persona is specified
    assert "doctor.py detect" in body  # step 4 wiring
    assert "server_lib" in body        # step 5 wiring
