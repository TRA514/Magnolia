# Windows Runtime Portability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Magnolia engine's runtime work natively on Windows by routing every POSIX-shaped subprocess/PATH call through the `platform_lib.py` seam — fixing the `[WinError 193]`/`[WinError 2]` class of bug the first Windows beta user hit, across the whole system, without adding a Git Bash dependency.

**Architecture:** Approach C — stop the Python→bash→python hop (`task.sh`/`task-extract-meetings.sh` invoked from Python become direct `sys.executable` calls; the `.sh` files survive as thin human-CLI shims). Consolidate three hand-rolled colon-`PATH` blocks onto the already-correct `platform_lib.headless_claude_env()`. Resolve/guard external tools (`qmd`, `fswatch`, `pandoc`, `osascript`) via `shutil.which` with graceful skip. Route the board's file-open through a new `platform_lib.open_file_cmd()`.

**Tech Stack:** Python 3.12, `subprocess`, `pathlib`, `shutil.which`, pytest with `monkeypatch` (mock `platform_lib.os_kind()` for Windows branches — design-validated, no Windows box).

**Design doc:** `docs/plans/2026-06-11-windows-runtime-portability-design.md`

**Green gates (run before EVERY commit that touches code):**
```bash
python3 -m pytest -q
python3 scripts/card_schema.py          # expect: registry.json OK
python3 -m pytest tests/test_engine_no_jay.py -q
```

---

## Task 1: `platform_lib` seam — `resolve_tool()` + `open_file_cmd()`

**Files:**
- Modify: `scripts/platform_lib.py`
- Test: `tests/test_platform_lib.py`

**Step 1: Write the failing tests**

Add to `tests/test_platform_lib.py`:

```python
def test_resolve_tool_found(monkeypatch):
    monkeypatch.setattr(platform_lib.shutil, "which", lambda n: "/usr/bin/qmd")
    assert platform_lib.resolve_tool("qmd") == "/usr/bin/qmd"

def test_resolve_tool_missing_returns_none(monkeypatch):
    monkeypatch.setattr(platform_lib.shutil, "which", lambda n: None)
    monkeypatch.setattr(platform_lib.os.path, "isfile", lambda p: False)
    assert platform_lib.resolve_tool("qmd") is None

def test_open_file_cmd_darwin(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "darwin")
    assert platform_lib.open_file_cmd("/x/y.docx") == ["open", "/x/y.docx"]

def test_open_file_cmd_windows(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "windows")
    assert platform_lib.open_file_cmd("C:/x/y.docx") == ["cmd", "/c", "start", "", "C:/x/y.docx"]

def test_open_file_cmd_linux(monkeypatch):
    monkeypatch.setattr(platform_lib, "os_kind", lambda: "linux")
    assert platform_lib.open_file_cmd("/x/y.docx") == ["xdg-open", "/x/y.docx"]
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_platform_lib.py -q`
Expected: FAIL (`AttributeError: module 'platform_lib' has no attribute 'resolve_tool'`)

**Step 3: Implement**

In `scripts/platform_lib.py`, add after `resolve_claude()` (~line 108):

```python
def resolve_tool(name):
    """Absolute path to a CLI tool, or None if not found.

    Honors PATHEXT on Windows via shutil.which. Unlike resolve_claude (which
    falls back to the bare name because claude is required), this returns None
    when the tool is genuinely absent, so callers can gracefully SKIP an
    optional tool (qmd, etc.) instead of crashing with WinError 2.
    """
    found = shutil.which(name)
    if found:
        return found
    for d in _CLAUDE_PREPEND_DIRS:
        cand = os.path.join(d, name)
        if os.path.isfile(cand):
            return cand
    return None


def open_file_cmd(path):
    """OS-correct argv to open a file in the user's default handler."""
    kind = os_kind()
    if kind == "darwin":
        return ["open", path]
    if kind == "windows":
        # empty "" is the title arg for start; required when the path is quoted
        return ["cmd", "/c", "start", "", path]
    return ["xdg-open", path]
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_platform_lib.py -q`
Expected: PASS

**Step 5: Run gates + commit**

```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
git add scripts/platform_lib.py tests/test_platform_lib.py
git commit -m "feat(platform): add resolve_tool() + open_file_cmd() seams"
```

---

## Task 2: Port `task-extract-meetings.sh` core to Python + reduce `.sh` to a shim

