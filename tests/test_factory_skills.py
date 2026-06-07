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


def test_factory_skills_in_core_pack():
    from ruamel.yaml import YAML
    packs = YAML(typ="safe").load((REPO / ".claude/packs.yaml").read_text())
    core = packs["core"]["skills"]
    assert "meta-factory-core" in core
    assert "meta-create-worker" in core


def test_meta_create_card_type_exists_and_frontmatter():
    body = _read(".claude/skills/meta-create-card-type/SKILL.md")
    assert body.startswith("---\n")
    fm = body.split("---\n", 2)[1]
    assert "name: meta-create-card-type" in fm
    assert "Use when" in fm
    assert "meta-factory-core" in body
    assert "factory_lib" in body
    assert "card_schema" in body
    assert "registry.json" in body
    # composition-only is explicit + the out-of-scope refusal is stated
    assert "composition" in body.lower()
    assert "zero new render code" in body or "no JS" in body or "no new JS" in body


def test_meta_create_card_type_lists_only_existing_pieces():
    """The skill must enumerate the real signals/actions/body-renderers so the
    agent composes from them and doesn't invent new ones."""
    body = _read(".claude/skills/meta-create-card-type/SKILL.md")
    for renderer in ("diff", "preview", "agreement"):
        assert renderer in body
    for action in ("mark_done", "accept", "keep", "undo", "graduate"):
        assert action in body
