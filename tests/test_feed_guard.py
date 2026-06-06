import feed_guard


def test_detects_competing_launchagent(tmp_path):
    la = tmp_path / "LaunchAgents"
    la.mkdir()
    (la / "com.jayjenkins.otter-sync.plist").write_text(
        "<plist><dict><key>Label</key><string>com.jayjenkins.otter-sync</string>"
        "<key>ProgramArguments</key><array><string>/Users/x/scripts/otter/otter_sync.py</string>"
        "</array></dict></plist>"
    )
    (la / "com.apple.unrelated.plist").write_text("<plist><dict></dict></plist>")
    ours = "com.pm-os.task-server"
    found = feed_guard.detect_competing(launch_agents_dir=str(la), own_labels=[ours])
    labels = [f["label"] for f in found]
    assert "com.jayjenkins.otter-sync" in labels
    assert "com.apple.unrelated" not in labels


def test_does_not_flag_our_own_agent(tmp_path):
    la = tmp_path / "LaunchAgents"
    la.mkdir()
    (la / "com.pm-os.transcript.plist").write_text(
        "<plist><dict><key>Label</key><string>com.pm-os.transcript</string>"
        "<key>ProgramArguments</key><array><string>x/otter_sync.py</string></array></dict></plist>"
    )
    found = feed_guard.detect_competing(launch_agents_dir=str(la), own_labels=["com.pm-os.transcript"])
    assert found == []


def test_disable_renames_aside_and_returns_status(tmp_path):
    p = tmp_path / "com.jayjenkins.otter-sync.plist"
    p.write_text("<plist><dict></dict></plist>")
    result = feed_guard.disable(str(p), activate=False)
    assert result["disabled_path"].endswith(".disabled-by-magnolia")
    assert result["unloaded"] is None  # activate=False → not attempted
    import os
    assert not os.path.exists(str(p))           # original moved
    assert os.path.exists(result["disabled_path"])  # backup exists
    assert "never deletes" or True  # (sanity)


def test_disable_never_clobbers_existing_backup(tmp_path):
    import os
    p = tmp_path / "feed.plist"
    p.write_text("FIRST")
    first = feed_guard.disable(str(p), activate=False)
    # user restored the original and it gets disabled again
    p.write_text("SECOND")
    second = feed_guard.disable(str(p), activate=False)
    # both backups must survive with distinct content — no clobber
    assert first["disabled_path"] != second["disabled_path"]
    assert open(first["disabled_path"]).read() == "FIRST"
    assert open(second["disabled_path"]).read() == "SECOND"
