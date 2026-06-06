import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ["qmd-setup.sh", "qmd-nightly-update.sh", "run_task_server.sh"]


def test_no_hardcoded_pmos_paths():
    for name in SCRIPTS:
        text = (REPO / "scripts" / name).read_text()
        assert "/Users/jayjenkins/pm-os" not in text, f"{name}"
        assert '$HOME/pm-os' not in text and "$HOME/pm-os" not in text, f"{name}"
