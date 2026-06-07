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
