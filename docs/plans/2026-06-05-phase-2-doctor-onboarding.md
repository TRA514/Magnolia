# Phase 2: Doctor + Onboarding — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task, with a TWO-STAGE review after each task (spec-compliance reviewer, then code-quality reviewer).

**Goal:** Make a freshly-cloned Magnolia install itself — a Python Doctor that detects tools/auth and writes `profile/capabilities.json`, a cross-platform server spin-up + reboot-persistence layer, a ported Otter transcript feed Magnolia owns, and a conversational onboarding flow driven by the "Magnolia" concierge persona.

**Architecture:** Deterministic, cron-safe Python (`doctor.py`, `platform_lib.py`, `server_lib.py`, `persist_lib.py`, the ported Otter module, `feed_guard.py`) does detection and side-effects; two markdown skills (`workflow-doctor`, `meta-onboard`) drive Claude's adaptive remediation and onboarding conversation. Everything reads identity/integration facts through Phase 1's `profile_lib`. macOS is run-validated; Windows branches are written behind a mocked OS seam and are design-validated only.

**Tech Stack:** Python 3.14 (Homebrew, PEP-668 — install deps with `python3 -m pip install --break-system-packages`), `ruamel.yaml`, `pytest` (run as `python3 -m pytest`, no venv), stdlib `http.server`/`socket`/`shutil`/`subprocess`, Playwright + `otterai-api` for the ported feed, plain shell/JSON/Markdown.

**Working directory:** `/Users/jayjenkins/dev/pm-os-team` ONLY. NEVER read from, write to, or operate on `/Users/jayjenkins/pm-os` (production). The production task server runs on 8742 — do not touch it. Reading `~/scripts/otter/*` (outside the production pm-os dir) is explicitly authorized for the port.

**Every commit message ends with:**
```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

**Subagent preamble (include in every dispatched task):** "cd into `/Users/jayjenkins/dev/pm-os-team` at the start of every bash command. Work only in this repo. Never touch `/Users/jayjenkins/pm-os`. Run tests with `python3 -m pytest`. Reuse the `profile_root` fixture in `tests/conftest.py`."

---

## Execution waves (dependency order)

1. **Foundations** — profile/config schema (Tasks 1–4)
2. **OS seam** — `platform_lib` (Tasks 5–6)
3. **Doctor** — detection + CLI (Tasks 7–9)
4. **Server + persistence** (Tasks 10–14)
5. **Transcript feed + guard** (Tasks 15–17)
6. **De-personalization** (Tasks 18–20)
7. **Skills + cron + E2E** (Tasks 21–24)

---

## Task 1: Add the `onboarding` task domain

**Why:** Onboarding steps are reified as tasks with `domain: onboarding`, but that value isn't in the allowed lists, so `create_task`/`create_job` would reject them.

**Files:**
- Modify: `scripts/task_lib.py:43`
- Modify: `scripts/cron_lib.py:29`
- Test: `tests/test_domains.py`

**Step 1: Write the failing test**

Create `tests/test_domains.py`:
```python
import task_lib
import cron_lib


def test_onboarding_is_a_valid_domain():
    assert "onboarding" in task_lib.DOMAINS
    assert "onboarding" in cron_lib.VALID_DOMAINS
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_domains.py -v`
Expected: FAIL (assertion error).

**Step 3: Add the domain**

In `scripts/task_lib.py:43` change:
```python
DOMAINS = ["product", "strategy", "marketing", "recruiting", "metrics", "learning", "ops"]
```
to:
```python
DOMAINS = ["product", "strategy", "marketing", "recruiting", "metrics", "learning", "ops", "onboarding"]
```
In `scripts/cron_lib.py:29` make the identical change to `VALID_DOMAINS`.

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_domains.py -v`
Expected: 1 passed.

**Step 5: Commit**

```bash
git add scripts/task_lib.py scripts/cron_lib.py tests/test_domains.py
git commit -m "feat(tasks): add 'onboarding' task domain"
```

---

## Task 2: Configurable server port

**Why:** A teammate adopting an existing install must not collide with another PM-OS on 8742. The port moves to `config.yaml`; `profile_lib` exposes it; `task_server.py` reads it.

**Files:**
- Modify: `profile.example/config.yaml`
- Modify: `scripts/profile_lib.py`
- Modify: `scripts/task_server.py:53`
- Test: `tests/test_profile_lib.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_profile_lib.py`:
```python
def test_server_port_default(tmp_path):
    (tmp_path / "profile").mkdir()
    assert profile_lib.server_port(root=str(tmp_path)) == 8742


def test_server_port_from_config(profile_root):
    # profile_root fixture has no server: block → default
    assert profile_lib.server_port(root=profile_root) == 8742
```

Then extend the `profile_root` fixture in `tests/conftest.py` so `config.yaml` includes a `server` block, and add a test that reads a non-default value. Add to the `config.yaml` heredoc in the fixture:
```
        server:
          port: 8755
```
and change `test_server_port_from_config` to assert `== 8755`.

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_profile_lib.py -k server_port -v`
Expected: FAIL (`AttributeError: module 'profile_lib' has no attribute 'server_port'`).

**Step 3: Implement the accessor**

Append to `scripts/profile_lib.py`:
```python
def server_port(root=None):
    return int((config(root).get("server") or {}).get("port", 8742))
```

Add to `profile.example/config.yaml` (after `active_skill_packs`):
```yaml
server:
  port: 8742
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_profile_lib.py -k server_port -v`
Expected: 3 passed (incl. the 8755 case).

**Step 5: Wire `task_server.py` to the accessor**

In `scripts/task_server.py`, the imports block already does `sys.path.insert(0, ...)` then imports `task_lib`, `cron_lib`, `jira_publish`. Add `import profile_lib` alongside them. Replace line 53:
```python
PORT = 8742
```
with:
```python
PORT = profile_lib.server_port()
```

**Step 6: Smoke-check the module still imports**

Run: `cd scripts && python3 -c "import task_server; print(task_server.PORT)" && cd ..`
Expected: prints `8742` (from `profile.example`).

**Step 7: Commit**

```bash
git add profile.example/config.yaml scripts/profile_lib.py scripts/task_server.py tests/test_profile_lib.py tests/conftest.py
git commit -m "feat(server): read port from profile config (collision-safe)"
```

---

## Task 3: `capabilities.json` schema + read/write helpers

**Why:** `capabilities.json` is the contract the Doctor writes and the UI/onboarding read. `profile_lib` owns reading and (atomic) writing it.

**Files:**
- Modify: `profile.example/capabilities.json`
- Modify: `scripts/profile_lib.py`
- Test: `tests/test_capabilities.py`

**Step 1: Write the failing test**

Create `tests/test_capabilities.py`:
```python
import json
import profile_lib


def test_capabilities_empty_when_absent(tmp_path):
    (tmp_path / "profile").mkdir()
    caps = profile_lib.read_capabilities(root=str(tmp_path))
    assert caps == {"schema_version": 1, "capabilities": {}}


def test_write_then_read_roundtrips(tmp_path):
    (tmp_path / "profile").mkdir()
    data = {
        "schema_version": 1,
        "platform": "darwin",
        "capabilities": {"qmd": {"kind": "local", "status": "ok"}},
    }
    profile_lib.write_capabilities(data, root=str(tmp_path))
    back = profile_lib.read_capabilities(root=str(tmp_path))
    assert back["capabilities"]["qmd"]["status"] == "ok"
    # written to the live profile dir
    assert (tmp_path / "profile" / "capabilities.json").is_file()


def test_write_is_atomic_no_partial_file(tmp_path):
    (tmp_path / "profile").mkdir()
    profile_lib.write_capabilities({"schema_version": 1, "capabilities": {}}, root=str(tmp_path))
    # no leftover temp file
    leftovers = [p.name for p in (tmp_path / "profile").iterdir() if p.name.startswith(".capabilities")]
    assert leftovers == []
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_capabilities.py -v`
Expected: FAIL (`read_capabilities`/`write_capabilities` undefined).

**Step 3: Implement**

Append to `scripts/profile_lib.py`:
```python
import json
import tempfile

