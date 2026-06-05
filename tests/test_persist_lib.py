import persist_lib


def test_render_plist_has_no_hardcoded_user_and_uses_repo_path():
    plist = persist_lib.render_launchagent(
        label="com.pm-os.task-server",
        program=["/usr/bin/python3", "/repo/scripts/task_server.py"],
        working_dir="/repo",
        log_path="/repo/logs/task-server.log",
    )
    assert "/Users/jayjenkins" not in plist
    assert "<key>RunAtLoad</key>" in plist and "<true/>" in plist
    assert "<key>KeepAlive</key>" in plist
    assert "/repo/scripts/task_server.py" in plist
    assert "com.pm-os.task-server" in plist


def test_render_scheduled_task_at_logon():
    ps = persist_lib.render_scheduled_task(
        name="MagnoliaTaskServer",
        program="C:\\Python\\python.exe",
        args="C:\\repo\\scripts\\task_server.py",
        working_dir="C:\\repo",
    )
    assert "Register-ScheduledTask" in ps
    assert "-AtLogOn" in ps
    assert "MagnoliaTaskServer" in ps
    # per-user, no admin: interactive token, not SYSTEM
    assert "-RunLevel Highest" not in ps
