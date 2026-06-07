import os
import textwrap
import packs_lib


def _write_packs(root, body):
    claude = os.path.join(root, ".claude")
    os.makedirs(claude, exist_ok=True)
    with open(os.path.join(claude, "packs.yaml"), "w") as f:
        f.write(textwrap.dedent(body))


def test_load_packs_parses_manifest(tmp_path):
    _write_packs(str(tmp_path), """\
        core:
          label: "Core"
          description: "Baseline."
          skills: [task-create, context-search]
        pm:
          label: "Product Management"
          description: "PRDs."
          skills: [workflow-prd-creation]
    """)
    packs = packs_lib.load_packs(root=str(tmp_path))
    assert set(packs) == {"core", "pm"}
    assert packs["core"]["skills"] == ["task-create", "context-search"]


def test_load_packs_missing_file_returns_empty(tmp_path):
    assert packs_lib.load_packs(root=str(tmp_path)) == {}


def test_pack_catalog_shape(tmp_path):
    _write_packs(str(tmp_path), """\
        core:
          label: "Core"
          description: "Baseline."
          skills: []
        pm:
          label: "Product Management"
          description: "PRDs."
          skills: []
    """)
    cat = packs_lib.pack_catalog(root=str(tmp_path))
    assert {"id", "label", "description"} <= set(cat[0])
    assert {c["id"] for c in cat} == {"core", "pm"}


def test_pack_catalog_missing_file_returns_empty_list(tmp_path):
    assert packs_lib.pack_catalog(root=str(tmp_path)) == []


def test_load_packs_malformed_yaml_returns_empty(tmp_path):
    _write_packs(str(tmp_path), """\
        ":
          - [unclosed
    """)
    assert packs_lib.load_packs(root=str(tmp_path)) == {}


def test_load_packs_non_dict_root_returns_empty(tmp_path):
    _write_packs(str(tmp_path), """\
        - a
        - b
    """)
    assert packs_lib.load_packs(root=str(tmp_path)) == {}


def test_load_packs_skips_non_dict_pack_and_filters_skills(tmp_path):
    _write_packs(str(tmp_path), """\
        scalar_pack: "just a string"
        pm:
          label: "Product Management"
          description: "PRDs."
          skills: [workflow-prd-creation, 42, context-search, null]
    """)
    packs = packs_lib.load_packs(root=str(tmp_path))
    assert "scalar_pack" not in packs
    assert packs["pm"]["skills"] == ["workflow-prd-creation", "context-search"]


def test_load_packs_label_defaults_to_titlecase(tmp_path):
    _write_packs(str(tmp_path), """\
        pm:
          skills: [workflow-prd-creation]
    """)
    packs = packs_lib.load_packs(root=str(tmp_path))
    assert packs["pm"]["label"] == "Pm"
    assert packs["pm"]["description"] == ""


def test_active_skill_folders_unions_core_and_active(tmp_path):
    packs = {
        "core": {"label": "", "description": "", "skills": ["task-create"]},
        "pm":   {"label": "", "description": "", "skills": ["workflow-prd-creation"]},
        "eng":  {"label": "", "description": "", "skills": ["workflow-jira-home"]},
    }
    on_disk = {"task-create", "workflow-prd-creation", "workflow-jira-home"}
    got = packs_lib.active_skill_folders(["pm"], packs=packs, on_disk=on_disk)
    assert got == {"task-create", "workflow-prd-creation"}   # core + pm, not eng


def test_active_skill_folders_core_always_on(tmp_path):
    packs = {"core": {"label": "", "description": "", "skills": ["task-create"]},
             "pm": {"label": "", "description": "", "skills": ["workflow-prd-creation"]}}
    on_disk = {"task-create", "workflow-prd-creation"}
    got = packs_lib.active_skill_folders([], packs=packs, on_disk=on_disk)
    assert "task-create" in got and "workflow-prd-creation" not in got


def test_active_skill_folders_unlisted_stays_visible(tmp_path):
    packs = {"core": {"label": "", "description": "", "skills": ["task-create"]},
             "pm": {"label": "", "description": "", "skills": ["workflow-prd-creation"]}}
    on_disk = {"task-create", "workflow-prd-creation", "quality-content-style"}
    got = packs_lib.active_skill_folders(["pm"], packs=packs, on_disk=on_disk)
    assert "quality-content-style" in got   # in no pack -> always available


def test_active_skill_folders_no_manifest_returns_all(tmp_path):
    on_disk = {"a", "b", "c"}
    assert packs_lib.active_skill_folders(["pm"], packs={}, on_disk=on_disk) == on_disk


def test_on_disk_skill_folders_detects_skill_manifests(tmp_path):
    skills = tmp_path / ".claude" / "skills"
    (skills / "foo").mkdir(parents=True)
    (skills / "foo" / "SKILL.md").write_text("---\nname: foo\n---\n")
    (skills / "bar").mkdir(parents=True)
    (skills / "bar" / "skill.md").write_text("---\nname: bar\n---\n")
    (skills / "empty").mkdir(parents=True)   # no manifest -> ignored
    got = packs_lib._on_disk_skill_folders(root=str(tmp_path))
    assert got == {"foo", "bar"}


def test_on_disk_skill_folders_missing_dir_returns_empty(tmp_path):
    assert packs_lib._on_disk_skill_folders(root=str(tmp_path)) == set()