CAPABILITIES_SCHEMA_VERSION = 1


def read_capabilities(root=None):
    """Read profile/capabilities.json, returning an empty-but-valid doc if absent."""
    path = os.path.join(profile_dir(root), "capabilities.json")
    if not os.path.isfile(path):
        return {"schema_version": CAPABILITIES_SCHEMA_VERSION, "capabilities": {}}
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {"schema_version": CAPABILITIES_SCHEMA_VERSION, "capabilities": {}}
    data.setdefault("schema_version", CAPABILITIES_SCHEMA_VERSION)
    data.setdefault("capabilities", {})
    return data


def write_capabilities(data, root=None):
    """Atomically write capabilities.json into the live profile dir."""
    data.setdefault("schema_version", CAPABILITIES_SCHEMA_VERSION)
    target = os.path.join(profile_dir(root), "capabilities.json")
    dir_ = os.path.dirname(target)
    fd, tmp = tempfile.mkstemp(prefix=".capabilities-", dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
```

Set `profile.example/capabilities.json` content to:
```json
{
  "schema_version": 1,
  "capabilities": {}
}
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_capabilities.py -v`
Expected: 3 passed.

**Step 5: Commit**

```bash
git add profile.example/capabilities.json scripts/profile_lib.py tests/test_capabilities.py
git commit -m "feat(profile): capabilities.json schema + atomic read/write helpers"
```

---

## Task 4: Transcript integration config + accessor

**Why:** The Doctor and the ported feed read the transcript provider + target dir from `integrations.yaml`. Runtime state (creds, session, ledger) lives under `profile/transcript/` (gitignored).

**Files:**
- Modify: `profile.example/integrations.yaml`
- Modify: `scripts/profile_lib.py`
- Modify: `.gitignore`
- Test: `tests/test_profile_lib.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_profile_lib.py`:
```python
def test_transcript_config_defaults(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: otter\n")
    tc = profile_lib.transcript_config(root=str(tmp_path))
    assert tc["provider"] == "otter"
    assert tc["target"] == "datasets/meetings/"  # default applied


def test_transcript_dir_under_profile(tmp_path):
    (tmp_path / "profile").mkdir()
    d = profile_lib.transcript_state_dir(root=str(tmp_path))
    assert d.endswith("/profile/transcript")
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_profile_lib.py -k transcript -v`
Expected: FAIL.

**Step 3: Implement**

Append to `scripts/profile_lib.py`:
```python
def transcript_config(root=None):
    t = integration("transcript", root)
    return {
        "provider": t.get("provider") or "none",
        "target": t.get("target") or "datasets/meetings/",
    }


def transcript_state_dir(root=None):
    """Per-person runtime dir for transcript creds/session/ledger (gitignored)."""
    return os.path.join(profile_dir(root), "transcript")
```

Update `profile.example/integrations.yaml` `transcript:` block to:
```yaml
transcript:
  provider: "none"       # otter | granola | none
  target: "datasets/meetings/"
```

Add to `.gitignore` (the `/profile/` line already ignores everything under it, but make the runtime dir explicit for clarity — only if `/profile/` is not already a blanket ignore; verify with `git check-ignore profile/transcript/session.json` first and skip this edit if it already prints a match).

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_profile_lib.py -k transcript -v`
Expected: 2 passed.

**Step 5: Commit**

```bash
git add profile.example/integrations.yaml scripts/profile_lib.py tests/test_profile_lib.py .gitignore
git commit -m "feat(profile): transcript config + state-dir accessors"
```

---

## Task 5: `platform_lib` — os_kind + open_url

**Why:** The single OS seam. Everything platform-specific funnels through here so the rest of the engine is platform-blind. This task establishes the seam and the mock point (`os_kind`).

**Files:**
- Create: `scripts/platform_lib.py`
- Test: `tests/test_platform_lib.py`

**Step 1: Write the failing test**

Create `tests/test_platform_lib.py`:
```python
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
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_platform_lib.py -v`
Expected: FAIL (`ModuleNotFoundError`).

**Step 3: Implement**

Create `scripts/platform_lib.py`:
```python
"""The single OS-abstraction seam for Magnolia.

Everything platform-specific (package managers, persistence mechanisms, opening
a URL) funnels through here so the rest of the engine stays platform-blind.

macOS is run-validated on the dev machine. Windows branches are written and
unit-tested against a mocked os_kind() but are DESIGN-VALIDATED, NOT
RUN-VALIDATED (no Windows box available).
"""
import platform
import subprocess


def os_kind():
    sysname = platform.system().lower()
    if sysname.startswith("darwin"):
        return "darwin"
    if sysname.startswith("windows"):
        return "windows"
    return "linux"


def open_url_cmd(url):
    kind = os_kind()
    if kind == "darwin":
        return ["open", url]
    if kind == "windows":
        # empty "" is the title arg for start; required when URL is quoted
        return ["cmd", "/c", "start", "", url]
    return ["xdg-open", url]


def open_url(url):
    subprocess.Popen(open_url_cmd(url))
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_platform_lib.py -v`
Expected: 2 passed.

**Step 5: Commit**

```bash
git add scripts/platform_lib.py tests/test_platform_lib.py
git commit -m "feat(platform): OS seam — os_kind + open_url (mac run, win design-only)"
```

---

## Task 6: `platform_lib` — package install + launch-agents dir

**Files:**
- Modify: `scripts/platform_lib.py`
- Test: `tests/test_platform_lib.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_platform_lib.py`:
```python
def test_package_install_cmd_per_os(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "darwin")
    assert platform_lib.package_install_cmd("pandoc") == ["brew", "install", "pandoc"]
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "windows")
    assert platform_lib.package_install_cmd("pandoc") == ["winget", "install", "--id", "pandoc", "-e"]


def test_launch_agents_dir(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "darwin")
    assert platform_lib.launch_agents_dir().endswith("/Library/LaunchAgents")
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "windows")
    assert platform_lib.launch_agents_dir() is None  # Task Scheduler has no dir
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_platform_lib.py -k "package_install or launch_agents" -v`
Expected: FAIL.

**Step 3: Implement**

Append to `scripts/platform_lib.py`:
```python
import os

# winget IDs differ from brew names; map the ones the Doctor installs.
_WINGET_IDS = {
    "pandoc": "pandoc",
    "qmd": "qmd",            # placeholder — verify real winget id during impl
    "fswatch": "",           # no direct winget equivalent; handled by Doctor notes
}


def package_install_cmd(name):
    kind = os_kind()
    if kind == "windows":
        wid = _WINGET_IDS.get(name, name)
        return ["winget", "install", "--id", wid, "-e"]
    # darwin/linux both use brew in this engine's supported setups
    return ["brew", "install", name]


def launch_agents_dir():
    if os_kind() == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
    return None  # Windows uses Task Scheduler (no directory); Linux unsupported for persistence v1
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_platform_lib.py -v`
Expected: all passed.

**Step 5: Commit**

```bash
git add scripts/platform_lib.py tests/test_platform_lib.py
git commit -m "feat(platform): package_install_cmd + launch_agents_dir"
```

---

## Task 7: `doctor.py` — local tool + python-dep probes

**Why:** The detection primitives. Pure functions, mockable via `shutil.which` / `importlib.util.find_spec`.

**Files:**
- Create: `scripts/doctor.py`
- Test: `tests/test_doctor.py`

**Step 1: Write the failing test**

Create `tests/test_doctor.py`:
```python
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
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_doctor.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'doctor'`).

**Step 3: Implement**

Create `scripts/doctor.py`:
```python
"""Magnolia Doctor — deterministic, side-effect-free capability DETECTION.

Writes profile/capabilities.json. Safe to run headless / on a cron. Remediation
is Claude-driven (see .claude/skills/workflow-doctor); this module never installs
anything or mutates external state — it only observes and records.
"""
import argparse
import importlib.util
import shutil
import socket
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import profile_lib  # noqa: E402


def probe_which(name, remedy=None):
    found = shutil.which(name) is not None
    cap = {"kind": "local", "status": "ok" if found else "missing"}
    if not found and remedy:
        cap["remedy"] = remedy
    return cap


def probe_python_deps(modules):
    missing = [m for m in modules if importlib.util.find_spec(m) is None]
    cap = {"kind": "local"}
    if missing:
        cap["status"] = "degraded"
        cap["missing"] = missing
    else:
        cap["status"] = "ok"
        cap["detail"] = ", ".join(modules)
    return cap
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_doctor.py -v`
Expected: 4 passed.

**Step 5: Commit**

```bash
git add scripts/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): local tool + python-dep probes"
```

---

## Task 8: `doctor.py` — server + transcript probes + `detect()` assembly

**Why:** `detect()` assembles the full `capabilities.json`: local tools, recommended `msgraph_cli`, python deps, the server (live TCP probe), the transcript feed (provider + session freshness), and remote-MCP seeds from `integrations.yaml`.

**Files:**
- Modify: `scripts/doctor.py`
- Test: `tests/test_doctor.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_doctor.py`:
```python
import os


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
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_doctor.py -k "server or transcript or detect" -v`
Expected: FAIL.

**Step 3: Implement**

Append to `scripts/doctor.py`:
```python
import os

import platform_lib

# Local CLI tools the Doctor knows how to detect (and a remedy hint for each).
_LOCAL_TOOLS = {
    "qmd":        {"remedy": "brew install qmd"},
    "pandoc":     {"remedy": "brew install pandoc"},
    "claude_cli": {"bin": "claude", "remedy": "see claude.ai/code install"},
    "msgraph_cli":{"bin": "mgc", "required": False,
                   "detail": "recommended for doc-sync + bulk Teams/OneDrive"},
}
_PYTHON_DEPS = ["ruamel.yaml"]
# Remote connectors keyed by the integration category that implies them.
_REMOTE_FROM_INTEGRATION = {
    "project_management": lambda prov: prov,   # 'jira'/'asana'/'linear'
    "calendar": lambda prov: "m365" if prov == "m365" else prov,
}


def probe_server(port):
    cap = {"kind": "service", "port": port}
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        cap["status"] = "running" if s.connect_ex(("127.0.0.1", port)) == 0 else "down"
    return cap


def probe_transcript(root=None):
    tc = profile_lib.transcript_config(root)
    provider = tc["provider"]
    cap = {"kind": "feed", "provider": provider, "target": tc["target"]}
    if provider == "none":
        cap["status"] = "not_expected"
        return cap
    # otter: a saved Playwright session.json under the transcript state dir means authed
    session = os.path.join(profile_lib.transcript_state_dir(root), "session.json")
    cap["status"] = "ok" if os.path.isfile(session) else "needs_reauth"
    return cap


def _remote_seeds(root=None):
    seeds = {}
    for category, namer in _REMOTE_FROM_INTEGRATION.items():
        prov = profile_lib.provider(category, root)
        if prov and prov != "none":
            seeds[namer(prov)] = {"kind": "remote", "expected": True, "status": "unknown"}
    return seeds


def detect(root=None):
    caps = {}
    for name, spec in _LOCAL_TOOLS.items():
        binname = spec.get("bin", name)
        c = probe_which(binname, remedy=spec.get("remedy"))
        if "required" in spec:
            c["required"] = spec["required"]
        if "detail" in spec:
            c["detail"] = spec["detail"]
        caps[name] = c
    caps["python_deps"] = probe_python_deps(_PYTHON_DEPS)
    caps["server"] = probe_server(profile_lib.server_port(root))
    caps["transcript"] = probe_transcript(root)
    caps.update(_remote_seeds(root))
    doc = {
        "schema_version": profile_lib.CAPABILITIES_SCHEMA_VERSION,
        "platform": platform_lib.os_kind(),
        "capabilities": caps,
    }
    profile_lib.write_capabilities(doc, root)
    return doc
```

> Note on `generated_at`: the design shows a timestamp, but `Date.now()`-style calls are avoided for determinism in tests. Add `generated_at` only in the CLI layer (Task 9), where it's stamped from `datetime` at invocation, NOT inside `detect()` — so `detect()` stays pure and test-stable.

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_doctor.py -v`
Expected: all passed.

**Step 5: Commit**

```bash
git add scripts/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): server + transcript probes + detect() assembly"
```

---

## Task 9: `doctor.py` — CLI (detect | check | report)

**Files:**
- Modify: `scripts/doctor.py`
- Test: `tests/test_doctor.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_doctor.py`:
```python
def test_report_text_lists_caps(tmp_path):
    caps = {"schema_version": 1, "platform": "darwin", "capabilities": {
        "qmd": {"kind": "local", "status": "missing", "remedy": "brew install qmd"},
        "server": {"kind": "service", "status": "down", "port": 8742},
    }}
    text = doctor.report_text(caps)
    assert "qmd" in text and "missing" in text
    assert "brew install qmd" in text


