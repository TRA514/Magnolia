import os

import doctor


def test_probe_which_ok(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda n: "/usr/bin/" + n)
    cap = doctor.probe_which("pandoc")
    assert cap["kind"] == "local"
    assert cap["status"] == "ok"
    assert "remedy" not in cap


def test_probe_which_missing(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda n: None)
    cap = doctor.probe_which("qmd", remedy="brew install qmd")
    assert cap["status"] == "missing"
    assert cap["remedy"] == "brew install qmd"


def test_probe_python_deps_all_present(monkeypatch):
    monkeypatch.setattr(doctor.importlib.util, "find_spec", lambda n: object())
    cap = doctor.probe_python_deps(["ruamel.yaml", "otterai"])
    assert cap["status"] == "ok"


def test_probe_python_deps_missing(monkeypatch):
    monkeypatch.setattr(doctor.importlib.util, "find_spec",
                        lambda n: None if n == "otterai" else object())
    cap = doctor.probe_python_deps(["ruamel.yaml", "otterai"])
    assert cap["status"] == "degraded"
    assert "otterai" in cap["missing"]


def test_probe_python_deps_handles_find_spec_raising(monkeypatch):
    def fake_find_spec(n):
        if n == "ruamel.yaml":
            raise ModuleNotFoundError("No module named 'ruamel'")
        return object()
    monkeypatch.setattr(doctor.importlib.util, "find_spec", fake_find_spec)
    cap = doctor.probe_python_deps(["ruamel.yaml", "json"])
    assert cap["status"] == "degraded"
    assert "ruamel.yaml" in cap["missing"]


def test_probe_server_down(monkeypatch):
    # nothing listening on this port
    cap = doctor.probe_server(port=59999)
    assert cap["kind"] == "service"
    assert cap["status"] == "down"
    assert cap["port"] == 59999


def test_probe_transcript_not_expected(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: none\n")
    cap = doctor.probe_transcript(root=str(tmp_path))
    assert cap["status"] == "not_expected"


def test_probe_transcript_needs_reauth_when_no_session(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: otter\n")
    cap = doctor.probe_transcript(root=str(tmp_path))
    assert cap["provider"] == "otter"
    assert cap["status"] == "needs_reauth"  # no session.json present


def test_detect_assembles_capabilities(tmp_path, monkeypatch):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text(
        "project_management:\n  provider: jira\n"
        "transcript:\n  provider: none\n"
    )
    (tmp_path / "profile" / "config.yaml").write_text("server:\n  port: 59998\n")
    monkeypatch.setattr(doctor.shutil, "which", lambda n: None)
    monkeypatch.setattr(doctor.importlib.util, "find_spec", lambda n: object())
    caps = doctor.detect(root=str(tmp_path))
    assert caps["schema_version"] == 1
    assert "platform" in caps
    c = caps["capabilities"]
    assert c["qmd"]["status"] == "missing"
    assert c["msgraph_cli"]["required"] is False
    assert c["server"]["status"] == "down"
    # remote MCP seeded as expected from integrations.yaml
    assert c["jira"]["kind"] == "remote" and c["jira"]["expected"] is True
    # detect() persisted the file
    assert (tmp_path / "profile" / "capabilities.json").is_file()
