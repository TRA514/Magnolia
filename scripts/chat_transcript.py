"""Sidecar chat transcript persistence.

Stores a task's chat as one normalized JSON event per line in a sidecar
`.jsonl` file. This is Magnolia's own durable UI history, independent of
Claude Code's internal transcript. No LLM, no network — pure file append/read.

Event dicts look like:
    {"role","kind","text"|"steps","run_id","origin","post_run","turn_id","ts"}

This is a dumb persistence layer: no classification, no business logic.
"""

import datetime
import json
import os
import pathlib
import uuid

import task_lib


def _transcript_path(task_id):
    """Resolve the sidecar transcript path for a task.

    Uses a dedicated `_chat/` dir keyed by task id rather than co-locating
    next to the task `.md`, because tasks get moved to `_archive/` on
    completion — a co-located sidecar would be orphaned. This location is
    stable across archiving, and the digest reads archived tasks too.
    """
    return pathlib.Path(os.path.join(task_lib.TASKS_DIR, "_chat", f"{task_id}.chat.jsonl"))


def append_event(task_id, event):
    """Append a chat event to the task's sidecar transcript.

    Shallow-copies the event, stamping `turn_id` and `ts` if absent, then
    appends it as one JSON line. Returns the stamped event.
    """
    e = dict(event)
    if "turn_id" not in e:
        e["turn_id"] = uuid.uuid4().hex
    if "ts" not in e:
        e["ts"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = _transcript_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, default=str) + "\n")
    return e


def read_events(task_id):
    """Read all chat events for a task.

    Returns [] if the transcript doesn't exist. Parses each non-empty line,
    skipping malformed lines rather than crashing.
    """
    path = _transcript_path(task_id)
    if not path.exists():
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
    return events