**Files:**
- Create: `scripts/task_extract_meetings.py`
- Modify: `scripts/task-extract-meetings.sh` (becomes a thin shim)
- Test: `tests/test_task_extract_meetings.py`

**Step 1: Write the failing tests**

Create `tests/test_task_extract_meetings.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import task_extract_meetings as tem  # noqa: E402


def test_resolve_relative_path(tmp_path, monkeypatch):
    monkeypatch.setattr(tem, "PM_OS_DIR", tmp_path)
    f = tmp_path / "datasets" / "meetings" / "x.md"
    f.parent.mkdir(parents=True)
    f.write_text("hi")
    assert tem.resolve_path("datasets/meetings/x.md") == f.resolve()

def test_resolve_absolute_posix_path(tmp_path, monkeypatch):
    monkeypatch.setattr(tem, "PM_OS_DIR", tmp_path)
    f = tmp_path / "a.md"; f.write_text("hi")
    assert tem.resolve_path(str(f)) == f.resolve()

def test_resolve_windows_drive_path_not_doubled(tmp_path, monkeypatch):
    # The bug: bash treated C:\... as relative and prepended PM_OS_DIR.
    # pathlib must treat a drive-absolute path as absolute (no doubling).
    monkeypatch.setattr(tem, "PM_OS_DIR", tmp_path)
    p = tem.resolve_path("C:/Users/Josh/x.md")
    assert str(p).replace("\\", "/").endswith("Users/Josh/x.md")
    assert "datasets" not in str(p)  # PM_OS_DIR was NOT prepended

def test_processed_idempotency(tmp_path, monkeypatch):
    monkeypatch.setattr(tem, "PM_OS_DIR", tmp_path)
    pf = tmp_path / "datasets" / "tasks" / "_processed-meetings.txt"
    pf.parent.mkdir(parents=True)
    monkeypatch.setattr(tem, "PROCESSED_FILE", pf)
    assert tem.is_processed("datasets/meetings/x.md") is False
    tem.mark_processed("datasets/meetings/x.md")
    assert tem.is_processed("datasets/meetings/x.md") is True
    tem.mark_processed("datasets/meetings/x.md")  # second call no-op
    assert pf.read_text().count("x.md") == 1
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_task_extract_meetings.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'task_extract_meetings'`)

**Step 3: Implement `scripts/task_extract_meetings.py`**

Mirror the `.sh` exactly; `resolve_path`/`is_processed`/`mark_processed` are module-level so tests can monkeypatch `PM_OS_DIR`/`PROCESSED_FILE`. The `claude -p` prompt is copied verbatim from the `.sh` (the embedded `./scripts/task.sh` references stay — Claude runs those in its own Bash tool).

