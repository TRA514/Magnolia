import json
import profile_lib


def test_capabilities_empty_when_absent(tmp_path):
    (tmp_path / "profile").mkdir()
    caps = profile_lib.read_capabilities(root=str(tmp_path))
    assert caps == {"schema_version": 1, "capabilities": {}}


def test_write_then_read_roundtrips(tmp_path):
    (tmp_path / "profile").mkdir()
    data = {
        "schema_version": 1,
        "platform": "darwin",
        "capabilities": {"qmd": {"kind": "local", "status": "ok"}},
    }
    profile_lib.write_capabilities(data, root=str(tmp_path))
    back = profile_lib.read_capabilities(root=str(tmp_path))
    assert back["capabilities"]["qmd"]["status"] == "ok"
    # written to the live profile dir
    assert (tmp_path / "profile" / "capabilities.json").is_file()


def test_write_is_atomic_no_partial_file(tmp_path):
    (tmp_path / "profile").mkdir()
    profile_lib.write_capabilities({"schema_version": 1, "capabilities": {}}, root=str(tmp_path))
    # no leftover temp file
    leftovers = [p.name for p in (tmp_path / "profile").iterdir() if p.name.startswith(".capabilities")]
    assert leftovers == []
