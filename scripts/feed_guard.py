"""Guard the single-transcript-feed guarantee.

Scans for OTHER downloaders that could write transcripts outside Magnolia.
Detection is conservative — it reports candidates; disabling is a separate,
user-confirmed step (Claude calls disable() only after the human says yes).
"""
import glob
import os
import re

# Signals that a LaunchAgent is a transcript downloader.
_SIGNAL_RE = re.compile(r"otter|granola|transcript|meeting[-_]?sync", re.IGNORECASE)


def detect_competing(launch_agents_dir=None, own_labels=None):
    own = set(own_labels or [])
    d = launch_agents_dir or os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
    found = []
    for path in sorted(glob.glob(os.path.join(d, "*.plist"))):
        text = open(path, encoding="utf-8", errors="ignore").read()
        m = re.search(r"<key>Label</key>\s*<string>([^<]+)</string>", text)
        label = m.group(1) if m else os.path.basename(path)[:-6]
        if label in own:
            continue
        if _SIGNAL_RE.search(text):
            found.append({"label": label, "path": path})
    return found


def disable(path, activate=True):
    """Disable a competing LaunchAgent (user-confirmed). Renames it aside; never deletes."""
    if activate:
        import subprocess
        subprocess.run(["launchctl", "unload", path], capture_output=True)
    disabled = path + ".disabled-by-magnolia"
    os.rename(path, disabled)
    return disabled
