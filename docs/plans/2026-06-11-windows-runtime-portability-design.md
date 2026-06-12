# Windows runtime portability — close the POSIX leaks past the `platform_lib` seam

**Date:** 2026-06-11
**Status:** Approved design → implementation
**Origin:** First Windows beta user (Josh Mulvihill) hit `[WinError 193]` and `[WinError 2]` running the Granola → task-extraction pipeline. He patched his local copy; this build fixes the root cause across the system so no future Windows user hits the same class of bug.

## Problem

The beta user saw two errors, but both are symptoms of **one root cause: POSIX assumptions leaking _past_ the `platform_lib.py` OS seam.** The seam already exists (it's how the earlier Windows work fixed the `fcntl` crash), but several runtime code paths bypass it:

- **`WinError 193` — `%1 is not a valid Win32 application`** — `transcript_post.py:61` executes `task-extract-meetings.sh` directly. Windows can't exec a `.sh`.
- **`WinError 2` — `cannot find the file specified` (qmd)** — two causes stacked: `qmd` is invoked by bare name **and** `transcript_post.py:31` builds `PATH` with hardcoded `:` separators + `/opt/homebrew/bin`, which corrupts `PATH` on Windows so nothing resolves.

The same class of breakage recurs in paths the beta user never reached:
- **Agent dispatch** (`task_dispatch.py:156,970`) runs `task.sh` directly — every agent task hits this.
- **Cron** (`cron_lib.py:340-343`) and **board server** (`task_server.py:974-977`) hand-roll the same broken colon-`PATH`.
- **Board file-open** (`task_server.py:1715`) has `open`/`xdg-open`/`ghostty` branches but no Windows one, and bypasses `platform_lib` entirely.

The beta user's manual patch fixed only *his* hot path and inlined an `os.name` check — the anti-pattern the seam exists to prevent. The real fix is architectural.

## Principle

`platform_lib.py` is the **single OS seam**. Every fix either *uses* an existing seam function or *adds* one — no inline `os.name`/`sys.platform` checks scattered through callers. The engine shells **Python → Python via `sys.executable`**, never Python → bash. Shell scripts survive as thin human-facing front doors. Aligns with the root `CLAUDE.md` guardrail: *"A script that errors on Windows is a portability bug to fix natively (the OS seam is `scripts/platform_lib.py`), not a reason to install a Unix layer."*

## Scope

**In:** everything a Windows user hits during **normal runtime operation**.
**Out (operator's call):** macOS-only *install* scripts (`qmd-setup.sh`, `run_task_server.sh` homebrew-python, `install_granola_sync.sh` launchd). Windows has its own install path (Task Scheduler / `INSTALL-windows.md`).

**Approach chosen: C** — stop the Python→bash→python hop; keep `.sh` files as thin shims. (Rejected: A = wrap in `bash`, adds a Git Bash dependency to the engine's own dispatch, against the guardrail; B = port all shell to Python, deletes the human CLI doors, most work.)

## Design

### A. Seam additions (`scripts/platform_lib.py`)
1. **`resolve_tool(name)`** — generalize the existing `resolve_claude()` (which becomes `resolve_tool("claude")`). Honors `PATHEXT` via `shutil.which`; returns `None` when a tool is genuinely absent so callers can skip gracefully. Used for `qmd`.
2. **`open_file_cmd(path)`** — OS-correct "open this file for the human" argv: `["open", path]` (darwin), `["cmd","/c","start","",path]` (windows), `["xdg-open", path]` (linux). Replaces the hand-rolled branch in `task_server.py`.
3. **`headless_claude_env()`** stays as-is — already the correct PATH builder (gates POSIX dirs, uses `os.pathsep`). The job is to make the three hand-rolled copies *call it*.

### B. Kill the Python→bash→python hop
- **`task_dispatch.py`** (156, 970): replace `[TASK_SH, …]` with `[sys.executable, TASK_CLI, …]` (`TASK_CLI` → `task_cli.py`). No bash. `task.sh` stays untouched as the CLI door.
- **`transcript_post.py:61`**: extract `task-extract-meetings.sh`'s core into new **`scripts/task_extract_meetings.py`** (processed-file tracking via pathlib + text file; `claude -p` via `resolve_tool("claude")` + `headless_claude_env()`; `--all-unprocessed` via `Path.glob`). `transcript_post` calls it via `sys.executable`. The `.sh` becomes a one-line `exec python3 task_extract_meetings.py "$@"` shim — human CLI + docs keep working, one source of truth, and the brittle `!= /*` Windows-drive bug disappears (pathlib handles drives). The embedded `claude -p` prompt's `./scripts/task.sh` references are **unchanged** — Claude's own Bash tool (Git Bash on Windows) runs those, which is Claude's runtime, not ours.

### C. Consolidate the broken colon-`PATH`
- **`transcript_post.py` `_hook_env()`**, **`cron_lib.py` (340-343)**, **`task_server.py` (974-977)**: all hand-roll `… + ":/opt/homebrew/bin" + ":" + …`, corrupting `PATH` on Windows. Replace all three with `platform_lib.headless_claude_env()`. One correct implementation, three call sites.

### D. Graceful degradation for unavailable tools
- **`qmd`** (`transcript_post.py:69`): resolve via `resolve_tool("qmd")`; if `None`, log `"qmd not found — skipping index update (semantic search optional)"` and continue.
- **`fswatch`** (`doc_sync_watcher.py`), **`pandoc`** (`doc_sync.py`), **`osascript`** (`otter_sync.py`, macOS-only notification): `shutil.which` guard → clean log-and-skip instead of an unhandled `FileNotFoundError`/`WinError`.
- **`python3`** (`task_lib.py:188`): → `sys.executable`.
- **board file-open** (`task_server.py:1715`): route through `platform_lib.open_file_cmd()` — `.docx` and editor-open get a real Windows branch (default-app open) instead of crashing on missing `xdg-open`/`ghostty`.

## Data flow (contract unchanged, mechanism portable)

Granola/Otter sync → `transcript_post.run_downstream()` → `[sys.executable, task_extract_meetings.py, path]` (was: direct `.sh`) → `claude -p` (resolved) → tasks created. Plus optional `qmd` index (skipped if absent). Identical on macOS; now functional on Windows.

## Error handling

Every external-tool call gets the same shape: resolve/guard → if absent, log a one-line human reason and continue. The hooks are already best-effort `try/except` with warnings; we make "missing tool" a *clean* skip, not a stack trace. No behavior change on macOS.

## Testing

Mirrors the existing Windows test pattern — mock `platform_lib.os_kind()` → `"windows"`; `platform_lib` is design-validated, not run-validated (no Windows box on the dev machine).
- Unit tests on **produced argv/env** under mocked Windows: `task_dispatch` builds bash-free `[sys.executable, …]`; `headless_claude_env` injects no POSIX dirs / no `:`-join; `open_file_cmd` returns `cmd /c start`; `resolve_tool` returns `None` → qmd hook skipped.
- Focused test for `task_extract_meetings.py`: path resolution (relative, absolute-POSIX, absolute-Windows-drive) and processed-file idempotency.
- Three green gates (`pytest`, `card_schema.py`, `test_engine_no_jay.py`) before every commit.
- Live e2e on macOS dev board (`:8743`): run a real transcript through `run_downstream`, confirm tasks extracted + board renders — proves no regression.

## Residual risk

True Windows **run-validation** still requires the beta user — the dev machine is macOS-only, so the Windows branches remain design-validated. The build closes the known failure class and unit-proves the produced commands; final confirmation is a Windows beta re-test.

## Invariants honored

- #1/#4 de-personalization: no person/team identity enters any artifact; `test_engine_no_jay.py` stays green.
- #2 green gates before every commit.
- #7 dev board only (`:8743`); prod (`~/pm-os`, `:8742`) untouched.
