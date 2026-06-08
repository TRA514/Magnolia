#!/usr/bin/env python3
"""
eval_digest.py — Deterministic negative-signal pull for the weekly feedback-loop
improvement pass (ROADMAP §1 / cron #5).

Reads negative eval signal from TASK FRONTMATTER (not LangFuse): judge scores
written by judge.py (judge_score / judge_why / judge_kind / judge_scored_at) and
human reactions written by the task board (human_react / human_react_note /
human_reacted_at). A task is negative when its judge_score is below
JUDGE_GOOD_THRESHOLD or a human reacted thumbs-down. Negative tasks are clustered
by pipeline step (judge_kind) and by worker/task-type, producing structured raw
material for the eval-analyst worker. No LLM here — deterministic data layer.

Reading from frontmatter (via task_lib's list_tasks/list_archived projections)
means teammates without a running LangFuse stack still get a useful digest. The
output shape (digest.json / digest.md keys) is unchanged so the downstream
eval-analyst worker contract holds.

Usage:
    python3 scripts/eval_digest.py                  # last 7 days
    python3 scripts/eval_digest.py --days 14
    python3 scripts/eval_digest.py --all            # full history (backfill)
    python3 scripts/eval_digest.py --out datasets/evals/feedback-loop/2026-06-05/

Outputs (to --out, default datasets/evals/feedback-loop/{date}[-backfill]/):
    digest.json   structured, for the agent
    digest.md     human-readable

Exit 0 even on error (writes a stub report) — safe under headless cron dispatch.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import task_lib
import chat_transcript

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
FEEDBACK_DIR = PROJECT_DIR / "datasets" / "evals" / "feedback-loop"

JUDGE_GOOD_THRESHOLD = 7  # mirror task_server.JUDGE_GOOD_THRESHOLD
FOLLOW_UP_SAMPLE_CHARS = 160  # trim each follow-up sample text to this length
FOLLOW_UP_SAMPLE_CAP = 3      # max sample texts per group / per item


# ── Signal logic ──────────────────────────────────────────────────────────────


def _group_key(t):
    """Cluster key mirroring the by_worker clustering (task_type → domain → fallback)."""
    return t.get("task_type") or t.get("domain") or "uncategorized"


def _is_followup(event):
    """A post-run chat follow-up is a user turn that originated in chat after the
    agent's first pass. Missing origin/post_run are treated as not-a-follow-up."""
    if not isinstance(event, dict):
        return False
    return (event.get("role") == "user"
            and event.get("origin") == "chat"
            and event.get("post_run") is True)


def _trim(text):
    s = (text or "").strip()
    return s[:FOLLOW_UP_SAMPLE_CHARS]

def _is_negative(t):
    s = t.get("judge_score")
    if s is not None:
        try:
            if float(s) < JUDGE_GOOD_THRESHOLD:
                return True
        except (TypeError, ValueError):
            pass
    return t.get("human_react") == "down"


def _within_window(t, cutoff_iso):
    if cutoff_iso is None:
        return True
    stamp = t.get("judge_scored_at") or t.get("human_reacted_at") or t.get("updated") or ""
    return stamp >= cutoff_iso


