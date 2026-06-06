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
