# Granola Fetch Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make `granola_sync` fetch real verbatim transcripts by fetching one transcript per `claude -p` call instead of batching many into one summarizing response.

**Architecture:** Split the single fat fetch into a metadata list call + a per-meeting transcript call, with a placeholder guard that skips (and re-tries) any transcript that comes back empty/summarized. Downstream is untouched. Spec: `docs/plans/2026-06-22-granola-fetch-redesign-design.md`.

## Global Constraints

- Four gates before the code commit: `python3 -m pytest` · `python3 scripts/card_schema.py` (-> `registry.json OK`) · `python3 -m pytest tests/test_engine_no_jay.py` · `python3 scripts/portability_gate.py` (-> `portability OK`).
- Branch `fix/granola-sync-ledger`; never commit to `main`.
- ASCII-safe strings/prompts (hyphen not em-dash, ASCII quotes).
- Commit trailer (verbatim last line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Keep the existing `subprocess` + `transcript_post._hook_env()` + `profile_lib.PM_OS_DIR` cwd pattern (portability seam). `_model`, `_prompt_ids`, `_parse_fetch_output`, `FETCH_TIMEOUT`, `MAX_NEW_PER_RUN` already exist - reuse them.

---

## Task 1: Per-meeting fetch redesign (granola_sync.py + tests)

**Files:**
- Modify: `scripts/granola_sync.py`
- Test: `tests/test_granola_sync.py`

**Interfaces produced (later steps + main() depend on these):**
- `_fetch_new_meetings(state_or_ids, root=None) -> list[dict]` keeps its signature and return shape (`{id,title,created_at,attendees,transcript}` dicts) — main() is unchanged.
- New helpers: `_run_claude(prompt, tools, root=None) -> str|None`, `_list_prompt(seen_ids) -> str`, `_transcript_prompt(meeting_id) -> str`, `_parse_transcript_output(stdout) -> str|None`, `_list_new_meetings(state_or_ids, root=None) -> list[dict]`, `_fetch_one_transcript(meeting_id, root=None) -> str|None`, `_looks_like_placeholder(text) -> bool`.

- [ ] **Step 1: Write failing tests** (add to `tests/test_granola_sync.py`)

```python
def test_looks_like_placeholder():
    assert granola_sync._looks_like_placeholder("") is True
    assert granola_sync._looks_like_placeholder(None) is True
    assert granola_sync._looks_like_placeholder(
        "[Full transcript available - engineering capacity, Atlas blockers]") is True
    assert granola_sync._looks_like_placeholder("too short") is True
    real = "Me: Morning. Them: Morning, how are you? " * 20  # > 200 chars of dialogue
    assert granola_sync._looks_like_placeholder(real) is False


def test_parse_transcript_output_envelope_and_bare():
    # claude -p --output-format json envelope wrapping the model's JSON
    wrapped = '{"result": "{\\"transcript\\": \\"Me: hi. Them: hello.\\"}"}'
    assert granola_sync._parse_transcript_output(wrapped) == "Me: hi. Them: hello."
    # bare object
    assert granola_sync._parse_transcript_output('{"transcript": "abc"}') == "abc"
    # embedded in prose
    assert granola_sync._parse_transcript_output('sure: {"transcript": "xy"} done') == "xy"
    # null / missing / malformed -> None
    assert granola_sync._parse_transcript_output('{"transcript": null}') is None
    assert granola_sync._parse_transcript_output('{"other": 1}') is None
    assert granola_sync._parse_transcript_output("not json") is None
    assert granola_sync._parse_transcript_output(None) is None


def test_list_new_meetings_filters_seen(monkeypatch):
    monkeypatch.setattr(granola_sync, "_run_claude",
        lambda prompt, tools, root=None: '[{"id":"a","title":"A","created_at":"2026-06-08T10:00:00Z","attendees":[]},'
                                         '{"id":"b","title":"B","created_at":"2026-06-09T10:00:00Z","attendees":[]}]')
    out = granola_sync._list_new_meetings({"a": "old.md"})  # 'a' already seen
    assert [m["id"] for m in out] == ["b"]


def test_fetch_one_transcript_good_and_bad(monkeypatch):
    monkeypatch.setattr(granola_sync, "_run_claude",
        lambda prompt, tools, root=None: '{"transcript": "Me: hi. Them: hello."}')
    assert granola_sync._fetch_one_transcript("id-1") == "Me: hi. Them: hello."
    monkeypatch.setattr(granola_sync, "_run_claude", lambda prompt, tools, root=None: None)
    assert granola_sync._fetch_one_transcript("id-1") is None


def test_fetch_new_meetings_skips_placeholder(monkeypatch):
    monkeypatch.setattr(granola_sync, "_list_new_meetings",
        lambda s, root=None: [
            {"id": "good", "title": "G", "created_at": "2026-06-08T10:00:00Z", "attendees": ["Ann"]},
            {"id": "stub", "title": "S", "created_at": "2026-06-09T10:00:00Z", "attendees": []},
        ])
    real = "Me: real discussion about the roadmap and next steps. " * 10
    def _one(mid, root=None):
        return real if mid == "good" else "[Full transcript available - topic keywords]"
    monkeypatch.setattr(granola_sync, "_fetch_one_transcript", _one)
    out = granola_sync._fetch_new_meetings(set())
    assert [m["id"] for m in out] == ["good"]            # placeholder meeting skipped
    assert out[0]["transcript"] == real
    assert out[0]["title"] == "G" and out[0]["attendees"] == ["Ann"]
```

- [ ] **Step 2: Run the new tests, verify they fail**

Run: `cd /Users/tomarnett/magnolia && PYTHONPATH=scripts python3 -m pytest tests/test_granola_sync.py -k "placeholder or transcript_output or list_new or fetch_one or skips_placeholder" -v`
Expected: FAIL (helpers not defined).

- [ ] **Step 3: Implement** in `scripts/granola_sync.py`

Add constants near `MAX_NEW_PER_RUN` (line 20) and replace the tool constant:

```python
MIN_TRANSCRIPT_CHARS = 200          # below this, treat as a summary/placeholder stub
GRANOLA_LIST_TOOLS = "mcp__claude_ai_Granola__list_meetings"
GRANOLA_TRANSCRIPT_TOOLS = "mcp__claude_ai_Granola__get_meeting_transcript"
```

Remove the old `GRANOLA_TOOLS` constant (lines 23-24) and the old `_fetch_prompt` (lines 73-84). Replace with the two prompt builders:

```python
def _list_prompt(seen_ids):
    return (
        "Use the Granola MCP. Call list_meetings(time_range='last_30_days'). "
        "Return STRICT JSON: a JSON array of "
        '{"id","title","created_at","attendees"} for every meeting, and NOTHING '
        "else. Do not include transcripts. Already-downloaded ids (you may still "
        "list them; they are filtered locally): " + json.dumps(sorted(seen_ids)) + "."
    )


def _transcript_prompt(meeting_id):
    return (
        "Use the Granola MCP. Call get_meeting_transcript(meeting_id="
        f"'{meeting_id}'). Return STRICT JSON: " '{"transcript": "<the full '
        'verbatim transcript text>"} and NOTHING else. Do NOT summarize, '
        "abbreviate, or describe the transcript - return the literal text. "
        'If no transcript is available, return {"transcript": null}.'
    )
```

Replace `_fetch_new_meetings` (lines 131-153) with the orchestrator plus the new seams and a shared runner:

```python
def _run_claude(prompt, tools, root=None):
    """Run one headless `claude -p` with the Granola MCP. Returns stdout or None.
    One retry on subprocess failure; parse failures are handled by callers."""
    cmd = ["claude", "-p", prompt, "--model", _model(root),
           "--output-format", "json", "--allowedTools", tools,
           "--permission-mode", "bypassPermissions", "--max-turns", "30"]
    env = transcript_post._hook_env()    # strips CLAUDECODE so nested claude -p runs
    for attempt in (1, 2):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=FETCH_TIMEOUT, env=env,
                                 cwd=str(profile_lib.PM_OS_DIR))
        except Exception as exc:
            log.error("claude -p failed (attempt %d): %s", attempt, exc)
            continue
        return out.stdout
    return None


def _parse_transcript_output(stdout):
    """Extract the transcript string from claude -p output. Mirrors
    _parse_fetch_output's envelope handling, but pulls a {"transcript": ...}
    object. Returns the transcript string, or None."""
    if not stdout:
        return None
    text = stdout.strip()
    try:
        outer = json.loads(text)
        if isinstance(outer, dict) and "transcript" not in outer:
            text = outer.get("result", text)
    except json.JSONDecodeError:
        pass
    if not isinstance(text, str):
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    t = obj.get("transcript")
    return t if isinstance(t, str) else None


def _looks_like_placeholder(text):
    """True when content is missing, too short, or a known summary stub - so the
    caller skips it (and does NOT mark it seen) and re-tries on the next run."""
    if not isinstance(text, str):
        return True
    t = text.strip()
    if len(t) < MIN_TRANSCRIPT_CHARS:
        return True
    if t.startswith("[Full transcript available"):
        return True
    return False


def _list_new_meetings(state_or_ids, root=None):
    """Phase 1: list meeting metadata (no transcripts). Returns dicts not yet seen."""
    seen = set(state_or_ids)
    meetings = _parse_fetch_output(
        _run_claude(_list_prompt(_prompt_ids(state_or_ids)), GRANOLA_LIST_TOOLS, root=root))
    if not meetings:
        return []
    return [m for m in meetings if m.get("id") and m.get("id") not in seen]


def _fetch_one_transcript(meeting_id, root=None):
    """Phase 2: fetch ONE transcript verbatim. Returns the text or None."""
    return _parse_transcript_output(
        _run_claude(_transcript_prompt(meeting_id), GRANOLA_TRANSCRIPT_TOOLS, root=root))


def _fetch_new_meetings(state_or_ids, root=None):
    """THE seam main() calls. List new meetings, then fetch each transcript one at
    a time (reliable verbatim content). Meetings whose transcript is missing or a
    placeholder are skipped - not returned, so they stay unseen and re-try."""
    seen = set(state_or_ids)
    out = []
    for m in _list_new_meetings(state_or_ids, root=root):
        mid = m.get("id")
        if not mid or mid in seen:
            continue
        transcript = _fetch_one_transcript(mid, root=root)
        if _looks_like_placeholder(transcript):
            log.warning("  skipping %s - transcript missing or placeholder", mid)
            continue
        out.append({"id": mid, "title": m.get("title"),
                    "created_at": m.get("created_at"),
                    "attendees": m.get("attendees"), "transcript": transcript})
        if len(out) >= MAX_NEW_PER_RUN:
            break
    return out
```

- [ ] **Step 4: Run tests, verify pass** (new + existing)

Run: `cd /Users/tomarnett/magnolia && PYTHONPATH=scripts python3 -m pytest tests/test_granola_sync.py -v`
Expected: all pass (new tests + the existing provider-gate/dedup/basename/downstream/_prompt_ids tests, which monkeypatch `_fetch_new_meetings` and are unaffected).

- [ ] **Step 5: Four gates**

Run:
```bash
cd /Users/tomarnett/magnolia && python3 -m pytest -q && python3 scripts/card_schema.py && \
python3 -m pytest tests/test_engine_no_jay.py -q && python3 scripts/portability_gate.py
```
Expected: pytest green, `registry.json OK`, no-jay green, `portability OK`.

- [ ] **Step 6: Commit**

```bash
git add scripts/granola_sync.py tests/test_granola_sync.py
git commit -m "feat(granola): per-meeting transcript fetch with placeholder guard

Fetch one transcript per claude -p call (list metadata, then get_meeting_transcript
per meeting) instead of batching many into one response that the model summarized.
Skip-and-retry any transcript that comes back empty or as a summary stub.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Controller steps (operational - run after Task 1 is reviewed clean)

These are environment/data/verification actions, not code tasks:

- [ ] **Install openai** (restores classification): `python3 -m pip install -r requirements-transcript.txt` (or at minimum `python3 -m pip install openai`); confirm `python3 -c "import openai"`.
- [ ] **Purge the 15 stub artifacts** so real transcripts re-fetch: remove the stub `.txt` files in `datasets/meetings/unknown/` written during the broken run, and delete their entries from `profile/transcript/granola_downloaded.json`. Back up the ledger first.
- [ ] **Live verify:** run `python3 scripts/granola_sync.py`; confirm real KB-sized transcripts written, classified into `datasets/meetings/<domain>/<YYYY-MM>/*.md` with frontmatter, and tasks created in `datasets/tasks/`. Confirm prod board on `:8742` is untouched.

## Self-review

- Spec coverage: two-phase fetch (Task 1), placeholder guard (Task 1), openai install + stub purge + live verify (controller steps). Covered.
- Type consistency: `_fetch_new_meetings` keeps its shape; helper names match between plan tasks and tests.
- No placeholders: all code and test bodies are complete.
