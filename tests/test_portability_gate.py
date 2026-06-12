import sys, os, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import portability_gate as pg

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_flags_direct_sh_invocation(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text('subprocess.Popen(["bash", "x.sh"])\n', encoding="utf-8")
    offenders = pg.scan([str(f)])
    assert any("shell script" in o or ".sh" in o for o in offenders)


def test_flags_os_name_branch_outside_seam(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("if os.name == 'nt':\n    pass\n", encoding="utf-8")
    offenders = pg.scan([str(f)])
    assert any("os.name" in o or "platform branch" in o for o in offenders)


def test_flags_start_new_session(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("Popen(cmd, start_new_session=True)\n", encoding="utf-8")
    offenders = pg.scan([str(f)])
    assert any("start_new_session" in o for o in offenders)


def test_clean_file_passes(tmp_path):
    f = tmp_path / "good.py"
    f.write_text('msg = "9 AM - 5 PM"\nPopen([sys.executable, "x.py"], **process_group_kwargs())\n',
                 encoding="utf-8")
    assert pg.scan([str(f)]) == []


def test_repo_is_green():
    """The gate MUST pass on the real repo or it is not shippable."""
    assert pg.validate() == [], "portability offenders on main:\n" + "\n".join(pg.validate())
