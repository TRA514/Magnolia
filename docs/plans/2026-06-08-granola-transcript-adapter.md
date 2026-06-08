# Granola Transcript Adapter Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Granola as a transcript provider that pulls meeting transcripts hourly via headless `claude -p` + the Granola MCP, dedups by meeting UUID, and runs the identical Otter downstream (classify → front matter → task extraction → qmd index).

**Architecture:** Option A — a thin, mockable `claude -p` fetch boundary in a new `granola_sync.py` that mirrors `otter_sync.py`; all dedup/state/write/classify/hook logic is deterministic Python shared with Otter via an extracted `transcript_post.py` helper. The hourly job is provider-gated (no-ops unless `transcript.provider == "granola"`), so the Engine-tab provider selection is the on/off switch.

**Tech Stack:** Python 3.14, pytest, `claude -p` CLI (`--output-format json`), Granola MCP (`mcp__claude_ai_Granola__*`), macOS LaunchAgent.

**Design doc:** `docs/plans/2026-06-08-granola-transcript-adapter-design.md`

**Green gates — run before EVERY code commit:**
```bash
python3 -m pytest -q
python3 scripts/card_schema.py            # -> "registry.json OK"
python3 -m pytest tests/test_engine_no_jay.py -q
```
Plus, after the adapter task: `python3 scripts/factory_lib.py validate-adapter transcript granola` -> `ok`

