import ast
import pathlib

PORTED = ["otter_sync.py", "otter_auth.py", "otter_classify.py", "otter_rename.py"]
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def test_no_hardcoded_user_paths():
    for name in PORTED:
        text = (SCRIPTS / name).read_text()
        assert "/Users/jayjenkins" not in text, f"{name} still has a hardcoded user path"


def test_ported_files_parse():
    for name in PORTED:
        ast.parse((SCRIPTS / name).read_text())  # raises SyntaxError if broken