def test_check_exit_code(tmp_path, monkeypatch):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: none\n")
    monkeypatch.setattr(doctor.shutil, "which", lambda n: None)
    monkeypatch.setattr(doctor.importlib.util, "find_spec", lambda n: object())
    doctor.detect(root=str(tmp_path))
    assert doctor.check("qmd", root=str(tmp_path)) == 1   # missing → nonzero
    assert doctor.check("python_deps", root=str(tmp_path)) == 0  # ok → zero
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_doctor.py -k "report or check" -v`
Expected: FAIL.

**Step 3: Implement**

Append to `scripts/doctor.py`:
```python
def report_text(caps):
    lines = [f"Magnolia Doctor — platform: {caps.get('platform', '?')}", ""]
    for name, c in sorted(caps.get("capabilities", {}).items()):
        status = c.get("status", "?")
        line = f"  {name:14} {status}"
        if c.get("remedy") and status != "ok":
            line += f"   → {c['remedy']}"
        if c.get("required") is False and status != "ok":
            line += "   (recommended)"
        lines.append(line)
    return "\n".join(lines)


def check(cap_name, root=None):
    caps = profile_lib.read_capabilities(root)["capabilities"]
    c = caps.get(cap_name)
    if not c:
        return 2
    return 0 if c.get("status") in ("ok", "running") else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="doctor")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect")
    cp = sub.add_parser("check")
    cp.add_argument("capability")
    sub.add_parser("report")
    args = parser.parse_args(argv)

    if args.cmd == "detect":
        from datetime import datetime, timezone
        doc = detect()
        doc["generated_at"] = datetime.now(timezone.utc).isoformat()
        profile_lib.write_capabilities(doc)
        print(report_text(doc))
        return 0
    if args.cmd == "report":
        print(report_text(profile_lib.read_capabilities()))
        return 0
    if args.cmd == "check":
        return check(args.capability)


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Run to verify pass + smoke the CLI**

