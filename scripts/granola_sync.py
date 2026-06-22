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
SEEN_IN_PROMPT = 200          # cap ledger ids interpolated into the fetch prompt
FETCH_TIMEOUT = 300           # seconds for the claude -p subprocess
MIN_TRANSCRIPT_CHARS = 200          # below this, treat as a summary/placeholder stub
GRANOLA_LIST_TOOLS = "mcp__claude_ai_Granola__list_meetings"
GRANOLA_TRANSCRIPT_TOOLS = "mcp__claude_ai_Granola__get_meeting_transcript"
# The transcript fetch only needs the model to INVOKE one tool (we scrape the raw
# tool_result; the model never reproduces the transcript, so its output is tiny).
# Haiku is unreliable at actually calling the tool - it wanders or skips it - so the
# fetch uses a stronger model. Cost stays modest because the output is tiny.
TRANSCRIPT_MODEL = "claude-sonnet-4-6"

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


def _basename(created_at, title, mid=None):
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        stamp = dt.strftime("%Y-%m-%d_%H-%M")
    except Exception:
        dt, stamp = None, "unknown"
    clean = re.sub(r"[_ ]{2,}", " ", safe_filename(title)).strip() or "untitled"
    # Suffix a short id slice so same minute+title across meetings can't collide.
    suffix = (mid or "")[:8]
    base = f"{stamp}_{clean}_{suffix}" if suffix else f"{stamp}_{clean}"
    return base, dt


def _load_state(root=None):
    f = _state_file(root)
    return json.loads(f.read_text()) if f.exists() else {}


def _save_state(state, root=None):
    f = _state_file(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, indent=2))


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
        f"'{meeting_id}') exactly once, then reply with just: OK. Do NOT repeat, "
        "echo, or summarize the transcript in your reply."
    )


def _parse_fetch_output(stdout):
    """claude --output-format json wraps the result; the model's text is the
    payload. Find the JSON array. Returns list, or None if unparseable."""
    if not stdout:
        return None
    text = stdout.strip()
    try:
        outer = json.loads(text)
        if isinstance(outer, dict):
            text = outer.get("result", text)
    except json.JSONDecodeError:
        pass
    if isinstance(text, list):
        return text
    if not isinstance(text, str):
        # e.g. {"result": null} / {"result": 42} / {"result": {...}}
        return None
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(text[start:end + 1])
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


def _prompt_ids(state_or_ids):
    """Cap the ledger ids interpolated into the fetch prompt to a recent slice.
    The LOCAL post-fetch filter (using the FULL seen set) is the authoritative
    dedup — this only bounds prompt size. If we got a dict keyed by UUID with
    `downloaded_at`, take the most-recently-downloaded N; else a plain slice."""
    if isinstance(state_or_ids, dict):
        def _recency(k):
            v = state_or_ids.get(k)
            if isinstance(v, dict):
                return v.get("downloaded_at") or ""
            # legacy ledger: value is the downloaded filename (date-prefixed),
            # which sorts newest-first just like downloaded_at. Non-str -> "".
            return v if isinstance(v, str) else ""
        ordered = sorted(state_or_ids, key=_recency, reverse=True)
        return ordered[:SEEN_IN_PROMPT]
    return list(state_or_ids)[:SEEN_IN_PROMPT]


def _run_claude(prompt, tools, root=None, stream=False, model=None):
    """Run one headless `claude -p` with the Granola MCP. Returns stdout or None.
    One retry on subprocess failure; parse failures are handled by callers.
    When stream=True, uses --output-format stream-json --verbose so tool_result
    events are captured verbatim in the raw NDJSON output. `model` overrides the
    configured model (the transcript fetch uses a stronger one for reliable tool
    calls). Do NOT restrict the tool set: the Granola MCP tools are deferred and the
    model needs ToolSearch/ListMcpResourcesTool to discover them before calling."""
    fmt_args = (["--output-format", "stream-json", "--verbose"]
                if stream else ["--output-format", "json"])
    cmd = ["claude", "-p", prompt, "--model", model or _model(root),
           *fmt_args, "--allowedTools", tools,
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


def _parse_stream_transcript(stdout):
    """Scrape the verbatim transcript from a claude -p stream-json run: find the
    get_meeting_transcript tool_result and return its transcript field. The model
    never reproduces the text, so this is reliable. Returns str or None."""
    if not stdout:
        return None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "user":
            continue
        msg = event.get("message") or {}
        for block in (msg.get("content") or []) if isinstance(msg, dict) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            inner = block.get("content")
            inner_list = inner if isinstance(inner, list) else []
            for item in inner_list:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                try:
                    payload = json.loads(item.get("text") or "")
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and isinstance(payload.get("transcript"), str):
                    return payload["transcript"]
    return None


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
    """Fetch ONE transcript by scraping the raw get_meeting_transcript tool_result
    from a stream-json claude -p run. The model only invokes the tool (tiny output),
    so the transcript is never summarized/truncated. Returns the text or None."""
    return _parse_stream_transcript(
        _run_claude(_transcript_prompt(meeting_id), GRANOLA_TRANSCRIPT_TOOLS,
                    root=root, stream=True, model=TRANSCRIPT_MODEL))


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


def main(root=None):
    if not log.handlers:
        logging.basicConfig(level=logging.INFO,
            format="%(asctime)s  %(levelname)s  %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)])
    # Provider gate — the Engine-tab switch.
    provider = profile_lib.transcript_config(root)["provider"]
    if provider != "granola":
        log.info("transcript provider is not granola (%s) — skipping", provider)
        return {"status": "skipped", "provider": provider}

    Path(_state_dir(root)).mkdir(parents=True, exist_ok=True)
    state = _load_state(root)
    meetings = _fetch_new_meetings(state, root=root)
    log.info("Granola returned %d new meeting(s)", len(meetings))

    new_count = 0
    for m in meetings:
        mid = m.get("id")
        if not mid or mid in state:
            continue
        base, dt = _basename(m.get("created_at"), m.get("title"), mid)
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
        # Already marked seen + the .txt write succeeded; isolate downstream so one
        # bad meeting can't abort the loop. On error, log and continue (stays seen).
        try:
            final_path = transcript_post.run_downstream(txt_path, mid, state, log)
            state[mid]["final_path"] = str(final_path)
            _save_state(state, root)
        except Exception as exc:
            log.error("  Downstream failed for %s: %s", mid, exc)
            _save_state(state, root)
            continue
        new_count += 1

    log.info("Downloaded %d new Granola transcript(s)", new_count)
    return {"status": "ok", "provider": "granola", "new": new_count}


if __name__ == "__main__":
    print(main())
