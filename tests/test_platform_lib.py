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