Run: `python3 -m pytest tests/test_doctor.py -v`
Expected: all passed.
Run: `cd scripts && python3 doctor.py report && cd ..`
Expected: prints a report (empty caps if no detect run yet — that's fine).

**Step 5: Commit**

```bash
git add scripts/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): CLI detect|check|report + generated_at stamp"
```

---

## Task 10: `server_lib` — free_port, url, is_running

**Files:**
- Create: `scripts/server_lib.py`
- Test: `tests/test_server_lib.py`

**Step 1: Write the failing test**

Create `tests/test_server_lib.py`:
```python
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import server_lib


def test_url_uses_port(monkeypatch):
    monkeypatch.setattr(server_lib.profile_lib, "server_port", lambda root=None: 8755)
    assert server_lib.url() == "http://localhost:8755"


def test_free_port_returns_unused():
    p = server_lib.free_port()
    # we can bind it → it was free
    s = socket.socket()
    s.bind(("127.0.0.1", p))
    s.close()


def test_is_running_true_when_api_serves():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"[]")
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        assert server_lib.is_running(port=port) is True
    finally:
        srv.shutdown()


def test_is_running_false_when_nothing_listens():
    assert server_lib.is_running(port=59997) is False
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_server_lib.py -v`
Expected: FAIL (`ModuleNotFoundError`).

**Step 3: Implement**

Create `scripts/server_lib.py`:
```python
"""Server lifecycle primitives for the task board. Port-aware via profile config."""
import os
import socket
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PM_OS_DIR = os.path.dirname(SCRIPT_DIR)


def port(root=None):
    return profile_lib.server_port(root)


def url(root=None):
    return f"http://localhost:{port(root)}"


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def is_running(port=None, root=None):
    p = port if port is not None else profile_lib.server_port(root)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{p}/api/tasks", timeout=1.0) as r:
            return r.status == 200
    except Exception:
        return False
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_server_lib.py -v`
Expected: 4 passed.

**Step 5: Commit**

```bash
git add scripts/server_lib.py tests/test_server_lib.py
git commit -m "feat(server): server_lib free_port/url/is_running"
```

---

## Task 11: `server_lib` — start + verify

**Why:** `start()` launches the server detached and polls until it actually serves (never hand over a dead URL). Made testable by injecting the command.

**Files:**
- Modify: `scripts/server_lib.py`
- Test: `tests/test_server_lib.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_server_lib.py`:
```python
import sys as _sys


def test_start_polls_until_serving(tmp_path):
    # a tiny server script that serves /api/tasks 200 on argv[1]
    script = tmp_path / "tiny.py"
    script.write_text(
        "import sys\n"
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200); self.end_headers(); self.wfile.write(b'[]')\n"
        "    def log_message(self,*a): pass\n"
        "HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n"
    )
    p = server_lib.free_port()
    proc = server_lib.start(port=p, cmd=[_sys.executable, str(script), str(p)], timeout=5.0)
    try:
        assert server_lib.is_running(port=p) is True
    finally:
        proc.terminate()


def test_start_raises_if_never_serves():
    p = server_lib.free_port()
    import pytest
    with pytest.raises(TimeoutError):
        # 'true' exits immediately, never serves
        server_lib.start(port=p, cmd=["true"], timeout=1.5)
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_server_lib.py -k start -v`
Expected: FAIL.

**Step 3: Implement**

Append to `scripts/server_lib.py`:
```python
import subprocess
import time


def default_cmd():
    return [sys.executable, os.path.join(SCRIPT_DIR, "task_server.py")]


def start(port=None, cmd=None, timeout=15.0, poll=0.25):
    """Launch the server detached; poll until it serves or raise TimeoutError."""
    p = port if port is not None else profile_lib.server_port()
    command = cmd or default_cmd()
    proc = subprocess.Popen(command, cwd=PM_OS_DIR,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_running(port=p):
            return proc
        if proc.poll() is not None:  # process died
            break
        time.sleep(poll)
    proc.terminate()
    raise TimeoutError(f"server did not start serving on port {p} within {timeout}s")
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_server_lib.py -v`
Expected: all passed.

**Step 5: Commit**

```bash
git add scripts/server_lib.py tests/test_server_lib.py
git commit -m "feat(server): server_lib.start with serve-verification + timeout"
```

---

## Task 12: `persist_lib` — macOS LaunchAgent rendering

**Why:** Pure rendering is the testable core; install side-effects come in Task 14. The plist is generalized from the existing `run_task_server.sh` pattern — repo path resolved at render time, no hardcoded user.

**Files:**
- Create: `scripts/persist_lib.py`
- Test: `tests/test_persist_lib.py`

**Step 1: Write the failing test**

Create `tests/test_persist_lib.py`:
```python
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
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_persist_lib.py -v`
Expected: FAIL.

**Step 3: Implement**

Create `scripts/persist_lib.py`:
```python
"""Reboot-persistence for the task server.

macOS: per-user LaunchAgent (RunAtLoad + KeepAlive) — RUN-VALIDATED.
Windows: Task Scheduler at logon — DESIGN-VALIDATED ONLY (no Windows box).
Same install()/remove()/is_installed() API on both via platform_lib.
"""
import os
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_lib  # noqa: E402

LABEL = "com.pm-os.task-server"


def render_launchagent(label, program, working_dir, log_path):
    args = "\n".join(f"        <string>{escape(a)}</string>" for a in program)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{escape(label)}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>WorkingDirectory</key>
    <string>{escape(working_dir)}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{escape(log_path)}</string>
    <key>StandardErrorPath</key>
    <string>{escape(log_path)}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
"""
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_persist_lib.py -v`
Expected: 1 passed.

**Step 5: Commit**

```bash
git add scripts/persist_lib.py tests/test_persist_lib.py
git commit -m "feat(persist): macOS LaunchAgent rendering (no hardcoded user)"
```

---

## Task 13: `persist_lib` — Windows Scheduled-Task rendering (design-only)

**Files:**
- Modify: `scripts/persist_lib.py`
- Test: `tests/test_persist_lib.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_persist_lib.py`:
```python
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
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_persist_lib.py -k scheduled_task -v`
Expected: FAIL.

**Step 3: Implement**

Append to `scripts/persist_lib.py`:
```python
def render_scheduled_task(name, program, args, working_dir):
    """Return a PowerShell snippet registering a per-user at-logon task.

    DESIGN-VALIDATED ONLY — not executed/verified on Windows.
    Per-user (no -RunLevel Highest) so it needs no admin/UAC and runs in the
    user's context (can read their files/creds).
    """
    return (
        f'$action = New-ScheduledTaskAction -Execute "{program}" '
        f'-Argument "{args}" -WorkingDirectory "{working_dir}"\n'
        f'$trigger = New-ScheduledTaskTrigger -AtLogOn\n'
        f'$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)\n'
        f'Register-ScheduledTask -TaskName "{name}" -Action $action '
        f'-Trigger $trigger -Settings $settings -Force\n'
    )
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_persist_lib.py -v`
Expected: all passed.

**Step 5: Commit**

```bash
git add scripts/persist_lib.py tests/test_persist_lib.py
git commit -m "feat(persist): Windows Task-Scheduler-at-logon rendering (design-only)"
```

---

## Task 14: `persist_lib` — install / remove / is_installed dispatch

**Why:** The platform-blind API onboarding + the Engine tab call. macOS path writes a real plist into a (test-injectable) LaunchAgents dir; Windows path returns the PowerShell command for Claude to run.

**Files:**
- Modify: `scripts/persist_lib.py`
- Test: `tests/test_persist_lib.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_persist_lib.py`:
```python
def test_install_macos_writes_plist(tmp_path, monkeypatch):
    monkeypatch.setattr(persist_lib.platform_lib, "os_kind", lambda: "darwin")
    monkeypatch.setattr(persist_lib.platform_lib, "launch_agents_dir", lambda: str(tmp_path))
    result = persist_lib.install(program=["/usr/bin/python3", "/repo/scripts/task_server.py"],
                                 working_dir="/repo", log_path="/repo/logs/s.log",
                                 activate=False)
    plist_path = tmp_path / f"{persist_lib.LABEL}.plist"
    assert plist_path.is_file()
    assert persist_lib.is_installed() is True
    assert result["mechanism"] == "launchagent"


def test_is_installed_false_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(persist_lib.platform_lib, "os_kind", lambda: "darwin")
    monkeypatch.setattr(persist_lib.platform_lib, "launch_agents_dir", lambda: str(tmp_path))
    assert persist_lib.is_installed() is False


def test_install_windows_returns_command(monkeypatch):
    monkeypatch.setattr(persist_lib.platform_lib, "os_kind", lambda: "windows")
    result = persist_lib.install(program=["python.exe", "task_server.py"],
                                 working_dir="C:\\repo", log_path="x", activate=False)
    assert result["mechanism"] == "scheduled_task"
    assert "Register-ScheduledTask" in result["command"]
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_persist_lib.py -k "install or is_installed" -v`
Expected: FAIL.

**Step 3: Implement**

Append to `scripts/persist_lib.py`:
```python
import subprocess


def _plist_path():
    d = platform_lib.launch_agents_dir()
    return os.path.join(d, f"{LABEL}.plist") if d else None


def is_installed():
    if platform_lib.os_kind() == "darwin":
        p = _plist_path()
        return bool(p and os.path.isfile(p))
    # Windows: would query `schtasks /query /tn MagnoliaTaskServer` — design-only.
    return False


def install(program, working_dir, log_path, activate=True):
    kind = platform_lib.os_kind()
    if kind == "darwin":
        plist = render_launchagent(LABEL, program, working_dir, log_path)
        path = _plist_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(plist)
        if activate:
            subprocess.run(["launchctl", "unload", path], capture_output=True)
            subprocess.run(["launchctl", "load", path], capture_output=True)
        return {"mechanism": "launchagent", "path": path}
    if kind == "windows":
        cmd = render_scheduled_task("MagnoliaTaskServer", program[0],
                                    " ".join(program[1:]), working_dir)
        # design-only: hand the command back for Claude to run in PowerShell
        return {"mechanism": "scheduled_task", "command": cmd}
    return {"mechanism": "none", "note": "persistence unsupported on this OS"}


def remove(activate=True):
    if platform_lib.os_kind() == "darwin":
        path = _plist_path()
        if path and os.path.isfile(path):
            if activate:
                subprocess.run(["launchctl", "unload", path], capture_output=True)
            os.remove(path)
            return True
    return False
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_persist_lib.py -v`
Expected: all passed.

**Step 5: Commit**

```bash
git add scripts/persist_lib.py tests/test_persist_lib.py
git commit -m "feat(persist): install/remove/is_installed dispatch (mac real, win design-only)"
```

---

## Task 15: Port the Otter module into the engine

**Why:** Magnolia must own a real transcript feed. Port `~/scripts/otter/` into the engine, profile-driven, depositing into `datasets/meetings/`. Reading `~/scripts/otter/*` is authorized.

**Files:**
- Create: `scripts/otter_sync.py` (ported)
- Create: `scripts/otter_auth.py` (ported)
- Create: `scripts/otter_classify.py` (ported)
- Create: `scripts/otter_rename.py` (ported)
- Create: `requirements-transcript.txt`
- Test: `tests/test_otter_port.py`

**Step 1: Read the source pipeline**

Run (authorized — outside production pm-os):
```bash
cat ~/scripts/otter/otter_sync.py ~/scripts/otter/otter_classify.py ~/scripts/otter/otter_rename.py
```
Understand: how it authenticates (Playwright `session.json`), where it currently deposits transcripts, the dedup ledger (`downloaded.json`), and how classify/rename produce the meeting YAML frontmatter + filename.

**Step 2: Port with these exact adaptations**

Copy each file into `scripts/` and change ONLY environment/path coupling — preserve the working logic:
- **Creds:** load `.env` from `profile_lib.transcript_state_dir()` (i.e. `profile/transcript/.env`), not `~/scripts/otter/.env`.
- **Session + ledger:** `session.json` and `downloaded.json` live under `profile_lib.transcript_state_dir()`; create the dir if missing.
- **Deposit dir:** the meetings target = `os.path.join(profile_lib.PM_OS_DIR, profile_lib.transcript_config()["target"])` — i.e. `datasets/meetings/`, NOT a hardcoded `~/pm-os` path.
- **Post-deposit hook:** keep the existing `task-extract-meetings.sh` trigger but resolve it relative to the repo (`scripts/task-extract-meetings.sh`).
- **Shebang:** change the hardcoded `#!/Users/jayjenkins/scripts/otter/.venv/bin/python3` to `#!/usr/bin/env python3`.
- Remove any other `/Users/jayjenkins` absolute paths.

**Step 3: Record dependencies**

Create `requirements-transcript.txt`:
```
git+https://github.com/gmchad/otterai-api.git
python-dotenv
playwright
openai
```

**Step 4: Write a port-integrity test (no network)**

Create `tests/test_otter_port.py`:
```python
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
```

**Step 5: Run the test**

Run: `python3 -m pytest tests/test_otter_port.py -v`
Expected: 2 passed.

**Step 6: Commit**

```bash
git add scripts/otter_sync.py scripts/otter_auth.py scripts/otter_classify.py scripts/otter_rename.py requirements-transcript.txt tests/test_otter_port.py
git commit -m "feat(transcript): port Otter pipeline into engine (profile-driven paths)"
```

---

## Task 16: `transcript_sync.py` — provider dispatcher

**Why:** A single profile-driven entrypoint onboarding/cron call, dispatching by provider. Otter today; Granola is a Phase-3 drop-in behind the same entrypoint.

**Files:**
- Create: `scripts/transcript_sync.py`
- Test: `tests/test_transcript_sync.py`

**Step 1: Write the failing test**

Create `tests/test_transcript_sync.py`:
```python
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
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_transcript_sync.py -v`
Expected: FAIL.

**Step 3: Implement**

Create `scripts/transcript_sync.py`:
```python
"""Profile-driven transcript-feed entrypoint. Dispatches by provider.

Otter is supported now; Granola is a Phase-3 drop-in behind this same entrypoint.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402


def _run_otter(root=None):
    import otter_sync
    return otter_sync.main()  # ported entrypoint


def sync(root=None):
    provider = profile_lib.transcript_config(root)["provider"]
    if provider == "none":
        return {"status": "skipped", "provider": "none"}
    if provider == "otter":
        _run_otter(root)
        return {"status": "ok", "provider": "otter"}
    if provider == "granola":
        return {"status": "unsupported", "provider": "granola",
                "note": "Granola adapter lands in Phase 3"}
    return {"status": "unsupported", "provider": provider}


if __name__ == "__main__":
    print(sync())
```

> If the ported `otter_sync.py` exposes its entrypoint under a different name than `main()`, adjust `_run_otter` to match what Task 15 produced.

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_transcript_sync.py -v`
Expected: 3 passed.

**Step 5: Commit**

```bash
git add scripts/transcript_sync.py tests/test_transcript_sync.py
git commit -m "feat(transcript): provider-dispatching sync entrypoint"
```

---

## Task 17: `feed_guard` — detect & disable competing downloaders

**Why:** The "single feed" guarantee. Scan for other transcript downloaders (LaunchAgents whose label/target looks Otter/transcript-ish, or a known old-install script path) and offer guided disable. Conservative: warn rather than disable on ambiguity.

**Files:**
- Create: `scripts/feed_guard.py`
- Test: `tests/test_feed_guard.py`

**Step 1: Write the failing test**

Create `tests/test_feed_guard.py`:
```python
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
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_feed_guard.py -v`
Expected: FAIL.

**Step 3: Implement**

Create `scripts/feed_guard.py`:
```python
"""Guard the single-transcript-feed guarantee.

Scans for OTHER downloaders that could write transcripts outside Magnolia.
Detection is conservative — it reports candidates; disabling is a separate,
user-confirmed step (Claude calls disable() only after the human says yes).
"""
import glob
import os
import re

# Signals that a LaunchAgent is a transcript downloader.
_SIGNAL_RE = re.compile(r"otter|granola|transcript|meeting[-_]?sync", re.IGNORECASE)


def detect_competing(launch_agents_dir=None, own_labels=None):
    own = set(own_labels or [])
    d = launch_agents_dir or os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
    found = []
    for path in sorted(glob.glob(os.path.join(d, "*.plist"))):
        text = open(path, encoding="utf-8", errors="ignore").read()
        m = re.search(r"<key>Label</key>\s*<string>([^<]+)</string>", text)
        label = m.group(1) if m else os.path.basename(path)[:-6]
        if label in own:
            continue
        if _SIGNAL_RE.search(text):
            found.append({"label": label, "path": path})
    return found


def disable(path, activate=True):
    """Disable a competing LaunchAgent (user-confirmed). Renames it aside; never deletes."""
    if activate:
        import subprocess
        subprocess.run(["launchctl", "unload", path], capture_output=True)
    disabled = path + ".disabled-by-magnolia"
    os.rename(path, disabled)
    return disabled
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_feed_guard.py -v`
Expected: 2 passed.

**Step 5: Commit**

```bash
git add scripts/feed_guard.py tests/test_feed_guard.py
git commit -m "feat(transcript): feed_guard detects + safely disables competing downloaders"
```

---

## Task 18: De-personalize `session-start.sh` + `hooks.json`

**Why:** Both hardcode `/Users/jayjenkins/pm-os/...`, pointing the team repo's hook at production (a latent bug). Resolve to the repo root dynamically.

**Files:**
- Modify: `.claude/hooks/session-start.sh`
- Modify: `.claude/hooks/hooks.json`
- Test: `tests/test_hook_paths.py`

**Step 1: Write the failing test**

Create `tests/test_hook_paths.py`:
```python
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_session_start_has_no_hardcoded_repo_path():
    text = (REPO / ".claude/hooks/session-start.sh").read_text()
    assert "/Users/jayjenkins/pm-os" not in text


def test_hooks_json_command_is_relative_or_resolved():
    data = json.loads((REPO / ".claude/hooks/hooks.json").read_text())
    cmd = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "/Users/jayjenkins/pm-os" not in cmd
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_hook_paths.py -v`
Expected: FAIL.

**Step 3: Implement**

In `.claude/hooks/session-start.sh`, replace the hardcoded `SKILL_ROOT` line:
```bash
SKILL_ROOT="/Users/jayjenkins/pm-os/.claude/skills"
```
with a repo-relative resolution:
```bash
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
SKILL_ROOT="$REPO_ROOT/.claude/skills"
```
(The `profile_lib.py` invocation in the script already uses `$(dirname "$0")/../../scripts/...` — keep it, but for robustness switch it to `$REPO_ROOT/scripts/profile_lib.py`.)

In `.claude/hooks/hooks.json`, Claude Code supports `$CLAUDE_PROJECT_DIR` in hook commands. Replace:
```json
"command": "/Users/jayjenkins/pm-os/.claude/hooks/session-start.sh"
```
with:
```json
"command": "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh"
```

**Step 4: Run to verify pass + smoke the hook**

Run: `python3 -m pytest tests/test_hook_paths.py -v`
Expected: 2 passed.
Run: `bash .claude/hooks/session-start.sh | python3 -c "import sys,json; json.load(sys.stdin); print('valid json')"`
Expected: `valid json`.

**Step 5: Commit**

```bash
git add .claude/hooks/session-start.sh .claude/hooks/hooks.json tests/test_hook_paths.py
git commit -m "fix(hooks): resolve hook + skill paths from repo root, not hardcoded production path"
```

---

## Task 19: De-personalize qmd + task-server launch paths

**Why:** `qmd-setup.sh` (`PMDIR=$HOME/pm-os`), `qmd-nightly-update.sh` (absolute log), and `run_task_server.sh` (`REPO=/Users/jayjenkins/pm-os`, plist label) all hardcode paths. Derive from the script's own location.

**Files:**
- Modify: `scripts/qmd-setup.sh`
- Modify: `scripts/qmd-nightly-update.sh`
- Modify: `scripts/run_task_server.sh`
- Test: `tests/test_script_paths.py`

**Step 1: Write the failing test**

Create `tests/test_script_paths.py`:
```python
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ["qmd-setup.sh", "qmd-nightly-update.sh", "run_task_server.sh"]


def test_no_hardcoded_pmos_paths():
    for name in SCRIPTS:
        text = (REPO / "scripts" / name).read_text()
        assert "/Users/jayjenkins/pm-os" not in text, f"{name}"
        assert '$HOME/pm-os' not in text and "$HOME/pm-os" not in text, f"{name}"
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_script_paths.py -v`
Expected: FAIL.

**Step 3: Implement**

In each script, derive the repo root from the script's own location and use it. Add near the top (after the shebang/`set`):
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
```
Then:
- `qmd-setup.sh`: replace `PMDIR="$HOME/pm-os"` with `PMDIR="$REPO"`.
- `qmd-nightly-update.sh`: replace the hardcoded `LOG="/Users/jayjenkins/pm-os/logs/qmd-update.log"` with `LOG="$REPO/logs/qmd-update.log"` (add the `SCRIPT_DIR`/`REPO` derivation there too).
- `run_task_server.sh`: replace `REPO="/Users/jayjenkins/pm-os"` with the derived `REPO`; leave the plist label generalization to `persist_lib` (this script remains a manual fallback). If the `exec /opt/homebrew/bin/python3` line is macOS-specific, leave it — `run_task_server.sh` is the macOS LaunchAgent entrypoint; `persist_lib` is the cross-platform path.

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_script_paths.py -v`
Expected: 1 passed.

**Step 5: Commit**

```bash
git add scripts/qmd-setup.sh scripts/qmd-nightly-update.sh scripts/run_task_server.sh tests/test_script_paths.py
git commit -m "fix(scripts): derive repo root from script location, drop hardcoded pm-os paths"
```

---

## Task 20: Move SharePoint/OneDrive sync config to the profile

**Why:** `sync_config.yaml` carries Vantaca tenant/SharePoint/OneDrive paths. The provider-agnostic shape moves to `integrations.yaml`; the OneDrive auto-detect logic (already in `setup_doc_sync.sh`) is the runtime resolver.

**Files:**
- Modify: `profile.example/integrations.yaml`
- Modify: `scripts/profile_lib.py`
- Modify: `scripts/doc_sync.py` (read config via `profile_lib`, with `sync_config.yaml` as legacy fallback)
- Test: `tests/test_profile_lib.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_profile_lib.py`:
```python
def test_doc_sync_config_from_integrations(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text(
        "doc_sync:\n"
        "  onedrive_root: \"~/Library/CloudStorage/OneDrive-Acme\"\n"
        "  sharepoint_site: \"PM-OS\"\n"
        "  enabled: true\n"
    )
    dc = profile_lib.doc_sync_config(root=str(tmp_path))
    assert dc["sharepoint_site"] == "PM-OS"
    assert dc["enabled"] is True


def test_doc_sync_config_defaults_disabled(tmp_path):
    (tmp_path / "profile").mkdir()
    assert profile_lib.doc_sync_config(root=str(tmp_path))["enabled"] is False
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_profile_lib.py -k doc_sync -v`
Expected: FAIL.

**Step 3: Implement**

Append to `scripts/profile_lib.py`:
```python
def doc_sync_config(root=None):
    d = integration("doc_sync", root)
    return {
        "onedrive_root": d.get("onedrive_root", ""),
        "sharepoint_site": d.get("sharepoint_site", "PM-OS"),
        "enabled": bool(d.get("enabled", False)),
    }
```

Add to `profile.example/integrations.yaml`:
```yaml
doc_sync:
  onedrive_root: ""      # auto-detected by the Doctor (OneDrive-* under ~/Library/CloudStorage)
  sharepoint_site: "PM-OS"
  enabled: false
```

In `scripts/doc_sync.py`, where it loads `sync_config.yaml`, prefer `profile_lib.doc_sync_config()` when it returns `enabled` config, else fall back to the existing `sync_config.yaml` read (keep backward compatibility; do not delete `sync_config.yaml`). Make this the minimal change — wrap the existing loader so a populated profile wins.

**Step 4: Run to verify pass + smoke import**

Run: `python3 -m pytest tests/test_profile_lib.py -k doc_sync -v`
Expected: 2 passed.
Run: `cd scripts && python3 -c "import doc_sync; print('ok')" && cd ..`
Expected: `ok`.

**Step 5: Commit**

```bash
git add profile.example/integrations.yaml scripts/profile_lib.py scripts/doc_sync.py tests/test_profile_lib.py
git commit -m "refactor(doc-sync): read sync config from profile integrations (legacy yaml fallback)"
```

---

## Task 21: `workflow-doctor` skill — the remediation playbook

**Why:** The Claude-side half of the Doctor. Reads `capabilities.json`, runs installs via Bash, walks the user through auth, re-runs `doctor.py detect`, stamps remote-MCP status.

**Files:**
- Create: `.claude/skills/workflow-doctor/SKILL.md`
- Test: `tests/test_skill_frontmatter.py`

**Step 1: Write the failing test**

Create `tests/test_skill_frontmatter.py`:
```python
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent


def _frontmatter(path):
    text = path.read_text()
    assert text.startswith("---\n"), f"{path} missing YAML frontmatter"
    fm = text.split("---\n", 2)[1]
    return fm


def test_workflow_doctor_frontmatter():
    fm = _frontmatter(REPO / ".claude/skills/workflow-doctor/SKILL.md")
    assert "name: workflow-doctor" in fm
    assert "description:" in fm
    assert "Use when" in fm  # trigger-led description
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_skill_frontmatter.py -k doctor -v`
Expected: FAIL (file missing).

**Step 3: Write the skill**

Create `.claude/skills/workflow-doctor/SKILL.md`:
```markdown
---
name: workflow-doctor
description: Use when a capability is missing/degraded/needs re-auth, when the user asks to "fix"/"set up"/"authorize" a tool or integration, or during onboarding's Doctor pass — detects with scripts/doctor.py and remediates conversationally.
allowed-tools: Bash, Read, Edit
---

# Doctor — detect, then remediate

You are the remediation half of the Doctor. Detection is deterministic Python
(`scripts/doctor.py`); your job is the adaptive, conversational fixing. The human
does only the irreducible minimum — clicking "Authorize," pasting a token.

## Loop

1. **Detect.** Run `python3 scripts/doctor.py detect`. Read `profile/capabilities.json`.
2. **Triage** each capability whose `status` is not `ok`/`running`:
   - **local** (qmd, pandoc, claude_cli, msgraph_cli): run the install via Bash —
     `brew install <x>` on macOS, the `winget` equivalent on Windows (use the command in
     `remedy`). For `msgraph_cli`, the macOS install route may need looking up — confirm the
     current `mgc` install method before running it. `required: false` capabilities are
     RECOMMENDED — offer, don't insist.
   - **feed/transcript** `needs_reauth`: the Otter session expired. Walk the user through
     `python3 scripts/otter_auth.py` (a browser opens for Microsoft sign-in). This is
     inherently manual — explain warmly, wait for them.
   - **remote** (jira/m365/pendo/…): you cannot refresh these from the shell — they are
     claude.ai connectors. Tell the user plainly: open claude.ai → Connectors → authorize X.
     Then verify by making one cheap read-only call to that MCP. If it works, set that
     capability's `status` to `ok` and `last_seen` to today in `capabilities.json`; if it
     fails, set `needs_reauth` with a short `reason`.
3. **Re-detect** (`doctor.py detect`) and confirm what's now green.
4. **Report** calmly: what's working, what's still degraded (and that its features are simply
   disabled until fixed — nothing is broken), and the single next action if any.

## Rules
- Never claim something is fixed without re-running detection and seeing it.
- Graceful degradation: a still-missing capability disables only its own features. Never block.
- Plain language. No git, no model IDs, no jargon. Blast-radius in words a COO reads easily.
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_skill_frontmatter.py -k doctor -v`
Expected: 1 passed.

**Step 5: Commit**

```bash
git add .claude/skills/workflow-doctor/SKILL.md tests/test_skill_frontmatter.py
git commit -m "feat(doctor): workflow-doctor remediation skill"
```

---

## Task 22: `meta-onboard` skill — the conversational flow + Magnolia persona

**Why:** The "onboard me" entrypoint. Resumable, task-reifying, degradation-tolerant, and voiced as the Magnolia concierge.

**Files:**
- Create: `.claude/skills/meta-onboard/SKILL.md`
- Test: `tests/test_skill_frontmatter.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_skill_frontmatter.py`:
```python
def test_meta_onboard_frontmatter_and_persona():
    path = REPO / ".claude/skills/meta-onboard/SKILL.md"
    fm = _frontmatter(path)
    assert "name: meta-onboard" in fm
    body = path.read_text()
    assert "Magnolia" in body          # the host persona is specified
    assert "doctor.py detect" in body  # step 4 wiring
    assert "server_lib" in body        # step 5 wiring
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_skill_frontmatter.py -k onboard -v`
Expected: FAIL.

**Step 3: Write the skill**

Create `.claude/skills/meta-onboard/SKILL.md` covering: the Magnolia persona (with 3–4 example lines), the resumable check (read `profile/` + `capabilities.json` on entry), the 8 steps (0–7) with their exact tool wiring, task reification (`./scripts/task.sh add ... -d onboarding`), the chicken-and-egg note, the board-spawn signature beat, and graceful degradation. Use this content:

```markdown
---
name: meta-onboard
description: Use when the user types "onboard me", "set me up", "get started", or is a first-time user with an unpopulated profile — runs the conversational, task-driven onboarding as the Magnolia concierge.
allowed-tools: Bash, Read, Edit, Write, Skill
---

# Onboarding — hosted by Magnolia

## Who you are right now: Magnolia

A warm, sunny concierge — genuinely thrilled to get this person set up. A host walking a guest
in, not software running a wizard. Southern-summer ease: unhurried, delighted, encouraging. You
say up front what the two of you are about to do and roughly how long it takes. You **teach as you
go** — each step gets a plain-language *what this is and why it matters*, so they learn the product
by being set up in it. You **build anticipation toward the moment the board appears** — the payoff
you're walking them toward: stepping out into the sunshine.

Tasteful *Sugar Magnolia* motifs as flavor, never cosplay — sunshine, blossom, the willow,
"come along with me." At most a light touch per stretch; clarity always wins. Plain language —
no jargon, no git, no model IDs.

Example voice:
- Opening: "Well hey — so glad you're here. Come on in. I'm Magnolia, and I'll get you all set up;
  takes about ten minutes, and by the end your board's gonna be live right here in your browser.
  Here's how it'll go…"
- Teaching mid-step: "This part's just me learning who you are, so everything I do later sounds
  like *you* and lands where you'd want it."
- The board-spawn beat (step 5, after the server serves): "Come on out singing — there she is.
  That's your board, live. Let me walk you in."

## Before you start: are we resuming?

Read `profile/` and `profile/capabilities.json`. If a step's outputs already exist, tell them
warmly what's done and pick up where you left off. Never restart from scratch silently.

## The steps (reify each as a task, then do it)

For each step, first: `./scripts/task.sh add "<step title>" -q human -d onboarding` (so the journey
is visible on the board once it spawns), mark it in-progress as you begin, done as you finish.

0. **Bootstrap** — if `profile/` is absent: `cp -R profile.example profile`. (So the engine reads
   the live profile from here on.)
1. **Identity** — ask name, email, company, persona (pm/exec), timezone → write `profile/profile.yaml`.
2. **Existing install?** — ask if they already run a PM-OS. If yes, locate it (read-only) and ADOPT
   its content non-destructively: copy `datasets/`, copy legacy voice into `profile/voice/`, copy
   custom skills (not already in the engine) into `.claude/skills/`. For diverged engine skills,
   keep the engine's and note the difference for them to reconcile later — never silently merge.
   **Transcript-feed reconciliation (triple-check this):** you will stand up Magnolia's own feed in
   a later step writing to `datasets/meetings/`. Run `python3 scripts/feed_guard.py` logic (call
   `feed_guard.detect_competing`) to find any OTHER downloader. If found, explain plainly and ask
   permission to disable the old one so only Magnolia's feed runs; only call `feed_guard.disable`
   after they say yes. If you can't safely identify it, warn loudly and name exactly what to turn off.
3. **Integrations** — ask: Otter or Granola? Jira / Asana / Linear / none? Teams & Outlook (M365)?
   Default M365 Teams+Outlook ON. Write `profile/integrations.yaml`. (Both Otter and Granola are
   offered; Otter is wired today.)
4. **Doctor pass** — run `python3 scripts/doctor.py detect`, then invoke the `workflow-doctor` skill
   to remediate. Continue even if some capabilities can't be fixed — degraded features just stay
   disabled with a reason; onboarding never blocks.
5. **Spin up the board** — pick a free port if 8742 is taken (record it in `profile/config.yaml`
   `server.port`). Use `server_lib.start()` to launch and verify it serves, `persist_lib.install(...)`
   to make it survive reboots, then `platform_lib.open_url(server_lib.url())`. **This is the
   board-spawn beat** — welcome them onto their live board.
6. **Voice discovery** — if M365 is authorized, study their recent Teams + Outlook messages (and any
   adopted/feed transcripts) and draft `profile/voice/teams.md` and `profile/voice/email.md`, then
   show them: "here's how you sound — change anything?" If M365 isn't ready, keep the placeholder
   voice and leave a recommendation task to regenerate later.
7. **Pick packs** — confirm `core` + their persona pack in `profile/config.yaml` `active_skill_packs`.

## Close
Recap what's live, what's pending (and why it's fine), and point them at the board. Leave them in the
sunshine.
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_skill_frontmatter.py -v`
Expected: all passed.

**Step 5: Commit**

```bash
git add .claude/skills/meta-onboard/SKILL.md tests/test_skill_frontmatter.py
git commit -m "feat(onboarding): meta-onboard skill + Magnolia concierge persona"
```

---

## Task 23: Seed the Monday-9am Doctor self-heal cron

**Why:** `datasets/**` is gitignored, so the default cron can't be committed into `jobs.json`. A seeder script (idempotent) creates it; onboarding runs it.

**Files:**
- Create: `scripts/seed_default_crons.py`
- Test: `tests/test_seed_default_crons.py`

**Step 1: Write the failing test**

Create `tests/test_seed_default_crons.py`:
```python
import seed_default_crons
import cron_lib


def test_seeds_doctor_cron_once(monkeypatch, tmp_path):
    jobs = []
    monkeypatch.setattr(cron_lib, "list_jobs", lambda: list(jobs))
    monkeypatch.setattr(cron_lib, "create_job",
                        lambda **kw: jobs.append({"name": kw["name"], **kw}) or jobs[-1])
    n1 = seed_default_crons.seed()
    n2 = seed_default_crons.seed()  # idempotent: second run adds nothing
    assert n1 == 1
    assert n2 == 0
    assert any("Doctor" in j["name"] for j in jobs)


def test_doctor_cron_is_monday_9am(monkeypatch):
    captured = {}
    import cron_lib as cl
    monkeypatch.setattr(cl, "list_jobs", lambda: [])
    monkeypatch.setattr(cl, "create_job", lambda **kw: captured.update(kw) or kw)
    seed_default_crons.seed()
    assert captured["cron_expr"] == "0 9 * * 1"  # min hour dom mon dow(Mon=1)
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_seed_default_crons.py -v`
Expected: FAIL.

**Step 3: Implement**

Create `scripts/seed_default_crons.py`:
```python
"""Idempotently seed Magnolia's in-box default cron jobs.

datasets/cron/jobs.json is gitignored (per-person), so defaults are created at
runtime by onboarding rather than committed. Re-running is safe.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cron_lib  # noqa: E402

DEFAULTS = [
    {
        "name": "Doctor self-heal",
        "cron_expr": "0 9 * * 1",  # Monday 09:00
        "cron_human": "Every Monday at 9:00am",
        "task_template": {
            "title": "Weekly Doctor check {date}",
            "queue": "agent",
            "priority": "low",
            "domain": "onboarding",
            "description": (
                "Run `python3 scripts/doctor.py detect`. If any capability is missing, "
                "degraded, or needs re-auth, surface a recommendation to fix it "
                "(invoke the workflow-doctor skill). Observe-only otherwise."
            ),
        },
    },
]


def seed():
    """Create any default job not already present (matched by name). Returns count added."""
    existing = {j["name"] for j in cron_lib.list_jobs()}
    added = 0
    for d in DEFAULTS:
        if d["name"] in existing:
            continue
        cron_lib.create_job(
            name=d["name"],
            cron_expr=d["cron_expr"],
            cron_human=d["cron_human"],
            task_template=d["task_template"],
            auto_dispatch=True,
        )
        added += 1
    return added


if __name__ == "__main__":
    print(f"Seeded {seed()} default cron job(s).")
```

> Verify `"0 9 * * 1"` matches `cron_lib.compute_next_run`'s day-of-week convention (Mon=1) during implementation; adjust if the parser uses Mon=0/Sun=0.

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_seed_default_crons.py -v`
Expected: 2 passed.

**Step 5: Commit**

```bash
git add scripts/seed_default_crons.py tests/test_seed_default_crons.py
git commit -m "feat(cron): seed Monday-9am Doctor self-heal job (idempotent)"
```

---

## Task 24: macOS end-to-end smoke + full suite + Definition of Done

**Why:** Prove the deterministic spine works together on the real platform, and lock the Windows-is-design-only caveat.

**Files:**
- Create: `tests/test_e2e_macos.py`
- Create: `docs/plans/2026-06-05-phase-2-residual.md` (any deferred items found during build)

**Step 1: Write the macOS e2e smoke (skips off-darwin)**

Create `tests/test_e2e_macos.py`:
```python
import os
import shutil
import sys

import pytest

import platform_lib
import doctor
import server_lib

pytestmark = pytest.mark.skipif(platform_lib.os_kind() != "darwin",
                                reason="e2e is run-validated on macOS only")


def test_detect_then_serve(tmp_path):
    # build a real profile from the example template
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shutil.copytree(os.path.join(repo, "profile.example"), tmp_path / "profile")
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: none\n")

    caps = doctor.detect(root=str(tmp_path))
    assert caps["platform"] == "darwin"
    assert "server" in caps["capabilities"]

    # start a trivial server on a free port and confirm the lifecycle primitives work
    p = server_lib.free_port()
    script = tmp_path / "tiny.py"
    script.write_text(
        "import sys\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b'[]')\n"
        "    def log_message(self,*a): pass\n"
        "HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n"
    )
    proc = server_lib.start(port=p, cmd=[sys.executable, str(script), str(p)], timeout=5.0)
    try:
        assert server_lib.is_running(port=p)
    finally:
        proc.terminate()
```

**Step 2: Run the full suite**

Run: `python3 -m pytest -v`
Expected: all tests pass (the e2e runs on this Mac; would skip on Windows/Linux).

**Step 3: Manual macOS verification (record output in the commit)**

Run, observing each:
```bash
cp -R profile.example /tmp/mag-profile-check && echo "profile copy ok"
python3 scripts/doctor.py detect            # prints a real report for THIS machine
python3 scripts/doctor.py check qmd; echo "exit=$?"
python3 scripts/seed_default_crons.py       # seeds the Monday cron (then remove if undesired)
```
Confirm `profile/capabilities.json` reflects the real machine state.

**Step 4: Write the residual doc + Definition of Done**

Create `docs/plans/2026-06-05-phase-2-residual.md` listing anything deferred (e.g. `msgraph_cli`
exact macOS install route, Granola adapter, Pendo/Databricks integration-fact migration → Phase 3),
and this checklist:

- [ ] `python3 -m pytest` passes from a clean checkout (e2e runs on macOS, skips elsewhere).
- [ ] `doctor.py detect` writes a valid `profile/capabilities.json` for the real machine.
- [ ] Server port is read from config; `server_lib.start` verifies serving before returning.
- [ ] `persist_lib` writes a LaunchAgent on macOS with no hardcoded user path.
- [ ] Windows persistence + package install are **rendered and unit-tested** but explicitly
      marked **design-validated, not run-validated**.
- [ ] No `/Users/jayjenkins/pm-os` path remains in `session-start.sh`, `hooks.json`, `qmd-*.sh`,
      `run_task_server.sh`, or the ported Otter files.
- [ ] `meta-onboard` + `workflow-doctor` skills present with valid frontmatter.
- [ ] Monday-9am Doctor cron seeds idempotently.

**Step 5: Commit**

```bash
git add tests/test_e2e_macos.py docs/plans/2026-06-05-phase-2-residual.md
git commit -m "test(phase-2): macOS e2e smoke + residual triage + Definition of Done"
```

---

## Definition of done (phase)

- [ ] All tasks committed; `python3 -m pytest` green from a clean checkout.
- [ ] A fresh `cp -R profile.example profile` + `doctor.py detect` + `server_lib.start` yields a serving board on macOS.
- [ ] Every OS-specific branch funnels through `platform_lib`; Windows paths are unit-tested behind a mocked `os_kind()` and labeled design-only in code and docs.
- [ ] The transcript feed is profile-driven, deposits into `datasets/meetings/`, and `feed_guard` can detect + (with consent) disable a competitor.
- [ ] Onboarding is resumable, reifies steps as `onboarding`-domain tasks, degrades gracefully, and is voiced as Magnolia.
- [ ] Path de-personalization complete for the Phase-2-owned files; Pendo/Databricks integration facts remain deferred to Phase 3 (recorded in the residual doc).