def build_digest(window_days=7, all_history=False, out_dir=None):
    """Scan judged task frontmatter, cluster negative signal by step + worker.

    Returns the payload dict and writes digest.json + digest.md to out_dir.
    """
    now = datetime.now(timezone.utc)
    if all_history:
        cutoff_iso, window_label = None, "all history"
    else:
        cutoff = now - timedelta(days=window_days)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        window_label = f"last {window_days} days (since {cutoff.strftime('%Y-%m-%d')})"

    out = Path(out_dir) if out_dir else (FEEDBACK_DIR / now.strftime("%Y-%m-%d"))

    active = task_lib.list_tasks()
    archived = task_lib.list_archived(limit=2000)
    judged = [t for t in (active + archived)
              if (t.get("judge_score") is not None or t.get("human_react"))]
    judged = [t for t in judged if _within_window(t, cutoff_iso)]
    flagged = [t for t in judged if _is_negative(t)]

    by_step = defaultdict(lambda: {"flagged": 0, "comments": []})
    by_worker = defaultdict(lambda: {"flagged": 0})
    flagged_out = []
    for t in flagged:
        step = t.get("judge_kind") or "unknown"
        group = t.get("task_type") or t.get("domain") or "uncategorized"
        by_step[step]["flagged"] += 1
        note = (t.get("human_react_note") or "").strip()
        why = (t.get("judge_why") or "").strip()
        for c in (note, why):
            if c:
                by_step[step]["comments"].append(c)
        by_worker[group]["flagged"] += 1
        flagged_out.append({
            "trace_id": t["id"], "step": step, "session_id": t["id"],
            "task": {"task_id": t["id"], "title": t.get("title", ""),
                     "domain": t.get("domain", ""), "queue": t.get("queue", "")},
            "worker": group, "timestamp": t.get("judge_scored_at", ""),
            "negative_scores": [
                {"name": "judge", "value": t.get("judge_score"), "comment": why},
            ] + ([{"name": "human", "value": 0, "comment": note}] if t.get("human_react") == "down" else []),
            "output_summary": (t.get("agent_output") or "")[:240],
        })

    flagged_out.sort(key=lambda r: r["timestamp"] or "", reverse=True)

    # ── Post-run chat follow-ups ────────────────────────────────────────────
    # Scan the SAME windowed task set for chat follow-ups: user turns made in
    # chat AFTER the agent's first pass. Deterministic capture only — every
    # post-run follow-up is included; the eval-analyst worker decides what to
    # do with the clusters. Defensive: tasks without a transcript yield [].
    windowed = [t for t in (active + archived) if _within_window(t, cutoff_iso)]
    fu_by_group = defaultdict(lambda: {"count": 0, "samples": []})
    fu_items = []
    fu_total = 0
    for t in windowed:
        try:
            events = chat_transcript.read_events(t["id"])
        except Exception:
            events = []
        texts = [_trim(e.get("text")) for e in events if _is_followup(e)]
        if not texts:
            continue
        group = _group_key(t)
        fu_total += len(texts)
        g = fu_by_group[group]
        g["count"] += len(texts)
        for s in texts:
            if len(g["samples"]) < FOLLOW_UP_SAMPLE_CAP:
                g["samples"].append(s)
        fu_items.append({
            "task_id": t["id"], "title": t.get("title", ""), "group": group,
            "count": len(texts), "samples": texts[:FOLLOW_UP_SAMPLE_CAP],
        })
    fu_items.sort(key=lambda i: i["count"], reverse=True)
    follow_ups = {
        "total": fu_total,
        "tasks_with_follow_ups": len(fu_items),
        "by_group": dict(fu_by_group),
        "items": fu_items,
    }

    has_signal = bool(flagged_out) or fu_total > 0
    payload = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": window_label,
        "status": "ok" if has_signal else "clean",
        "totals": {"negative_scores": sum(len(r["negative_scores"]) for r in flagged_out),
                   "flagged_traces": len(flagged_out),
                   "follow_ups": fu_total},
        "by_step": dict(by_step), "by_worker": dict(by_worker), "flagged": flagged_out,
        "follow_ups": follow_ups,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "digest.json").write_text(json.dumps(payload, indent=2, default=str))
    _write_markdown(out / "digest.md", payload)
    return payload


# ── Output ────────────────────────────────────────────────────────────────────

def write_stub(out_dir, reason, window_label):
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": window_label,
        "status": "no-data",
        "reason": reason,
        "totals": {"negative_scores": 0, "flagged_traces": 0, "follow_ups": 0},
        "by_step": {}, "by_worker": {}, "flagged": [],
        "follow_ups": {"total": 0, "tasks_with_follow_ups": 0, "by_group": {}, "items": []},
    }
    (out_dir / "digest.json").write_text(json.dumps(payload, indent=2))
    (out_dir / "digest.md").write_text(
        f"# Feedback-loop digest — {window_label}\n\n"
        f"**Status:** no data — {reason}\n\nGenerated {payload['generated']}.\n")
    print(f"[eval_digest] {reason} — wrote stub to {out_dir}")