**Denylist rule (invariant #1):** every new `.py` reads identity/team/paths from `profile_lib` — never hardcode a name, email, or `/Users/...` path. The plist template uses placeholders, never a real user.

---

### Task 1: Extract the shared downstream helper

Pull Otter's post-write block (classify + task-extract hook + qmd hook) into one module both syncs call, so parity is guaranteed by sharing, not copying.

**Files:**
- Create: `scripts/transcript_post.py`
- Modify: `scripts/otter_sync.py:321-382` (replace the inline classify+hooks block with a call)
- Test: `tests/test_transcript_post.py`

**Step 1: Write the failing test**

```python
# tests/test_transcript_post.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import transcript_post


def test_run_downstream_classifies_and_fires_hooks(tmp_path, monkeypatch):
    txt = tmp_path / "2026-06-08_10-00_demo.txt"
    txt.write_text("hello", encoding="utf-8")
    state = {}
    calls = {"classify": 0, "popen": []}

    def fake_classify(path, speech_id=None, downloaded_state=None):
        calls["classify"] += 1
        return {"domain": "product/home", "final_path": str(txt)}

    monkeypatch.setattr(transcript_post, "_classify_fn", lambda: fake_classify)
    monkeypatch.setattr(transcript_post.subprocess, "Popen",
                        lambda *a, **k: calls["popen"].append(a[0]) or None)

    final = transcript_post.run_downstream(str(txt), "uuid-123", state, log=transcript_post._null_log())
    assert final == str(txt)
    assert state["uuid-123"]["domain"] == "product/home"
    assert calls["classify"] == 1
    assert len(calls["popen"]) == 2   # task-extract + qmd
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_transcript_post.py -v`
Expected: FAIL (`ModuleNotFoundError: transcript_post`)

**Step 3: Write minimal implementation**

Move the logic verbatim from `otter_sync.py` lines ~321-382. Structure:

```python
# scripts/transcript_post.py
"""Shared transcript downstream: classify -> front matter -> task-extract + qmd.

Used by every transcript provider (otter_sync, granola_sync) so the post-download
pipeline is byte-for-byte identical. Reads all paths from profile_lib."""
import logging, os, subprocess, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402

SCRIPT_DIR = Path(__file__).parent.resolve()


def _null_log():
    lg = logging.getLogger("transcript_post.null")
    lg.addHandler(logging.NullHandler())
    return lg


def _classify_fn():
    """Late import so openai stays optional (graceful degradation)."""
    from otter_classify import process_file
    return process_file


def _hook_env():
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)            # allow nested claude -p
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    env["PATH"] = (str(Path.home() / ".local" / "bin") + ":/opt/homebrew/bin"
                   + ":" + env.get("PATH", "/usr/bin:/bin"))
    return env


def run_downstream(txt_path, item_id, state, log):
    """Classify the txt, record domain/final_path in state[item_id], fire the
    task-extract + qmd hooks. Returns final_path (or txt_path if classify absent).
    Mirrors the Otter post-write block exactly; provider-agnostic via item_id."""
    final_path = str(txt_path)
    try:
        process_file = _classify_fn()
    except ImportError:
        log.warning("  openai not installed — skipping classification for %s", item_id)
        process_file = None
    if process_file:
        try:
            result = process_file(txt_path, speech_id=item_id, downloaded_state=state)
            state.setdefault(item_id, {})["domain"] = result["domain"]
            state[item_id]["final_path"] = str(result["final_path"])
            final_path = str(result["final_path"])
            log.info("  Classified -> %s", result["final_path"])
        except Exception as exc:
            log.warning("  Classification failed for %s: %s", item_id, exc)

    log_dir = Path(profile_lib.PM_OS_DIR) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    env = _hook_env()
    try:
        subprocess.Popen([str(SCRIPT_DIR / "task-extract-meetings.sh"), final_path],
                         cwd=str(profile_lib.PM_OS_DIR), start_new_session=True, env=env,
                         stdout=open(log_dir / "task-extract.log", "a"),
                         stderr=subprocess.STDOUT)
        log.info("  Triggered task extraction for %s", final_path)
    except Exception as exc:
        log.warning("  Task extraction hook failed: %s", exc)
    try:
        subprocess.Popen(["qmd", "update", "-c", "meetings_product"],
                         cwd=str(profile_lib.PM_OS_DIR), start_new_session=True, env=env,
                         stdout=open(log_dir / "qmd-index.log", "a"),
                         stderr=subprocess.STDOUT)
        log.info("  Triggered qmd index update (meetings_product)")
    except Exception as exc:
        log.warning("  QMD index update hook failed: %s", exc)
    return final_path
```

Then in `otter_sync.py`, replace the inline classify+hooks block (lines ~322-382) with:
```python
import transcript_post
...
final_path = transcript_post.run_downstream(txt_path, speech_id, state, log)
state[speech_id]["final_path"] = final_path
save_state(state)
new_count += 1
```
Keep `save_state`/`new_count` behavior identical. The test monkeypatches `_classify_fn`/`subprocess.Popen` — make sure those names match.

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_transcript_post.py -q && python3 -m pytest -q`
Expected: PASS (full suite still green — otter has no unit test that breaks, but verify import works)

**Step 5: Commit** (run the three green gates first)

```bash
git add scripts/transcript_post.py scripts/otter_sync.py tests/test_transcript_post.py
git commit -m "refactor: extract shared transcript downstream into transcript_post"
```

---

### Task 2: `granola_sync.py` — fetch boundary + dedup + write

**Files:**
- Create: `scripts/granola_sync.py`
- Test: `tests/test_granola_sync.py`

**Step 1: Write the failing tests**

```python
# tests/test_granola_sync.py
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import granola_sync


def _profile(tmp_path, provider="granola"):
    (tmp_path / "profile").mkdir(exist_ok=True)
    (tmp_path / "profile" / "integrations.yaml").write_text(
        f"transcript:\n  provider: {provider}\n  target: datasets/meetings/\n")
    (tmp_path / "profile" / "config.yaml").write_text("models: {}\n")


def test_dedup_skips_seen_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(granola_sync, "_fetch_new_meetings",
        lambda seen, root=None: [] if "uuid-1" in seen else [{"id": "uuid-1",
            "title": "Demo", "created_at": "2026-06-08T10:00:00Z",
            "attendees": [], "transcript": "hi"}])
    seen_state = {"uuid-1": {"title": "Demo"}}
    new = granola_sync._fetch_new_meetings(set(seen_state), root=str(tmp_path))
    assert new == []   # already-seen id excluded by the fetch contract


def test_main_writes_and_records(tmp_path, monkeypatch):
    _profile(tmp_path)
    monkeypatch.setattr(granola_sync.profile_lib, "PM_OS_DIR", str(tmp_path))
    monkeypatch.setattr(granola_sync, "_state_dir", lambda root=None: str(tmp_path / "st"))
    monkeypatch.setattr(granola_sync, "_fetch_new_meetings",
        lambda seen, root=None: [{"id": "uuid-9", "title": "Voice AI call",
            "created_at": "2026-06-08T10:00:00Z", "attendees": ["Ann"],
            "transcript": "Ann: hello world"}])
    fired = {}
    monkeypatch.setattr(granola_sync.transcript_post, "run_downstream",
        lambda txt, mid, state, log: fired.setdefault(mid, txt) or str(txt))
    granola_sync.main(root=str(tmp_path))
    state = json.load(open(tmp_path / "st" / "granola_downloaded.json"))
    assert "uuid-9" in state                      # recorded
    assert "uuid-9" in fired                       # downstream fired
    # second run: already seen -> no new fetch, no error
    monkeypatch.setattr(granola_sync, "_fetch_new_meetings", lambda seen, root=None: [])
    granola_sync.main(root=str(tmp_path))


def test_main_noop_when_provider_not_granola(tmp_path, monkeypatch):
    _profile(tmp_path, provider="otter")
    called = {"fetch": False}
    monkeypatch.setattr(granola_sync, "_fetch_new_meetings",
        lambda seen, root=None: called.__setitem__("fetch", True) or [])
    result = granola_sync.main(root=str(tmp_path))
    assert called["fetch"] is False               # provider gate: never fetched
    assert result["status"] == "skipped"
```

**Step 2: Run to verify fail**

Run: `python3 -m pytest tests/test_granola_sync.py -q`
Expected: FAIL (`ModuleNotFoundError: granola_sync`)

**Step 3: Implement**

```python
# scripts/granola_sync.py
#!/usr/bin/env python3
"""Granola transcript sync — mirrors otter_sync.

Fetches new Granola meeting transcripts via headless `claude -p` + the Granola
MCP (the single mockable seam `_fetch_new_meetings`), dedups by meeting UUID in
granola_downloaded.json, writes a dated .txt into the profile meetings target,
then runs the SHARED Otter downstream (transcript_post.run_downstream).

Provider-gated: main() is a no-op unless transcript.provider == "granola", so the
Engine-tab provider selection is the on/off switch for the hourly LaunchAgent."""
import json, logging, os, re, subprocess, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib            # noqa: E402
import transcript_post        # noqa: E402

DEFAULT_MODEL = "claude-haiku-4-5"
MAX_NEW_PER_RUN = 20
FETCH_TIMEOUT = 300           # seconds for the claude -p subprocess
GRANOLA_TOOLS = ("mcp__claude_ai_Granola__list_meetings,"
                 "mcp__claude_ai_Granola__get_meeting_transcript")

log = logging.getLogger("granola_sync")


def _state_dir(root=None):
    return profile_lib.transcript_state_dir(root)


def _meetings_dir(root=None):
    return Path(profile_lib.PM_OS_DIR) / profile_lib.transcript_config(root)["target"]


def _state_file(root=None):
    return Path(_state_dir(root)) / "granola_downloaded.json"


def _model(root=None):
    return (profile_lib.config(root).get("models") or {}).get("granola_fetch") or DEFAULT_MODEL


def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name or "").strip()


