import pathlib, re
REPO = pathlib.Path(__file__).resolve().parent.parent
SKILL = REPO / ".claude/skills/workflow-magnolia-build/SKILL.md"


def test_loop_wires_the_new_subskills_and_gate():
    body = SKILL.read_text()
    # the new scoping step sits between brainstorm and writing-plans
    assert "meta-scope-extension" in body
    assert "meta-integration-discovery" in body
    # the portability gate is named among the gates the loop runs
    assert "portability_gate" in body
    # the seam-binding idea is explicit: subagents get a per-surface contract
    assert "build contract" in body.lower() or "build-contract" in body.lower()
    assert "contract" in body.lower()
    # preserved structure
    assert "brainstorming" in body
    assert "writing-plans" in body
    assert "subagent-driven-development" in body
    assert "finishing-a-development-branch" in body


def test_magnolia_build_denylist_clean():
    body = SKILL.read_text()
    for pat in (r"\bjay\b", r"board 1096", r"/Users/", r"~/pm-os"):
        assert not re.search(pat, body, re.IGNORECASE), f"leaks /{pat}/"