def _write_markdown(path, payload):
    lines = [f"# Feedback-loop digest — {payload['window']}", ""]
    t = payload["totals"]
    lines.append(f"Generated {payload['generated']}. Status: **{payload['status']}**.")
    lines += ["",
              f"- Negative scores: **{t['negative_scores']}**",
              f"- Flagged traces: **{t['flagged_traces']}**",
              f"- Post-run chat follow-ups: **{t.get('follow_ups', 0)}**", ""]
    if payload["status"] == "clean":
        lines.append("No negative signal in this window. Clean week.")
        path.write_text("\n".join(lines) + "\n")
        return

    lines += ["## By step", "", "| Step | Flagged | Sample comments |", "|---|---|---|"]
    for step, d in sorted(payload["by_step"].items(), key=lambda kv: -kv[1]["flagged"]):
        sample = "; ".join(c.replace("|", "/").replace("\n", " ") for c in d["comments"][:3])
        lines.append(f"| {step} | {d['flagged']} | {sample} |")
    lines.append("")

    if payload.get("by_worker"):
        lines += ["## By worker / task-type", "", "| Group | Flagged |", "|---|---|"]
        for g, d in sorted(payload["by_worker"].items(), key=lambda kv: -kv[1]["flagged"]):
            lines.append(f"| {g} | {d['flagged']} |")
        lines.append("")

    lines += ["## Flagged traces", ""]
    for r in payload["flagged"]:
        task = r.get("task") or {}
        title = task.get("title", "") if task else ""
        lines.append(f"### `{r['step']}` — {title or r.get('session_id') or r['trace_id']}")
        lines.append(f"- trace: `{r['trace_id']}` · task: `{r.get('session_id') or '—'}`"
                     f" · domain: {task.get('domain','—') if task else '—'} · {r['timestamp']}")
        for s in r["negative_scores"]:
            c = (s.get("comment") or "").strip()
            lines.append(f"- **{s['name']}** = {s['value']}" + (f" — \"{c}\"" if c else ""))
        if r.get("output_summary"):
            lines.append(f"- output: {r['output_summary']}")
        lines.append("")

    fu = payload.get("follow_ups") or {}
    if fu.get("total", 0) > 0:
        def _san(s):
            return (s or "").replace("|", "/").replace("\n", " ")
        lines += ["## Post-run chat follow-ups", "",
                  f"{fu['total']} follow-up turn(s) across {fu['tasks_with_follow_ups']} task(s) — "
                  "evidence the agent's first pass left something on the table.", "",
                  "| Group | Count | Sample follow-ups |", "|---|---|---|"]
        for g, d in sorted(fu.get("by_group", {}).items(), key=lambda kv: -kv[1]["count"]):
            sample = "; ".join(_san(s) for s in d.get("samples", [])[:3])
            lines.append(f"| {g} | {d['count']} | {sample} |")
        lines.append("")
        lines += ["### By task", ""]
        for item in fu.get("items", []):
            title = item.get("title") or item.get("task_id")
            lines.append(f"- **{title}** (`{item['task_id']}`, {item['group']}) — "
                         f"{item['count']} follow-up(s)")
            for s in item.get("samples", [])[:3]:
                lines.append(f"  - {_san(s)}")
        lines.append("")

    path.write_text("\n".join(lines) + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Task-frontmatter negative-signal digest")
    ap.add_argument("--days", type=int, default=7, help="lookback window in days (default 7)")
    ap.add_argument("--all", action="store_true", help="full history (ignore --days)")
    ap.add_argument("--out", default=None,
                    help="output dir (default datasets/evals/feedback-loop/{date}[-backfill])")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    date_slug = now.strftime("%Y-%m-%d")

    if args.all:
        window_label = "all history"
        default_out = FEEDBACK_DIR / f"{date_slug}-backfill"
    else:
        cutoff = now - timedelta(days=args.days)
        window_label = f"last {args.days} days (since {cutoff.strftime('%Y-%m-%d')})"
        default_out = FEEDBACK_DIR / date_slug

    out_dir = Path(args.out) if args.out else default_out
    if not out_dir.is_absolute():
        out_dir = PROJECT_DIR / out_dir

    try:
        payload = build_digest(window_days=args.days, all_history=args.all, out_dir=str(out_dir))
    except Exception as e:
        write_stub(out_dir, f"digest build failed: {e}", window_label)
        return 0

    print(f"[eval_digest] window={payload['window']}")
    print(f"[eval_digest] flagged {payload['totals']['flagged_traces']} tasks "
          f"with {payload['totals']['negative_scores']} negative scores")
    if payload["by_step"]:
        print("[eval_digest] by step:")
        for step, d in sorted(payload["by_step"].items(), key=lambda kv: -kv[1]["flagged"]):
            print(f"    {step}: {d['flagged']}")
    print(f"[eval_digest] wrote {out_dir}/digest.json + digest.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