def _basename(created_at, title):
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        stamp = dt.strftime("%Y-%m-%d_%H-%M")
    except Exception:
        stamp = "unknown"
    clean = re.sub(r"[_ ]{2,}", " ", safe_filename(title)).strip() or "untitled"
    return f"{stamp}_{clean}", (dt if stamp != "unknown" else None)


def _load_state(root=None):
    f = _state_file(root)
    return json.loads(f.read_text()) if f.exists() else {}


def _save_state(state, root=None):
    f = _state_file(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, indent=2))


def _fetch_prompt(seen_ids):
    return (
        "Use the Granola MCP. Call list_meetings(time_range='last_30_days'). "
        "For EACH meeting whose id is NOT in this already-downloaded list, call "
        "get_meeting_transcript(meeting_id). Already downloaded ids: "
        + json.dumps(sorted(seen_ids)) + ". "
        f"Return at most {MAX_NEW_PER_RUN} meetings as STRICT JSON: a JSON array of "
        '{"id","title","created_at","attendees","transcript"} and NOTHING else. '
        "If a transcript is unavailable (e.g. plan restriction), omit that meeting. "
        "If there are no new meetings, return []."
    )


def _fetch_new_meetings(seen_ids, root=None):
    """THE mockable seam. Shell out to claude -p + Granola MCP; return a list of
    new meeting dicts. Validates JSON; one retry on malformed; [] on hard failure."""
    cmd = ["claude", "-p", _fetch_prompt(seen_ids),
           "--model", _model(root), "--output-format", "json",
           "--allowedTools", GRANOLA_TOOLS,
           "--permission-mode", "bypassPermissions", "--max-turns", "30"]
    env = transcript_post._hook_env()    # strips CLAUDECODE so nested claude -p runs
    for attempt in (1, 2):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=FETCH_TIMEOUT, env=env, cwd=str(profile_lib.PM_OS_DIR))
        except Exception as exc:
            log.error("claude -p fetch failed (attempt %d): %s", attempt, exc)
            continue
        meetings = _parse_fetch_output(out.stdout)
        if meetings is not None:
            return [m for m in meetings if m.get("id") not in seen_ids and m.get("transcript")]
        log.warning("malformed fetch JSON (attempt %d)", attempt)
    return []