```python
#!/usr/bin/env python3
"""Extract tasks from meeting transcripts via headless claude.

Python port of task-extract-meetings.sh (the .sh is now a thin shim over this).
Invoked by transcript_post.run_downstream via sys.executable so the engine never
shells Python->bash->python. Path math uses pathlib so Windows drive-absolute
paths (C:\\...) are handled natively — no more PM_OS_DIR doubling.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_lib  # noqa: E402

PM_OS_DIR = Path(__file__).resolve().parent.parent
PROCESSED_FILE = PM_OS_DIR / "datasets" / "tasks" / "_processed-meetings.txt"


def resolve_path(filepath):
    """Resolve a transcript path to absolute. Relative paths are taken from
    PM_OS_DIR; absolute paths (POSIX / or a Windows drive) are used as-is."""
    p = Path(filepath)
    if not p.is_absolute():
        p = Path(PM_OS_DIR) / p
    return p.resolve()


def _normalized_key(file):
    return str(file).replace("\\", "/").split("datasets/meetings/")[-1]


def is_processed(file):
    if not Path(PROCESSED_FILE).exists():
        return False
    key = _normalized_key(file)
    return key in Path(PROCESSED_FILE).read_text(encoding="utf-8")


def mark_processed(file):
    Path(PROCESSED_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(PROCESSED_FILE).touch(exist_ok=True)
    if not is_processed(file):
        with open(PROCESSED_FILE, "a", encoding="utf-8") as fh:
            fh.write(str(file) + "\n")


def _prompt(filepath):
    return f"""Read the meeting transcript at {filepath}.

BEFORE extracting tasks, run: ./scripts/task.sh list --json
This gives you all existing open tasks. For EACH potential new task, check if a semantically similar task already exists (same underlying work, even if worded differently). If a duplicate exists:
- Do NOT create a new task
- Instead, run: ./scripts/task.sh update TASK-NNNN --comment "Additional context from {filepath}: <new details>"
- Append-only: add new context, never remove existing context
- If priority should escalate, update that too

Only create a new task if no existing task covers the same work.

Use the task-extract-from-meeting skill at .claude/skills/task-extract-from-meeting/SKILL.md to identify action items and create tasks. For each action item, use ./scripts/task.sh add with appropriate --queue, --priority, --domain, --source-meeting flags. Apply the auto-queue rules: human decisions -> human queue, autonomous work -> agent queue, joint work -> collab queue, delegated to others -> waiting queue."""


def process_transcript(filepath):
    target = resolve_path(filepath)
    if not target.is_file():
        print(f"[ERROR] File not found: {target}")
        return 1
    relative = str(target).replace(str(Path(PM_OS_DIR)) + os.sep, "")
    relative = relative.replace("\\", "/")
    if is_processed(relative):
        print(f"[SKIP] Already processed: {relative}")
        return 0
    print(f"[PROCESSING] {relative}")

    claude = platform_lib.resolve_claude()
    env = platform_lib.headless_claude_env()
    with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
        err_path = tf.name
    try:
        with open(err_path, "w") as errf:
            result = subprocess.run(
                [claude, "-p", _prompt(target),
                 "--allowedTools", "Bash(*),Read(*),Write(*)",
                 "--max-turns", "20"],
                cwd=str(PM_OS_DIR), env=env, stderr=errf,
            )
        stderr_text = Path(err_path).read_text(encoding="utf-8", errors="ignore")
        if result.returncode == 0:
            if "cannot be launched inside another Claude Code session" in stderr_text:
                print(f"[ERROR] Nested Claude session detected for: {relative} (not marking as processed)")
                sys.stderr.write(stderr_text)
            else:
                mark_processed(relative)
                print(f"[DONE] {relative}")
        else:
            print(f"[ERROR] claude exited non-zero for: {relative} (not marking as processed)")
            sys.stderr.write(stderr_text)
    finally:
        Path(err_path).unlink(missing_ok=True)
    return 0


def main(argv):
    if not argv:
        print("Usage: task_extract_meetings.py <transcript-path> | --all-unprocessed")
        return 1
    if argv[0] == "--all-unprocessed":
        meetings = Path(PM_OS_DIR) / "datasets" / "meetings"
        files = sorted([p for p in meetings.rglob("*") if p.suffix in (".md", ".txt")])
        if not files:
            print(f"[INFO] No .md or .txt files found under {meetings}")
        for f in files:
            process_transcript(str(f))
        return 0
    return process_transcript(argv[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

**Step 4: Reduce the `.sh` to a shim**

Replace the entire contents of `scripts/task-extract-meetings.sh` with:

```bash
#!/usr/bin/env bash
# task-extract-meetings.sh — thin shim over task_extract_meetings.py.
# The real implementation is Python so the engine never shells Python->bash->python.
# This shim keeps the human CLI entrypoint and the docs working.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(command -v python3 || command -v python)"
if [ -z "$PYTHON" ]; then
  echo "task-extract-meetings.sh: no python3/python found on PATH" >&2
  exit 127
fi
exec "$PYTHON" "$SCRIPT_DIR/task_extract_meetings.py" "$@"
```

**Step 5: Run tests to verify pass**

Run: `python3 -m pytest tests/test_task_extract_meetings.py -q`
Expected: PASS

**Step 6: Run gates + commit**

```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
git add scripts/task_extract_meetings.py scripts/task-extract-meetings.sh tests/test_task_extract_meetings.py
git commit -m "feat(transcripts): port task-extract-meetings to Python; .sh now a shim"
```

---

## Task 3: `transcript_post.py` — call Python directly, consolidate env, guard qmd

**Files:**
- Modify: `scripts/transcript_post.py`
- Test: `tests/test_transcript_post.py` (create if absent)

**Step 1: Write the failing tests**

Create/extend `tests/test_transcript_post.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import transcript_post  # noqa: E402

