import platform_lib


def test_os_kind_known(monkeypatch):
    monkeypatch.setattr(platform_lib.platform, "system", lambda: "Darwin")
    assert platform_lib.os_kind() == "darwin"
    monkeypatch.setattr(platform_lib.platform, "system", lambda: "Windows")
    assert platform_lib.os_kind() == "windows"
    monkeypatch.setattr(platform_lib.platform, "system", lambda: "Linux")
    assert platform_lib.os_kind() == "linux"


def test_open_url_cmd_per_os(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "darwin")
    assert platform_lib.open_url_cmd("http://x") == ["open", "http://x"]
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "windows")
    assert platform_lib.open_url_cmd("http://x") == ["cmd", "/c", "start", "", "http://x"]
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "linux")
    assert platform_lib.open_url_cmd("http://x") == ["xdg-open", "http://x"]


def test_package_install_cmd_per_os(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "darwin")
    assert platform_lib.package_install_cmd("pandoc") == ["brew", "install", "pandoc"]
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "linux")
    assert platform_lib.package_install_cmd("pandoc") == ["brew", "install", "pandoc"]
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "windows")
    assert platform_lib.package_install_cmd("pandoc") == ["winget", "install", "--id", "pandoc", "-e"]
    # documented no-equivalent package → None (unsupported-on-this-OS signal, not a broken command)
    assert platform_lib.package_install_cmd("fswatch") is None


def test_launch_agents_dir(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "darwin")
    assert platform_lib.launch_agents_dir().endswith("/Library/LaunchAgents")
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "windows")
    assert platform_lib.launch_agents_dir() is None  # Task Scheduler has no dir


def test_headless_claude_env_strips_claude_vars():
    base = {"CLAUDE_CODE_X": "1", "CMUX_CLAUDE_Y": "1", "PATH": "/usr/bin", "HOME": "/h"}
    env = platform_lib.headless_claude_env(base=base)
    assert not any(k.startswith(("CLAUDE", "CMUX_CLAUDE")) for k in env)
    assert "HOME" in env


def test_headless_claude_env_keeps_windows_path_untouched(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "windows")
    base = {"PATH": r"C:\Windows;C:\tools"}
    env = platform_lib.headless_claude_env(base=base)
    assert env["PATH"] == r"C:\Windows;C:\tools"


def test_resolve_claude_uses_which(monkeypatch):
    monkeypatch.setattr(platform_lib.shutil, "which", lambda n, path=None: "/found/claude")
    assert platform_lib.resolve_claude() == "/found/claude"


def test_resolve_claude_falls_back_to_bare_name(monkeypatch):
    monkeypatch.setattr(platform_lib.shutil, "which", lambda n, path=None: None)
    monkeypatch.setattr(platform_lib.os.path, "isfile", lambda p: False)
    assert platform_lib.resolve_claude() == "claude"


def test_process_group_kwargs_per_os(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "windows")
    assert "creationflags" in platform_lib.process_group_kwargs()
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "darwin")
    assert platform_lib.process_group_kwargs() == {"start_new_session": True}
