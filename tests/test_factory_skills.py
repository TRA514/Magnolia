"""Phase 9 PR1 — structural checks on the factory skills (mirrors test_skill_frontmatter)."""
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent


def _read(rel):
    return (REPO / rel).read_text()


def test_meta_factory_core_exists_and_frontmatter():
    body = _read(".claude/skills/meta-factory-core/SKILL.md")
    assert body.startswith("---\n")
    fm = body.split("---\n", 2)[1]
    assert "name: meta-factory-core" in fm
    assert "Use when" in fm
    # documents the shared mechanism + the capture-to-profile rule
    assert "factory_lib" in body
    assert "receipt" in body.lower()
    assert "conventions" in body
    assert "set_integration_conventions" in body
    # forward pointers / deferral noted
    assert "meta-create-skill" in body          # reuses the TDD spine by reference
    assert "Tier" in body                        # Tier-2 forward note for adapters


def test_meta_create_worker_exists_and_frontmatter():
    body = _read(".claude/skills/meta-create-worker/SKILL.md")
    assert body.startswith("---\n")
    fm = body.split("---\n", 2)[1]
    assert "name: meta-create-worker" in fm
    assert "Use when" in fm
    # references the core + the gate + the helper + profile-read pattern
    assert "meta-factory-core" in body
    assert "factory_lib" in body
    assert "test_engine_no_jay" in body
    assert "profile/integrations.yaml" in body
    # embeds a worker skeleton with the dispatch placeholders
    assert "{task_id}" in body
    assert "{skills_catalog}" in body
    assert "tier:" in body


def test_meta_create_worker_skeleton_is_denylist_clean():
    """The embedded skeleton must carry no per-person/per-team literals."""
    import re
    body = _read(".claude/skills/meta-create-worker/SKILL.md")
    for pat in (r"\bjay\b", r"board 1096", r"/Users/", r"~/pm-os"):
        assert not re.search(pat, body, re.IGNORECASE), f"skeleton leaks /{pat}/"
