import os, sys, shutil, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import profile_lib

def _tmp_profile(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "profile"))
    with open(os.path.join(root, "profile", "config.yaml"), "w") as f:
        f.write("models:\n  cost_posture: low\nserver:\n  port: 8743\n")
    return root

def test_autonomy_defaults_false_when_absent(tmp_path):
    root = _tmp_profile(tmp_path)
    assert profile_lib.autonomy_enforcement(root) is False

def test_set_autonomy_roundtrips_and_preserves_siblings(tmp_path):
    root = _tmp_profile(tmp_path)
    profile_lib.set_autonomy_enforcement(True, root=root)
    assert profile_lib.autonomy_enforcement(root) is True
    assert (profile_lib.config(root).get("models") or {}).get("cost_posture") == "low"
    profile_lib.set_autonomy_enforcement(False, root=root)
    assert profile_lib.autonomy_enforcement(root) is False
