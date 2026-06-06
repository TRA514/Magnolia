import transcript_sync


def test_dispatch_none_is_noop(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: none\n")
    result = transcript_sync.sync(root=str(tmp_path))
    assert result["status"] == "skipped"
    assert result["provider"] == "none"


def test_dispatch_granola_not_yet(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: granola\n")
    result = transcript_sync.sync(root=str(tmp_path))
    assert result["status"] == "unsupported"  # Phase 3


def test_dispatch_otter_calls_runner(tmp_path, monkeypatch):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: otter\n")
    called = {}
    monkeypatch.setattr(transcript_sync, "_run_otter", lambda root: called.setdefault("ran", True))
    transcript_sync.sync(root=str(tmp_path))
    assert called.get("ran") is True