def test_hook_env_delegates_to_platform_lib(monkeypatch):
    sentinel = {"PATH": "X", "FOO": "bar"}
    monkeypatch.setattr(transcript_post.platform_lib, "headless_claude_env", lambda: sentinel)
    assert transcript_post._hook_env() is sentinel

def test_qmd_skipped_when_absent(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(transcript_post.platform_lib, "resolve_tool", lambda n: None)
    monkeypatch.setattr(transcript_post.subprocess, "Popen",
                        lambda *a, **k: calls.append(a[0]))
    monkeypatch.setattr(transcript_post.profile_lib, "PM_OS_DIR", str(tmp_path))
    transcript_post._run_qmd_index(transcript_post._hook_env(),
                                   tmp_path / "logs", transcript_post._null_log())
    assert calls == []  # qmd absent -> no Popen
```

**Step 2: Run to verify fail**

Run: `python3 -m pytest tests/test_transcript_post.py -q`
Expected: FAIL (`AttributeError: module 'transcript_post' has no attribute 'platform_lib'` / `_run_qmd_index`)

**Step 3: Implement**

In `scripts/transcript_post.py`:

1. Add `import platform_lib` next to `import profile_lib` (line ~10).
2. Replace `_hook_env()` (lines 27-33) body with:
```python
def _hook_env():
    return platform_lib.headless_claude_env()
```
3. Replace the task-extract `Popen` block (lines 60-67) with a direct Python call:
```python
    task_extract = str(SCRIPT_DIR / "task_extract_meetings.py")
    try:
        subprocess.Popen([sys.executable, task_extract, final_path],
                         cwd=str(profile_lib.PM_OS_DIR), env=env,
                         stdout=open(log_dir / "task-extract.log", "a"),
                         stderr=subprocess.STDOUT,
                         **platform_lib.process_group_kwargs())
        log.info("  Triggered task extraction for %s", final_path)
    except Exception as exc:
        log.warning("  Task extraction hook failed: %s", exc)
```
4. Extract the qmd hook (lines 68-75) into a helper and guard it with `resolve_tool`:
```python
def _run_qmd_index(env, log_dir, log):
    qmd = platform_lib.resolve_tool("qmd")
    if not qmd:
        log.info("  qmd not found — skipping index update (semantic search optional)")
        return
    try:
        subprocess.Popen([qmd, "update", "-c", "meetings_product"],
                         cwd=str(profile_lib.PM_OS_DIR), env=env,
                         stdout=open(log_dir / "qmd-index.log", "a"),
                         stderr=subprocess.STDOUT,
                         **platform_lib.process_group_kwargs())
        log.info("  Triggered qmd index update (meetings_product)")
    except Exception as exc:
        log.warning("  QMD index update hook failed: %s", exc)
```
   …and call `_run_qmd_index(env, log_dir, log)` where the inline block was.

> Note: `start_new_session=True` is replaced by `**platform_lib.process_group_kwargs()` (the cross-platform detach — `CREATE_NEW_PROCESS_GROUP` on Windows).

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_transcript_post.py -q`
Expected: PASS

**Step 5: Gates + commit**

```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
git add scripts/transcript_post.py tests/test_transcript_post.py
git commit -m "fix(transcripts): call task-extract via sys.executable; consolidate env; guard qmd"
```

---

## Task 4: `task_dispatch.py` — invoke `task_cli.py` via `sys.executable`, not `task.sh`

**Files:**
- Modify: `scripts/task_dispatch.py` (line 49 const; lines 156, 970)
- Test: `tests/test_task_dispatch_windows.py` (create)

**Step 1: Write the failing test**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import task_dispatch  # noqa: E402

def test_actionable_query_uses_python_not_bash(monkeypatch):
    captured = {}
    class R:
        returncode = 0
        stdout = "[]"
    def fake_run(cmd, **k):
        captured["cmd"] = cmd
        return R()
    monkeypatch.setattr(task_dispatch.subprocess, "run", fake_run)
    task_dispatch.get_actionable_tasks()
    assert captured["cmd"][0] == sys.executable
    assert captured["cmd"][1].endswith("task_cli.py")
    assert not any(str(c).endswith("task.sh") for c in captured["cmd"])
```
(Confirm the function name at line ~152; adjust `get_actionable_tasks` if it differs.)

**Step 2: Run to verify fail**

Run: `python3 -m pytest tests/test_task_dispatch_windows.py -q`
Expected: FAIL (cmd[0] is `TASK_SH`, not `sys.executable`)

**Step 3: Implement**

In `scripts/task_dispatch.py`:
- Line 49, add alongside `TASK_SH`:
```python
TASK_CLI = os.path.join(PM_OS_DIR, "scripts", "task_cli.py")
```
- Line 156: `[TASK_SH, "list", "--queue", queue, "--json"]` → `[sys.executable, TASK_CLI, "list", "--queue", queue, "--json"]`
- Line 166 log message: `f"ERROR: task_cli.py not found at {TASK_CLI}"`
- Line 970: `[TASK_SH, "agent:fail", task_id, "--error", error_msg]` → `[sys.executable, TASK_CLI, "agent:fail", task_id, "--error", error_msg]`
- Leave `TASK_SH` defined only if still referenced elsewhere; otherwise remove it. (`grep -n TASK_SH scripts/task_dispatch.py` after edits — remove the const if unused.)

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_task_dispatch_windows.py -q`
Expected: PASS

**Step 5: Gates + commit**

```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
git add scripts/task_dispatch.py tests/test_task_dispatch_windows.py
git commit -m "fix(dispatch): call task_cli.py via sys.executable, drop task.sh hop"
```

---

## Task 5: Consolidate the colon-`PATH` blocks in `cron_lib.py` + `task_server.py`

**Files:**
- Modify: `scripts/cron_lib.py` (~337-345), `scripts/task_server.py` (~970-980)
- Test: `tests/test_cron_lib.py` (extend or create)

**Step 1: Write the failing test**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import cron_lib  # noqa: E402

def test_auto_dispatch_uses_headless_env(monkeypatch):
    seen = {}
    monkeypatch.setattr(cron_lib.platform_lib, "headless_claude_env",
                        lambda: {"PATH": "SENTINEL"})
    def fake_popen(cmd, **k):
        seen["env"] = k.get("env"); 
        class P: pass
        return P()
    monkeypatch.setattr(cron_lib.subprocess, "Popen", fake_popen)
    cron_lib._auto_dispatch("TASK-9999")
    assert seen["env"]["PATH"] == "SENTINEL"  # no hand-rolled colon PATH
```
(Ensure `cron_lib` imports `platform_lib`; if not, that's part of the fix.)

**Step 2: Run to verify fail**

Run: `python3 -m pytest tests/test_cron_lib.py -q`
Expected: FAIL (env PATH is the hand-rolled colon string, not SENTINEL)

**Step 3: Implement**

- `cron_lib.py` `_auto_dispatch`: ensure `import platform_lib` at top; replace the env-build block (the `{k:v ...}` dict comp + the `env["PATH"] = (...)` colon block) with:
```python
    env = platform_lib.headless_claude_env()
```
- `task_server.py` (~970-980): replace the identical hand-rolled `env = {...}` + `env["PATH"] = (...)` colon block with `env = platform_lib.headless_claude_env()`. Confirm `import platform_lib` is present (it is — used at line ~983 for `process_group_kwargs`).

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_cron_lib.py -q`
Expected: PASS

**Step 5: Gates + commit**

```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
git add scripts/cron_lib.py scripts/task_server.py tests/test_cron_lib.py
git commit -m "fix(env): route cron + task_server PATH through headless_claude_env"
```

---

## Task 6: Graceful guards for the remaining tool calls

**Files:**
- Modify: `scripts/task_lib.py` (~188), `scripts/task_server.py` (~1715), `scripts/otter_sync.py` (`notify`), `scripts/doc_sync_watcher.py` (`watch_local`/`watch_remote`), `scripts/doc_sync.py` (`md_to_docx`/`docx_to_md`)
- Test: `tests/test_windows_guards.py` (create)

**Step 1: Write the failing tests**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import task_lib, otter_sync  # noqa: E402

def test_doc_sync_trigger_uses_sys_executable(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(task_lib.subprocess, "Popen",
                        lambda cmd, **k: seen.setdefault("cmd", cmd))
    task_lib._trigger_doc_sync(str(tmp_path / "a.md"))
    assert seen["cmd"][0] == sys.executable

def test_otter_notify_skips_without_osascript(monkeypatch):
    monkeypatch.setattr(otter_sync.shutil, "which", lambda n: None)
    called = []
    monkeypatch.setattr(otter_sync.subprocess, "run", lambda *a, **k: called.append(a))
    otter_sync.notify("t", "m")
    assert called == []  # no crash, no run
```
(Add `import shutil` to `otter_sync.py` if absent.)

**Step 2: Run to verify fail**

Run: `python3 -m pytest tests/test_windows_guards.py -q`
Expected: FAIL

**Step 3: Implement the guards**

- **`task_lib.py:188`**: `["python3", sync_script, ...]` → `[sys.executable, sync_script, ...]` (add `import sys` if not already imported at top; it usually is).
- **`task_server.py:1714-1727`**: replace the darwin/`xdg-open`/`ghostty` branch with:
```python
    import platform_lib
    if filepath.endswith(".docx") or platform_lib.os_kind() == "windows":
        cmd = platform_lib.open_file_cmd(filepath)
    elif platform_lib.os_kind() == "darwin":
        cmd = ["open", "-na", "Ghostty.app", "--args",
               f"--command=nvim {shlex.quote(filepath)}"]
    else:
        cmd = ["ghostty", f"--command=nvim {shlex.quote(filepath)}"]
    subprocess.Popen(cmd, **platform_lib.process_group_kwargs())
```
   (On Windows there's no Ghostty/nvim assumption — open in the default handler; `.docx` already did on all platforms.)
- **`otter_sync.py` `notify`**: guard top of function:
```python
def notify(title: str, message: str) -> None:
    """Send a macOS notification via osascript (no-op off macOS)."""
    if not shutil.which("osascript"):
        return
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)
```
- **`doc_sync_watcher.py`**: at the top of `watch_local` and `watch_remote`, guard:
```python
    if not shutil.which("fswatch"):
        log("fswatch not found — file-watch disabled on this platform (sync still works on demand)")
        return
```
   (add `import shutil` if absent.)
- **`doc_sync.py`**: add a module-level helper and call it at the top of `md_to_docx` and `docx_to_md`:
```python
def _require_pandoc():
    if not shutil.which("pandoc"):
        raise RuntimeError("pandoc not found — install pandoc to enable Word sync")
```
   (add `import shutil` if absent.) This converts a raw `FileNotFoundError`/`WinError 2` into a clear, actionable error.

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_windows_guards.py -q`
Expected: PASS

**Step 5: Gates + commit**

```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
git add scripts/task_lib.py scripts/task_server.py scripts/otter_sync.py scripts/doc_sync_watcher.py scripts/doc_sync.py tests/test_windows_guards.py
git commit -m "fix(portability): sys.executable + which-guards for python3/osascript/fswatch/pandoc; board open via open_file_cmd"
```

---

## Task 7: Live e2e verification + ship

**Step 1: Full gate sweep**
```bash
python3 -m pytest -q
python3 scripts/card_schema.py            # expect: registry.json OK
python3 -m pytest tests/test_engine_no_jay.py -q
```
Expected: all green.

**Step 2: macOS e2e — prove no regression on the real pipeline**
- Pick (or create) a small meeting transcript under `datasets/meetings/`.
- Run the downstream path the way sync does:
  ```bash
  python3 -c "import sys; sys.path.insert(0,'scripts'); import transcript_post, logging; logging.basicConfig(level=logging.INFO); transcript_post.run_downstream('<path-to-transcript>', 'e2e-test', {}, logging.getLogger())"
  ```
- Confirm `logs/task-extract.log` shows `[PROCESSING]`/`[DONE]`, tasks appear via `./scripts/task.sh list`, and (if `qmd` installed) the qmd log updates — or the clean "qmd not found — skipping" line if not.
- Start the dev board and confirm it renders + the extracted tasks show:
  ```bash
  # per ui/task-board/CLAUDE.md; dev board is :8743 ONLY (never :8742 / ~/pm-os)
  ```
  Open `localhost:8743`, confirm the board loads and the new tasks render.

**Step 3: Note the residual**
Windows branches remain **design-validated** (no Windows box on the dev machine). Capture in the final summary that the one remaining step is a Windows beta re-test (the original reporter).

**Step 4: Finish the branch**
Use `superpowers:finishing-a-development-branch`. Merge authority for this build = **merge to local `main` when green** (do not push unless asked). Confirm gates green on the merge commit.
