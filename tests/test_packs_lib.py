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
