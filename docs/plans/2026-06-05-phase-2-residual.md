# Magnolia Phase 2 — Residual Triage & Definition of Done

Date: 2026-06-05
Branch: `feat/phase-2-doctor-onboarding`

This document closes out Magnolia Phase 2 (Doctor + Onboarding). It records the
Definition of Done verification and the residual / deferred items surfaced by the
two-stage reviews during implementation.

---

## Definition of Done

Verified on macOS (the dev machine) at Phase 2 close. Each item marked with honest status.

- [x] `python3 -m pytest` passes from a clean checkout (e2e runs on macOS, skips elsewhere).
  - 85 passed (4.13s). `tests/test_e2e_macos.py::test_detect_then_serve` runs on this Mac;
    it is guarded by `pytest.mark.skipif(platform_lib.os_kind() != "darwin")` so it skips on
    Windows/Linux.
- [x] `doctor.py detect` writes a valid `profile/capabilities.json` for the real machine.
  - Verified via temp-root `doctor.detect(root=...)` (to avoid mutating the repo). Output reflected
    THIS machine: `platform: darwin`; local tools (qmd, pandoc, claude_cli, msgraph_cli, python_deps)
    all `ok`; `server` `running` on port 8742; `transcript` `not_expected` (profile.example uses
    provider `none`). `schema_version: 1` present. `check('qmd')` returned exit 0.
- [x] Server port is read from config; `server_lib.start` verifies serving before returning.
  - `server_lib.port()` / `url()` resolve via `profile_lib.server_port()`. `start()` polls
    `is_running()` until the `/api/tasks` endpoint serves 200, raising `TimeoutError` (and killing
    the child) otherwise. Covered by `test_server_lib.py` (start_polls_until_serving,
    start_raises_if_never_serves, start_kills_child_that_ignores_sigterm).
    (config→server-port threading is validated by unit tests — `test_profile_lib.server_port` +
    `test_server_lib.start`; the macOS e2e injects an explicit port+cmd and does not exercise the
    production default-port path end-to-end.)
- [x] `persist_lib` writes a LaunchAgent on macOS with no hardcoded user path.
  - `test_persist_lib.py::test_render_plist_has_no_hardcoded_user_and_uses_repo_path` and
    `test_install_macos_writes_plist` pass. Path is derived from the repo, not a personal home dir.
- [x] Windows persistence + package install are rendered and unit-tested but explicitly marked
      design-validated, not run-validated.
  - `platform_lib.py` module docstring states macOS is run-validated and Windows branches are
    DESIGN-VALIDATED, NOT RUN-VALIDATED (no Windows box). Covered by
    `test_persist_lib.py::test_install_windows_returns_command` and
    `test_platform_lib.py::test_package_install_cmd_per_os`. See the Windows residual section below
    for the specific gaps that need a Windows box to run-validate.
- [x] No `/Users/jayjenkins/pm-os` path remains in `session-start.sh`, `hooks.json`, `qmd-*.sh`,
      `run_task_server.sh`, or the ported Otter files.
  - `grep -rn "/Users/jayjenkins/pm-os"` over those files returns no matches. Enforced going
    forward by `test_script_paths.py`, `test_hook_paths.py`, and `test_otter_port.py`.
    (`.claude/mcp.json` was also de-personalized post-merge-of-tasks — see the resolved item below.)
- [x] `meta-onboard` + `workflow-doctor` skills present with valid frontmatter.
  - Both `SKILL.md` files have `name`, `description`, and `allowed-tools`. Covered by
    `test_skill_frontmatter.py` (workflow_doctor_frontmatter, meta_onboard_frontmatter_and_persona).
- [x] Monday-9am Doctor cron seeds idempotently.
  - Covered by `test_seed_default_crons.py` (seeds_doctor_cron_once, doctor_cron_is_monday_9am,
    seed_cold_against_real_cron_lib). The live seed run against the real `datasets/cron` was
    intentionally NOT executed (it would seed a real job); the cold integration test validates it.

---

## ✅ Found-but-unplanned bug — RESOLVED

- **`.claude/mcp.json` hardcoded `"cwd": "/Users/jayjenkins/pm-os"`** for the qmd MCP server (same
  production-pointer class Task 18 fixed for the hooks; no Phase-2 task had covered it; Phase 1's
  triage wrongly believed it was handled in Tasks 9-10).
  - **Fixed:** verified against the Claude Code docs that `cwd` is NOT a supported `.mcp.json` field
    (Claude Code passes the project root to the server via `CLAUDE_PROJECT_DIR` and defaults the
    working dir to the launch dir), and that qmd resolves its config/collections from the global
    `~/.config/qmd/index.yml` with absolute collection paths — so qmd never needed a `cwd`. Removed
    the `cwd` field entirely. Also changed `command` from `/opt/homebrew/bin/qmd` to PATH-resolved
    `qmd` (consistent with how the Doctor probes it via `shutil.which("qmd")`; portable across
    Intel/Apple-Silicon/non-Homebrew). Regression-guarded by `tests/test_mcp_config.py`.
  - `.claude/` now contains zero `/Users/jayjenkins/pm-os` references.

