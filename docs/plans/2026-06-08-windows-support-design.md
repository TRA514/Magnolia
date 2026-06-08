# Windows support — design

> 2026-06-08. Goal: a Windows teammate can onboard, land on their live board, and use
> the chat panel + agent dispatch. ~half the team is on Windows, so Windows is a
> first-class platform, not a beta accommodation.

## Constraint that shapes everything
There is **no Windows box in the build environment** (the dev machine is a Mac).
`platform_lib`/`persist_lib` already say so. Therefore:
- **Tier 1 (onboarding)** is verifiable on the Mac and is high-confidence.
- **Tier 2 (chat/dispatch)** is **best-effort, unit-tested against a mocked `os_kind()`,
  but NOT run-validated.** The Windows teammate's first run is the live test.

## What is already Windows-safe (verified by reading the code)
- Board launch: `server_lib.default_cmd()` uses `sys.executable`.
- `platform_lib.open_url` / `free_port`: already have Windows branches.
- Feed-guard (onboarding step 2): `launch_agents_dir()` returns `None` on Windows →
  finds no competing feed → no-ops.
- Doctor detect: `shutil.which` + socket probe are portable; winget mapping exists.

## The two kinds of `/opt/homebrew` reference
- **PATH-appends** (`chat_runner`, `task_server`, `cron_lib`, `judge`, `transcript_post`):
  prepend a junk dir but keep the real PATH after it → **degrade, not crash.** Left alone
  except where the Tier-2 helper replaces them.
- **Hardcoded executables** (`parse_task_input.py:344` → brew python; `jira_publish.py` →
  brew claude w/ no PATH fallback): **100% crash on Windows**, but only fire on features
  (NL task-add CLI, Jira publish), never during onboarding or basic board use.

## Tier 1 — Onboarding (high confidence, Mac-verifiable)
1. **`scripts/task.sh`** — resolve `python` from PATH instead of `/opt/homebrew/bin/python3`.
   The lone hard onboarding blocker (every onboarding step shells `task.sh add`). Also fixes
   Linux. Relies on Git Bash being present on Windows — which it always is, because Claude
   Code itself requires Git for Windows to run.
2. **`scripts/doctor.py`** — mark `qmd` `required: false` so its likely-absence on Windows
   reads as "optional, semantic search degrades to keyword," not "broken."
3. **`.claude/skills/meta-onboard/SKILL.md`** — Step 5: one sentence that on Windows,
   auto-restart-on-reboot (Task Scheduler) is a later/optional setup; the board runs now.
   Do **not** auto-run the unverified PowerShell on the user's first session.

## Tier 2 — Chat + dispatch (best-effort, unverified)
Root cause: `chat_runner`, `task_dispatch`, and `judge` each copy-paste the same "launch
`claude` headless" idiom, which fails on Windows three ways: (a) bare `"claude"` argv[0]
doesn't resolve like on Mac, (b) `task_dispatch` wraps it in `script -q` (a Unix-only
command), (c) `chat_runner` uses POSIX-only `start_new_session=True`.

4. **One shared helper** (in `platform_lib`, or a small `claude_launch` seam) that:
   - resolves the `claude` binary cross-platform via `shutil.which` (PATHEXT-aware),
   - builds env/PATH with `os.pathsep` and platform-correct dirs,
   - drops the `script -q` pty-wrapper on Windows (runs the argv directly),
   - uses `creationflags=CREATE_NEW_PROCESS_GROUP` on Windows vs `start_new_session` on POSIX.
   Apply at `chat_runner`, `task_dispatch`, `judge`. Fold in the two cheap hardcoded-exec
   fixes for free: `parse_task_input` → `sys.executable`; `jira_publish` → the helper.

## Explicitly skipped ("fix what breaks")
- Kind-A PATH-append noise (harmless on Windows).
- Verified Task Scheduler reboot-persistence (degrades; documented in Tier 1 #3).
- Anything that needs a real Windows box to validate beyond the mocked tests.

## Verification
- **Mac:** full onboarding dry-run; the three green gates (`pytest`, `card_schema.py`,
  `test_engine_no_jay.py`); `task.sh` smoke run (no regression); new unit tests asserting the
  Tier-2 helper emits correct argv/env/wrapper for mocked `os_kind() == "windows"`.
- **Windows:** the teammate's live run, with a fix-loop on standby.

## Ship
PR off `main` (no direct merge). Jay regression-tests on his Mac from the branch before any
Windows box pulls from origin.
