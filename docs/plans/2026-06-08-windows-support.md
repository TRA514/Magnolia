# Windows Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a Windows teammate onboard, land on their live board, and use the chat panel + agent dispatch.

**Architecture:** Two tiers. Tier 1 (onboarding) is Mac-verifiable and high-confidence: fix the one hard blocker (`task.sh`'s hardcoded brew Python) + two graceful-degrade touches. Tier 2 (chat/dispatch) consolidates the copy-pasted "launch `claude` headless" idiom into one cross-platform seam in `platform_lib`, then applies it at the 3 launch sites + folds in 2 cheap hardcoded-exec fixes. Tier 2 is best-effort and unit-tested against a mocked `os_kind()`, but NOT run-validated (no Windows box).

**Tech Stack:** Python 3 (stdlib `subprocess`, `shutil`, `os`), bash (`task.sh`), pytest.

**Design:** see `docs/plans/2026-06-08-windows-support-design.md`.

**Gates (run before every code commit):** `python3 -m pytest` · `python3 scripts/card_schema.py` · `python3 -m pytest tests/test_engine_no_jay.py`

---

## TIER 1 — Onboarding (high confidence)

### Task 1: `task.sh` resolves Python from PATH

**Files:**
- Modify: `scripts/task.sh:23`

**Step 1: Make the change**

Replace line 23:
```bash
exec /opt/homebrew/bin/python3 "$SCRIPT_DIR/task_cli.py" "$@"
```
with a PATH-resolved interpreter (works on macOS, Linux, and Git-Bash-on-Windows):
```bash
PYTHON="$(command -v python3 || command -v python)"
if [ -z "$PYTHON" ]; then
  echo "task.sh: no python3/python found on PATH" >&2
  exit 127
fi
exec "$PYTHON" "$SCRIPT_DIR/task_cli.py" "$@"
```

**Step 2: Smoke-test on this Mac (no unit test for a shell one-liner)**

Run: `./scripts/task.sh list --json | head -c 80`
Expected: valid JSON output (proves the resolved interpreter still runs `task_cli.py` with no regression).

**Step 3: Commit**

```bash
git add scripts/task.sh
git commit -m "fix(windows): task.sh resolves python from PATH, not hardcoded brew path"
```

---

### Task 2: Doctor marks `qmd` optional

**Files:**
- Modify: `scripts/doctor.py` (the `_LOCAL_TOOLS` dict, `qmd` entry)
- Test: `tests/test_doctor.py`

**Step 1: Write the failing test**

In `tests/test_doctor.py`:
```python
def test_qmd_is_not_required():
    # qmd powers semantic search; on Windows it likely won't install, and that
    # must read as "optional, degrades to keyword search", never as "broken".
    doc = doctor.detect()
    qmd = doc["capabilities"]["qmd"]
    assert qmd.get("required") is False
```
(Match the import/fixture style already used in `tests/test_doctor.py`.)

**Step 2: Run, verify it fails**

Run: `python3 -m pytest tests/test_doctor.py::test_qmd_is_not_required -v`
Expected: FAIL (qmd currently has no `required` key).

**Step 3: Implement**

In `scripts/doctor.py`, change the `qmd` entry in `_LOCAL_TOOLS`:
```python
    "qmd":        {"required": False,
                   "detail": "powers semantic search; optional (keyword search works without it)",
                   "remedy": "brew install qmd"},
```
(`detect()` already copies `required`/`detail` into the capability when present — no other change needed.)

**Step 4: Run, verify it passes**

Run: `python3 -m pytest tests/test_doctor.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/doctor.py tests/test_doctor.py
git commit -m "fix(windows): mark qmd optional so its absence degrades, not breaks"
```

---

### Task 3: Onboarding note for Windows reboot-persistence

**Files:**
- Modify: `.claude/skills/meta-onboard/SKILL.md` (Step 5)

**Step 1: Make the change**

In Step 5, after the existing sentence about the `activated` flag, add:
> On Windows, auto-start-on-reboot uses Task Scheduler and is **not set up automatically** — the board runs now; tell them it's a quick optional follow-up later (the `persist_lib.install` return carries the PowerShell command, but never auto-run it on their first session). Don't block.

**Step 2: Verify the denylist gate still passes (doc change under `.claude/`)**

Run: `python3 -m pytest tests/test_engine_no_jay.py -v`
Expected: PASS.

**Step 3: Commit**

```bash
git add .claude/skills/meta-onboard/SKILL.md
git commit -m "docs(windows): onboarding notes reboot-persistence is optional on Windows"
```

---

## TIER 2 — Chat + dispatch (best-effort, unverified on Windows)

### Task 4: Cross-platform `claude`-launch seam in `platform_lib`

**Files:**
- Modify: `scripts/platform_lib.py` (add `import shutil`, `import signal`; add 4 helpers)
- Test: `tests/test_platform_lib.py`

**Step 1: Write the failing tests**

In `tests/test_platform_lib.py` (mock `os_kind` the same way existing tests there do):
```python
def test_headless_claude_env_strips_claude_vars():
    base = {"CLAUDE_CODE_X": "1", "CMUX_CLAUDE_Y": "1", "PATH": "/usr/bin", "HOME": "/h"}
    env = platform_lib.headless_claude_env(base=base)
    assert not any(k.startswith(("CLAUDE", "CMUX_CLAUDE")) for k in env)
    assert "HOME" in env

def test_headless_claude_env_keeps_windows_path_untouched(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "windows")
    base = {"PATH": r"C:\Windows;C:\tools"}
    env = platform_lib.headless_claude_env(base=base)
    assert env["PATH"] == r"C:\Windows;C:\tools"   # no unix dirs, no ":" mangling

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
```

**Step 2: Run, verify they fail**

Run: `python3 -m pytest tests/test_platform_lib.py -k "claude or process_group" -v`
Expected: FAIL (helpers not defined).

**Step 3: Implement in `scripts/platform_lib.py`**

```python
import shutil
import signal

# POSIX install locations to prefer ahead of the inherited PATH.
_CLAUDE_PREPEND_DIRS = [
    os.path.join(os.path.expanduser("~"), ".local", "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
]


def headless_claude_env(base=None):
    """Env for a headless `claude` subprocess, cross-platform.

    Strips CLAUDE*/CMUX_CLAUDE* (avoid nested-session detection). On POSIX,
    prepends common claude install dirs that actually exist. On Windows the
    inherited PATH is kept verbatim (claude resolves via shutil.which/PATHEXT) —
    never inject unix dirs or ':'-join onto a ';'-separated PATH.
    """
    src = os.environ if base is None else base
    env = {k: v for k, v in src.items()
           if not k.startswith(("CLAUDE", "CMUX_CLAUDE"))}
    cur = env.get("PATH", os.defpath)
    if os_kind() != "windows":
        prepend = [d for d in _CLAUDE_PREPEND_DIRS if os.path.isdir(d)]
        if prepend:
            env["PATH"] = os.pathsep.join(prepend + [cur])
    return env


def resolve_claude(path=None):
    """Absolute path to the claude CLI, or the bare name as a last resort.

    shutil.which honors PATHEXT on Windows (finds claude.exe / claude.cmd).
    """
    found = shutil.which("claude", path=path)
    if found:
        return found
    for d in _CLAUDE_PREPEND_DIRS:
        cand = os.path.join(d, "claude")
        if os.path.isfile(cand):
            return cand
    return "claude"


def process_group_kwargs():
    """Popen kwargs giving the child its own killable process group."""
    if os_kind() == "windows":
        # getattr so this evaluates on macOS (attr is Windows-only) for mocked tests.
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)}
    return {"start_new_session": True}


def kill_process_group(proc):
    """Best-effort kill of a child and its group, cross-platform."""
    try:
        if os_kind() == "windows":
            proc.terminate()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
```

**Step 4: Run, verify pass**

Run: `python3 -m pytest tests/test_platform_lib.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/platform_lib.py tests/test_platform_lib.py
git commit -m "feat(windows): cross-platform claude-launch seam in platform_lib"
```

---

### Task 5: Apply the seam in `chat_runner.py`

**Files:**
- Modify: `scripts/chat_runner.py` (`_chat_env`, `_spawn`, `_kill_process_group`, and where `build_chat_cmd` output is spawned)

**Step 1: Implementation**

- Replace the body of `_chat_env()` with `return platform_lib.headless_claude_env()` (keep the function name as a thin seam; import `platform_lib` if not already).
- At the spawn point, resolve the binary: before `subprocess.Popen`, set `cmd = [platform_lib.resolve_claude()] + list(cmd[1:])` if `cmd and cmd[0] == "claude"`.
- In `_spawn`, replace `start_new_session=True` with `**platform_lib.process_group_kwargs()`.
- Make `_kill_process_group` delegate to `platform_lib.kill_process_group(proc)` (it currently assumes POSIX `os.killpg`).

**Step 2: Run existing chat tests**

Run: `python3 -m pytest tests/test_chat_runner_persist.py -v`
Expected: PASS (no behavior change on macOS).

**Step 3: Commit**

```bash
git add scripts/chat_runner.py
git commit -m "feat(windows): chat_runner uses the cross-platform claude-launch seam"
```

---

### Task 6: Apply the seam in `task_dispatch.py` (incl. the `script -q` Windows branch)

**Files:**
- Modify: `scripts/task_dispatch.py` (the spawn block ~796-820)

**Step 1: Implementation**

Replace the wrapper + env + Popen block with:
```python
claude_cmd, claude_session_id = build_claude_cmd(prompt, model, tools_str, max_turns)
claude_cmd[0] = platform_lib.resolve_claude()

if platform_lib.os_kind() == "windows":
    # No `script` (pty) on Windows: run claude directly and tee stdout to the
    # output_file ourselves (the pty is what wrote it on POSIX).
    cmd = claude_cmd
    stdout_target = open(output_file, "wb")
else:
    cmd = ["script", "-q", output_file] + claude_cmd
    stdout_target = subprocess.DEVNULL

env = platform_lib.headless_claude_env()

try:
    proc = subprocess.Popen(
        cmd,
        stdout=stdout_target,
        stderr=subprocess.DEVNULL,
        cwd=PM_OS_DIR,
        env=env,
        **platform_lib.process_group_kwargs(),
    )
except FileNotFoundError:
    log("ERROR: 'claude' (or 'script' on POSIX) not found in PATH", task_id=task_id)
    return {"task_id": task_id, "success": False, "output": None, "error": "claude not found"}
```
- `import platform_lib` at top if not present.
- Where the process is later killed, route through `platform_lib.kill_process_group(proc)` if it currently uses `os.killpg`.

**Step 2: Run dispatch tests**

Run: `python3 -m pytest tests/ -k dispatch -v`
Expected: PASS on macOS (POSIX branch unchanged in behavior).

**Step 3: Commit**

```bash
git add scripts/task_dispatch.py
git commit -m "feat(windows): task_dispatch drops script-pty on Windows, uses launch seam"
```

---

### Task 7: Apply the seam in `judge.py`

**Files:**
- Modify: `scripts/judge.py` (`run_claude`)

**Step 1: Implementation**

In `run_claude`, replace the hand-rolled env block with `env = platform_lib.headless_claude_env()` and change `cmd = ["claude", ...]` to `cmd = [platform_lib.resolve_claude(), ...]`. Add `import platform_lib` if needed. Leave the FileNotFoundError/timeout handling as-is.

**Step 2: Run judge tests**

Run: `python3 -m pytest tests/ -k judge -v`
Expected: PASS.

**Step 3: Commit**

```bash
git add scripts/judge.py
git commit -m "feat(windows): judge uses the cross-platform claude-launch seam"
```

---

### Task 8: Fold in the two cheap hardcoded-exec fixes

**Files:**
- Modify: `scripts/parse_task_input.py:344` and `_claude_bin`/`call_claude`
- Modify: `scripts/jira_publish.py` (~225-231)

**Step 1: Implementation**

- `parse_task_input.py:344` — replace `"/opt/homebrew/bin/python3"` with `sys.executable` (import `sys` if needed):
  ```python
  result = subprocess.run(
      [sys.executable, os.path.join(pm_os_dir, "scripts", "task_cli.py"), "add"] + cli_args,
      ...
  ```
- `parse_task_input.py` `call_claude` — replace the env block with `env = platform_lib.headless_claude_env()` and `_claude_bin()` with `platform_lib.resolve_claude()` (import `platform_lib`).
- `jira_publish.py` — replace the env block with `platform_lib.headless_claude_env()` and the `claude_bin` resolution (which has NO PATH fallback today → 100% Windows crash) with `claude_bin = platform_lib.resolve_claude()`.

**Step 2: Run the full suite**

Run: `python3 -m pytest tests/ -k "parse_task or jira" -v`
Expected: PASS.

**Step 3: Commit**

```bash
git add scripts/parse_task_input.py scripts/jira_publish.py
git commit -m "fix(windows): replace hardcoded brew python/claude paths with portable resolution"
```

---

## Final verification (before opening the PR)

1. **Three green gates:**
   - `python3 -m pytest` → all pass
   - `python3 scripts/card_schema.py` → `registry.json OK`
   - `python3 -m pytest tests/test_engine_no_jay.py` → pass
2. **Onboarding smoke (Mac):** `./scripts/task.sh list --json` returns JSON; `python3 scripts/doctor.py detect` shows `qmd` as optional.
3. **Open PR** off `main` (do NOT merge). Body: the two-tier summary + the explicit "Tier 2 is unverified on Windows; teammate's run is the live test" caveat + Mac regression checklist for Jay.