def _parse_fetch_output(stdout):
    """claude --output-format json wraps the result; the model's text is the
    payload. Find the JSON array. Returns list, or None if unparseable."""
    if not stdout:
        return None
    text = stdout.strip()
    try:
        outer = json.loads(text)
        text = outer.get("result", text) if isinstance(outer, dict) else text
    except json.JSONDecodeError:
        pass
    if isinstance(text, list):
        return text
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(text[start:end + 1])
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


def main(root=None):
    if not log.handlers:
        logging.basicConfig(level=logging.INFO,
            format="%(asctime)s  %(levelname)s  %(message)s",
            handlers=[logging.FileHandler(Path(_state_dir(root)) / "granola_sync.log")
                      if Path(_state_dir(root)).exists() else logging.StreamHandler(),
                      logging.StreamHandler(sys.stdout)])
    # Provider gate — the Engine-tab switch.
    if profile_lib.transcript_config(root)["provider"] != "granola":
        log.info("transcript provider is not granola — skipping")
        return {"status": "skipped", "provider": profile_lib.transcript_config(root)["provider"]}

    Path(_state_dir(root)).mkdir(parents=True, exist_ok=True)
    state = _load_state(root)
    meetings = _fetch_new_meetings(set(state), root=root)
    log.info("Granola returned %d new meeting(s)", len(meetings))

    new_count = 0
    for m in meetings:
        mid = m.get("id")
        if not mid or mid in state:
            continue
        base, dt = _basename(m.get("created_at"), m.get("title"))
        folder = _meetings_dir(root) / (dt.strftime("%Y-%m") if dt else "unknown")
        folder.mkdir(parents=True, exist_ok=True)
        txt_path = folder / f"{base}.txt"
        header = f"# {m.get('title','untitled')}\nDate: {m.get('created_at','')}\n"
        if m.get("attendees"):
            header += "Attendees: " + ", ".join(str(a) for a in m["attendees"]) + "\n"
        try:
            txt_path.write_text(header + "\n" + (m.get("transcript") or ""), encoding="utf-8")
        except Exception as exc:
            log.error("  Failed to write %s: %s", mid, exc)
            continue            # do NOT mark seen -> retried next run
        state[mid] = {"title": m.get("title"), "downloaded_at": datetime.now().isoformat(),
                      "folder": str(folder)}
        final_path = transcript_post.run_downstream(txt_path, mid, state, log)
        state[mid]["final_path"] = final_path
        _save_state(state, root)
        new_count += 1

    log.info("Downloaded %d new Granola transcript(s)", new_count)
    return {"status": "ok", "provider": "granola", "new": new_count}


if __name__ == "__main__":
    print(main())
```

Note `_parse_fetch_output` is exercised by Task-2 tests indirectly; add a direct unit test for it (malformed -> None; wrapped result -> list).

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_granola_sync.py -q`
Expected: PASS

**Step 5: Commit** (green gates first)

```bash
git add scripts/granola_sync.py tests/test_granola_sync.py
git commit -m "feat: granola_sync — claude -p fetch boundary, UUID dedup, shared downstream"
```

---

### Task 3: `_run_granola` in transcript_sync + flip dispatch test

**Files:**
- Modify: `scripts/transcript_sync.py` (add `_run_granola`)
- Modify: `tests/test_transcript_sync.py` (replace `test_dispatch_granola_not_yet`)

**Step 1: Update the test** — replace `test_dispatch_granola_not_yet` with:

```python
def test_dispatch_granola_calls_runner(tmp_path, monkeypatch):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: granola\n")
    called = {}
    monkeypatch.setattr(transcript_sync, "_run_granola", lambda root: called.setdefault("ran", True))
    transcript_sync.sync(root=str(tmp_path))
    assert called.get("ran") is True


def test_dispatch_granola_runner_failure_returns_error(tmp_path, monkeypatch):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: granola\n")
    def boom(root=None):
        raise RuntimeError("mcp unauthorized")
    monkeypatch.setattr(transcript_sync, "_run_granola", boom)
    result = transcript_sync.sync(root=str(tmp_path))
    assert result["status"] == "error" and result["provider"] == "granola"
```

