import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import task_extract_meetings as tem  # noqa: E402


def test_resolve_relative_path(tmp_path, monkeypatch):
    monkeypatch.setattr(tem, "PM_OS_DIR", tmp_path)
    f = tmp_path / "datasets" / "meetings" / "x.md"
    f.parent.mkdir(parents=True)
    f.write_text("hi")
    assert tem.resolve_path("datasets/meetings/x.md") == f.resolve()

def test_resolve_absolute_posix_path(tmp_path, monkeypatch):
    monkeypatch.setattr(tem, "PM_OS_DIR", tmp_path)
    f = tmp_path / "a.md"; f.write_text("hi")
    assert tem.resolve_path(str(f)) == f.resolve()

def test_resolve_windows_drive_path_not_doubled(tmp_path, monkeypatch):
    # The bug: bash treated C:\... as relative and prepended PM_OS_DIR.
    # pathlib must treat a drive-absolute path as absolute (no doubling).
    monkeypatch.setattr(tem, "PM_OS_DIR", tmp_path)
    p = tem.resolve_path("C:/Users/Josh/x.md")
    assert str(p).replace("\\", "/").endswith("Users/Josh/x.md")
    assert "datasets" not in str(p)  # PM_OS_DIR was NOT prepended

def test_processed_idempotency(tmp_path, monkeypatch):
    monkeypatch.setattr(tem, "PM_OS_DIR", tmp_path)
    pf = tmp_path / "datasets" / "tasks" / "_processed-meetings.txt"
    pf.parent.mkdir(parents=True)
    monkeypatch.setattr(tem, "PROCESSED_FILE", pf)
    assert tem.is_processed("datasets/meetings/x.md") is False
    tem.mark_processed("datasets/meetings/x.md")
    assert tem.is_processed("datasets/meetings/x.md") is True
    tem.mark_processed("datasets/meetings/x.md")  # second call no-op
    assert pf.read_text().count("x.md") == 1
