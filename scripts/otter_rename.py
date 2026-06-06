#!/usr/bin/env python3
"""
Backfill rename: rename existing transcript files to YYYY-MM-DD_HH-MM_title.txt format.
Parses YAML frontmatter for title/date/otter_id, extracts time from transcript body.
Updates downloaded.json final_path entries to reflect new filenames.

Usage:
    python3 otter_rename.py           # dry run — shows planned renames, no changes made
    python3 otter_rename.py --execute  # actually rename files and update downloaded.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ── Engine wiring ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402

# ── Paths (profile-driven) ───────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
MEETINGS_DIR = Path(profile_lib.PM_OS_DIR) / profile_lib.transcript_config()["target"]
STATE_FILE = Path(profile_lib.transcript_state_dir()) / "downloaded.json"


def safe_filename(name: str) -> str:
    """Strip characters that are unsafe in file names."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def build_new_stem(date: str, time: str, title: str) -> str:
    """Build YYYY-MM-DD_HH-MM_{sanitized_title} filename stem."""
    clean = safe_filename(title.strip())
    clean = re.sub(r"[_ ]{2,}", " ", clean).strip()
    return f"{date}_{time}_{clean}"


def parse_frontmatter(text: str) -> dict:
    """
    Parse YAML frontmatter block (---...---) from a transcript file.
    Returns dict of scalar key/value pairs. Skips list items (participants).
    Returns empty dict if no frontmatter found.
    """
    if not text.startswith("---"):
        return {}
    # Find the closing --- (must be at start of line, after at least one line)
    end_idx = text.find("\n---", 3)
    if end_idx == -1:
        return {}
    fm_block = text[3:end_idx]
    result = {}
    for line in fm_block.splitlines():
        # Skip list items (participants: - "name")
        if line.startswith("  ") or not line.strip() or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # Remove surrounding double-quotes and unescape internal ones
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1].replace('\\"', '"')
        if key and val:
            result[key] = val
    return result


def extract_body_time(text: str) -> str:
    """
    Find the 'Date: YYYY-MM-DD HH:MM' line in the transcript body (after frontmatter).
    Returns 'HH-MM' string, or '' if not found (manual files, missing time).
    """
    # Skip past frontmatter if present
    body = text
    if text.startswith("---"):
        end_idx = text.find("\n---", 3)
        if end_idx != -1:
            body = text[end_idx + 4:]  # position after \n---\n

    for line in body.splitlines()[:10]:
        m = re.match(r"Date:\s*\d{4}-\d{2}-\d{2}\s+(\d{2}):(\d{2})", line)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    return ""


def unique_path(target: Path, assigned: set) -> Path:
    """
    Return target path unchanged if no collision, otherwise append _2, _3 etc.
    Checks both filesystem (existing files) and the assigned set (same-run collisions).
    """
    if not target.exists() and str(target) not in assigned:
        return target
    stem = target.stem
    parent = target.parent
    n = 2
    while True:
        candidate = parent / f"{stem}_{n}.txt"
        if not candidate.exists() and str(candidate) not in assigned:
            return candidate
        n += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Rename meeting transcripts to dated format")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually rename files and update downloaded.json (default: dry run)",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    if dry_run:
        print("── DRY RUN — no changes will be made ──────────────────────────────────")
    else:
        print("── EXECUTING renames ────────────────────────────────────────────────────")

    # Load state
    state = {}
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            state = json.load(f)

    # Build reverse map: old final_path string → speech_id (for files w/o otter_id in FM)
    path_to_id: dict[str, str] = {}
    for sid, info in state.items():
        if "final_path" in info:
            path_to_id[info["final_path"]] = sid

    renames: list[tuple[Path, Path, str | None]] = []  # (old, new, otter_id)
    skipped: list[Path] = []
    errors: list[tuple[Path, str]] = []
    assigned_new: set[str] = set()

    for txt_path in sorted(MEETINGS_DIR.rglob("*.txt")):
        text = txt_path.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)

        if not fm:
            errors.append((txt_path, "no frontmatter — skipping"))
            continue

        title = fm.get("title", "").strip()
        date = fm.get("date", "").strip()
        otter_id = fm.get("otter_id", "").strip() or None

        if not title:
            errors.append((txt_path, "missing title in frontmatter — skipping"))
            continue
        if not date:
            errors.append((txt_path, "missing date in frontmatter — skipping"))
            continue

        time_str = extract_body_time(text) or "00-00"
        new_stem = build_new_stem(date, time_str, title)
        new_path = txt_path.parent / f"{new_stem}.txt"

        if new_path == txt_path:
            skipped.append(txt_path)
            continue

        final_path = unique_path(new_path, assigned_new)
        assigned_new.add(str(final_path))
        renames.append((txt_path, final_path, otter_id))

    # ── Summary header ────────────────────────────────────────────────────────
    print(f"\nFiles to rename : {len(renames)}")
    print(f"Already correct : {len(skipped)}")
    if errors:
        print(f"Skipped (errors): {len(errors)}")
    print()

    for old_path, new_path, _ in renames:
        folder = old_path.relative_to(MEETINGS_DIR).parent
        print(f"  {folder}/")
        print(f"    {old_path.name}")
        print(f"  → {new_path.name}")
        print()

    if errors:
        print("── Skipped ──────────────────────────────────────────────────────────────")
        for p, reason in errors:
            print(f"  {p.name}: {reason}")
        print()

    if dry_run:
        print("── Dry run complete — run with --execute to apply renames ────────────────")
        return

    # ── Execute ───────────────────────────────────────────────────────────────
    renamed_count = 0
    state_updated = 0

    for old_path, new_path, otter_id in renames:
        try:
            old_path.rename(new_path)
            renamed_count += 1

            # Determine which speech_id to update
            sid = otter_id
            if not sid:
                # Fall back to reverse-lookup by old path
                sid = path_to_id.get(str(old_path))

            if sid and sid in state:
                state[sid]["final_path"] = str(new_path)
                state_updated += 1

        except Exception as exc:
            print(f"  ERROR renaming {old_path.name}: {exc}", file=sys.stderr)

    # Save updated downloaded.json
    if state_updated > 0:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    print("── Done ─────────────────────────────────────────────────────────────────")
    print(f"  Renamed              : {renamed_count} file(s)")
    print(f"  downloaded.json rows : {state_updated} updated")


if __name__ == "__main__":
    main()