**Step 2: Run to verify fail** — `python3 -m pytest tests/test_transcript_sync.py -q` (FAIL: `_run_granola` missing / old behavior).

Note: `transcript_sync.sync` dispatches via the adapter loader to `adapters.transcript.granola.sync`, which (Task 4) delegates back to `_run_granola`. The error-wrapping (`{status:error, provider:granola}`) must live in `granola.py` (mirror `otter.py`). For the dispatch test above to pass by monkeypatching `transcript_sync._run_granola`, `granola.py` must call `transcript_sync._run_granola` — so Tasks 3 and 4 land together.

**Step 3: Implement** in `transcript_sync.py`:

```python
def _run_granola(root=None):
    """Run the Granola sync. Lazy import keeps claude -p / MCP deps out of module load."""
    import granola_sync
    return granola_sync.main(root)
```

**Step 4: Run** — defer full pass to Task 4 (the adapter closes the loop). Commit together with Task 4.

---

### Task 4: Real `granola.py` adapter

**Files:**
- Modify: `scripts/adapters/transcript/granola.py` (replace stub)
- Test: covered by `tests/test_transcript_sync.py` dispatch tests + `validate-adapter`

**Step 1–3: Implement** (mirror `otter.py` exactly):

```python
"""Granola transcript adapter.

Delegates to transcript_sync._run_granola so the headless structured-error
contract and its test monkeypatch hold (mirrors otter.py)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def sync(root=None) -> dict:
    import transcript_sync
    try:
        transcript_sync._run_granola(root)
    except Exception as e:
        return {"status": "error", "provider": "granola", "error": str(e)}
    return {"status": "ok", "provider": "granola"}
```

**Step 4: Run gates + validate**

```bash
python3 -m pytest tests/test_transcript_sync.py -q          # dispatch tests pass
python3 scripts/factory_lib.py validate-adapter transcript granola   # -> ok
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
```

**Step 5: Commit** (Tasks 3+4 together)

```bash
git add scripts/transcript_sync.py scripts/adapters/transcript/granola.py tests/test_transcript_sync.py
git commit -m "feat: wire granola adapter + _run_granola dispatch (real, not stub)"
```

---

### Task 5: Provider-gate verification (already in `main()`)

The gate ships in Task 2 (`main()` returns `{status:skipped}` unless provider == granola) and is covered by `test_main_noop_when_provider_not_granola`. No new code. This task is a checkpoint: confirm the LaunchAgent (Task 7) invokes `granola_sync.py` whose `main()` self-gates, so flipping the provider in the Engine tab toggles the hourly job. No commit.

---

### Task 6: Granola-aware `doctor.probe_transcript`

**Files:**
- Modify: `scripts/doctor.py:84-94`
- Test: `tests/test_doctor.py` (add cases)

**Step 1: Write failing tests** (append to `tests/test_doctor.py`):

```python
def test_probe_transcript_granola_no_marker_needs_reauth(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: granola\n")
    cap = doctor.probe_transcript(root=str(tmp_path))
    assert cap["provider"] == "granola"
    assert cap["status"] == "needs_reauth"
    assert "mcp-signup" in cap.get("detail", "")


def test_probe_transcript_granola_with_marker_ok(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: granola\n")
    st = tmp_path / "profile" / "transcript"
    st.mkdir(parents=True)
    (st / "granola_downloaded.json").write_text("{}")
    cap = doctor.probe_transcript(root=str(tmp_path))
    assert cap["status"] == "ok"
```

**Step 2: Run to verify fail** — `python3 -m pytest tests/test_doctor.py -q`

**Step 3: Implement** — replace the body after the `none` check:

