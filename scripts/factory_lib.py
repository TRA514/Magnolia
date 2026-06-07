"""scripts/factory_lib.py — shared mechanism for the meta-create-* factory skills.

Two jobs:
  1. commit_and_emit_receipt() — stage EXACTLY the scaffolded files (precise
     staging, not `git add -A`), commit, and emit a `receipt` card carrying
     revert_commit + receipt_summary. The existing task_server.undo_receipt
     git-revert handler powers one-tap Undo unchanged. Git stays invisible — the
     board only ever shows Keep / Undo.
  2. validate_worker() — structural gate for a scaffolded worker .md (frontmatter
     parses + required fields). Denylist-cleanliness is enforced separately by the
     standing tests/test_engine_no_jay.py guard, so it is not duplicated here.
"""
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PM_OS_DIR = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import task_lib  # noqa: E402

_REQUIRED_WORKER_FIELDS = ("name", "description", "priority", "tier", "match",
                           "allowed_tools", "timeout", "max_turns")


class FactoryError(RuntimeError):
    """A factory step failed in an operator-actionable way."""


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def commit_and_emit_receipt(summary, files, kind, root=None):
    """Stage exactly `files`, commit, emit a receipt card. Returns the receipt task id.

    summary : human one-liner shown on the card ("a sample worker").
    files   : repo-relative paths the factory created/modified (precise staging).
    kind    : 'worker' | 'card-type' | 'adapter' (stored as factory_kind).
    Raises FactoryError if `files` is empty or nothing was staged (so a no-op
    scaffold can't strand a dangling receipt)."""
    repo = root or PM_OS_DIR
    if not files:
        raise FactoryError("no files to commit")
    add = _git(repo, "add", "--", *files)
    if add.returncode != 0:
        raise FactoryError(f"git add failed: {add.stderr.strip()[:300]}")
    # `git diff --cached --quiet` returns 0 when NOTHING is staged.
    if _git(repo, "diff", "--cached", "--quiet").returncode == 0:
        raise FactoryError("scaffold produced no committable changes")
    commit = _git(repo, "commit", "-m", f"factory: {summary}")
    if commit.returncode != 0:
        raise FactoryError(f"git commit failed: {commit.stderr.strip()[:300]}")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    receipt_id, _ = task_lib.create_task(
        f"Built: {summary}", queue="human", domain="ops", creator="agent",
        description="The factory built this for you. One-tap Undo reverts it cleanly.",
        card_type="receipt")
    task_lib.update_task(receipt_id, changes={
        "revert_commit": sha,
        "receipt_summary": summary,
        "factory_kind": kind,
    })
    return receipt_id


def validate_worker(path, root=None):
    """Return a list of structural problems with a scaffolded worker .md ([] = ok)."""
    import task_dispatch
    problems = []
    try:
        fm, body = task_dispatch._parse_worker_frontmatter(path)
    except Exception as e:
        return [f"frontmatter did not parse: {e}"]
    if not fm:
        return ["frontmatter did not parse"]
    for field in _REQUIRED_WORKER_FIELDS:
        if field not in fm:
            problems.append(f"missing required field: {field}")
    if not (body or "").strip():
        problems.append("empty prompt body")
    return problems


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("commit-and-receipt")
    c.add_argument("--summary", required=True)
    c.add_argument("--kind", required=True)
    c.add_argument("files", nargs="+")
    v = sub.add_parser("validate-worker")
    v.add_argument("path")
    args = ap.parse_args()
    if args.cmd == "commit-and-receipt":
        print(commit_and_emit_receipt(args.summary, args.files, args.kind))
    elif args.cmd == "validate-worker":
        probs = validate_worker(args.path)
        if probs:
            print("\n".join(probs)); sys.exit(1)
        print("ok")