---

## Windows — design-validated, NOT run-validated (no Windows box)

- **persist_lib Windows Scheduled-Task** uses bare `-AtLogOn` (no `-Principal`/`-User`) — fires at
  ANY user's logon. Should pin the trigger/principal to the installing user for true per-user behavior.
- **Missing `-ExecutionTimeLimit 0`** on the scheduled task — without it, the long-running server is
  killed after the default 3-day cap.
- **`-RestartCount 3` is not equivalent to macOS `KeepAlive`'s indefinite restart** (behavior
  asymmetry to document/reconcile).
- **PowerShell string-escaping deferred** — when run-validating, use single-quoted PS literals with
  `''` doubling. Inputs containing `"`, `$`, or backtick break the current f-string interpolation.
- **`persist_lib.remove()` has NO Windows branch** — a Windows-installed task can't be torn down via
  the API. Should return a symmetric `Unregister-ScheduledTask` command.
- **`persist_lib.is_installed()` always returns False on Windows** — latent idempotency gap;
  onboarding would re-issue install every run.
- **`platform_lib.package_install_cmd` winget IDs** for `qmd` (placeholder) and `fswatch`
  (no equivalent → returns None) need real Windows verification.

---

## Granola (Phase 3)

- Onboarding offers Granola, but only Otter is wired. `transcript_sync` returns `unsupported` for
  granola. Phase-3: drop-in adapter behind the same entrypoint.

---

## Integration facts deferred to Phase 3

- **Pendo** (subId / app IDs) and **Databricks** (`is_prod` catalog + table refs) integration facts
  across skills/workers remain to be profile-ized (carried over from Phase 1 residual triage).
- **`msgraph_cli` (`mgc`) exact macOS install route** is a placeholder remedy
  ("see claude.ai/code install") — confirm the real `mgc` install method during live Doctor use.

---

## Smaller hardening notes (non-blocking, surfaced in review)

### doctor.py
- `detect()` + CLI double-write capabilities.json (pure `detect` writes; the CLI re-writes with
  `generated_at`). Decide if `generated_at` should be intrinsic to every persisted doc.
- `main()` lacks a final `else` (unreachable now; add a guard if more subcommands are added).
- `report_text` uses a magic `{name:14}` width.
- `_remote_seeds` could collide if two integration categories ever resolve to the same provider name
  (add a defensive merge/comment).
- `server` capability omits the `persistent` field the design shows (consumers must `.get()`).

### profile_lib.py
- `write_capabilities` falls back to `profile.example/` if `profile/` is absent. Onboarding step 0
  (`cp -R profile.example profile`) runs before detect so it's safe in practice; consider guarding
  the write path to refuse `profile.example`.

### server_lib.py
- `url()` uses `localhost` while `is_running()` probes `127.0.0.1` (potential IPv6 `::1` mismatch).
- Full port/cmd consistency (threading the resolved port into `task_server.py` via argv/env) is
  deferred — documented; onboarding persists the chosen port to config before `start()`.

### otter_sync.py
- Module-level `mkdir` side effects at import (partly inherited).
- `transcript_sync` dict-shape consistency + `__main__` exit code.
- Deeper per-call `root` threading into the Otter runner if multi-root is ever needed.

### session-start.sh
- `BASH_SOURCE` not canonicalized → a symlinked invocation would silently drop the skills payload
  (non-issue for the real `$CLAUDE_PROJECT_DIR` path).
- Line-12 comment ("robust relative path") is stale.

### run_task_server.sh
- Line 10 comment references the stale `com.jayjenkins.task-server` plist label
  (persist_lib uses `com.pm-os.task-server`).
- **Known issue:** Line 28 hardcodes `/opt/homebrew/bin/python3` and line 18 hardcodes the
  Homebrew PATH. This is the macOS manual-fallback LaunchAgent entrypoint (the cross-platform
  path is `persist_lib`), but it silently fails on Intel Macs (`/usr/local`) or a non-Homebrew
  Python. Fix: resolve python via `command -v python3` / PATH. Low priority (fallback only).

### probe_transcript (doctor.py)
- Does an existence-only check on `session.json`, not true freshness. If a stale-but-present session
  should flip to `needs_reauth`, that's a follow-up; reconcile the design-doc "freshness" wording.