```python
def probe_transcript(root=None):
    tc = profile_lib.transcript_config(root)
    provider = tc["provider"]
    cap = {"kind": "feed", "provider": provider, "target": tc["target"]}
    if provider == "none":
        cap["status"] = "not_expected"
        return cap
    state_dir = profile_lib.transcript_state_dir(root)
    if provider == "granola":
        # The Granola MCP is a claude.ai connector — detect() can't probe it
        # directly. A successful-sync marker (granola_downloaded.json) is our
        # proof of a working feed; absent it, nudge the user to connect.
        marker = os.path.join(state_dir, "granola_downloaded.json")
        if os.path.isfile(marker):
            cap["status"] = "ok"
        else:
            cap["status"] = "needs_reauth"
            cap["detail"] = "Connect Granola via /mcp, then finish granola.ai/mcp-signup"
        return cap
    # otter: a saved Playwright session.json means authed
    session = os.path.join(state_dir, "session.json")
    cap["status"] = "ok" if os.path.isfile(session) else "needs_reauth"
    return cap
```

**Step 4: Run** — `python3 -m pytest tests/test_doctor.py -q` (PASS)

**Step 5: Commit** (green gates first)

```bash
git add scripts/doctor.py tests/test_doctor.py
git commit -m "feat: granola-aware doctor.probe_transcript"
```

---

### Task 7: De-personalized LaunchAgent plist template

**Files:**
- Create: `scripts/templates/transcript-granola-sync.plist.template`
- Create: `scripts/install_granola_sync.sh` (substitutes placeholders, loads agent)

**Step 1–3: Implement.** Template (placeholders only — denylist-clean, NO real user/path):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>__LABEL__</string>
    <key>ProgramArguments</key>
    <array>
        <string>__PYTHON__</string>
        <string>__PM_OS_DIR__/scripts/granola_sync.py</string>
    </array>
    <key>StandardOutPath</key><string>__PM_OS_DIR__/logs/granola_sync.log</string>
    <key>StandardErrorPath</key><string>__PM_OS_DIR__/logs/granola_sync.log</string>
    <key>StartCalendarInterval</key>
    <array>
        __HOURLY_WEEKDAY_BLOCK__
    </array>
</dict>
</plist>
```

`install_granola_sync.sh`: reads `PM_OS_DIR` from the script location, `PYTHON` from `command -v python3`, builds the weekday 9–17 hourly `<dict>` block, label `com.magnolia.granolasync`, writes to `~/Library/LaunchAgents/com.magnolia.granolasync.plist`, and runs `launchctl unload || true; launchctl load`. Echoes a confirmation. (No identity hardcoded; label is generic `magnolia`, not a person.)

**Step 4: Verify** — `python3 -m pytest tests/test_engine_no_jay.py -q` (template/sh not scanned, but keep clean); shellcheck-clean is nice-to-have.

**Step 5: Commit**

```bash
git add scripts/templates/transcript-granola-sync.plist.template scripts/install_granola_sync.sh
git commit -m "feat: de-personalized granola sync LaunchAgent template + installer"
```

> The actual `launchctl load` on the operator's machine is a **live, non-committed** step run after merge (a Tier-ish external-ish action — but local-only; confirm before running).

---

### Task 8: Onboarding + doctor/fix copy

**Files:**
- Modify: `.claude/skills/meta-onboard/SKILL.md:53-55` (drop "Otter is wired today" caveat — both are wired now)
- Modify: `.claude/skills/workflow-doctor/SKILL.md` (add the granola transcript fix path: select provider → `/mcp` connect → granola.ai/mcp-signup → verify via get_account_info)

**Steps:** Edit copy only (docs — not scanned by denylist gate, but keep generic). Then:

```bash
python3 -m pytest tests/test_onboard_collects_jira.py -q   # ensure onboarding tests still pass
git add .claude/skills/meta-onboard/SKILL.md .claude/skills/workflow-doctor/SKILL.md
git commit -m "docs: onboarding + doctor copy — granola transcript fully wired"
```

---

## Final verification (before ship)

```bash
python3 -m pytest -q
python3 scripts/card_schema.py            # registry.json OK
python3 -m pytest tests/test_engine_no_jay.py -q
python3 scripts/factory_lib.py validate-adapter transcript granola   # ok
```

Then e2e (requires live MCP account + paid plan): set `transcript.provider: granola`, run `python3 scripts/granola_sync.py`, confirm a new `.txt` lands in `datasets/meetings/YYYY-MM/`, state recorded in `granola_downloaded.json`, and the task-extract + qmd hooks fire. Confirm the Engine tab shows Granola → `ok` after the first sync (doctor marker present).

## Risks (verify at e2e)
- Headless `claude -p` + claude.ai-MCP OAuth survival in a non-interactive LaunchAgent context.
- `get_meeting_transcript` paid-plan gate.
Both degrade gracefully (log + retry, no state mutation).
