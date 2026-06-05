import doctor


def test_probe_which_ok(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda n: "/usr/bin/" + n)
    cap = doctor.probe_which("pandoc")
    assert cap["kind"] == "local"
    assert cap["status"] == "ok"


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
