#!/usr/bin/env python3
"""
Otter.ai transcript sync script.
Downloads new speeches to the profile's transcript target (datasets/meetings/YYYY-MM/) as TXT.
Tracks state in downloaded.json (under the profile transcript state dir) to avoid re-downloading.
Logs activity to otter_sync.log in the same state dir.

Requires a valid session.json — run otter_auth.py first (or again if expired).
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from otterai import OtterAI
except ImportError:  # optional third-party dep; absent on machines without Otter sync
    OtterAI = None

# ── Engine wiring ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402
import transcript_post  # noqa: E402

# ── Config ─────────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 30  # seconds — prevents indefinite hangs
SESSION_EXPIRY_WARN_DAYS = 3  # create a task this many days before session expires
CRITICAL_COOKIES = ("sessionid", "ot_uid")  # cookies that gate API access


def _timeout_wrapper(original_request, default_timeout):
    """Wrap requests.Session.request to inject a default timeout."""
    def wrapper(*args, **kwargs):
        kwargs.setdefault("timeout", default_timeout)
        return original_request(*args, **kwargs)
    return wrapper


# ── Paths (profile-driven) ───────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
STATE_DIR = Path(profile_lib.transcript_state_dir())
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Meetings deposit target = PM_OS_DIR + transcript_config()["target"]
MEETINGS_DIR = Path(profile_lib.PM_OS_DIR) / profile_lib.transcript_config()["target"]
STATE_FILE = STATE_DIR / "downloaded.json"
SESSION_FILE = STATE_DIR / "session.json"
LOG_FILE = STATE_DIR / "otter_sync.log"

# Correct base is forward/api/v1/ (not forward/user/api/v1/)
OTTER_USER_URL = "https://otter.ai/forward/api/v1/user"

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def notify(title: str, message: str) -> None:
    """Send a macOS notification via osascript (no-op off macOS)."""
    if not shutil.which("osascript"):
        return
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def check_session_expiry(state: dict) -> None:
    """
    Proactively check session cookie expiry dates.
    If critical cookies expire within SESSION_EXPIRY_WARN_DAYS, log a warning.
    Uses state file to avoid duplicate alerts.
    """
    if not SESSION_FILE.exists():
        return

    with open(SESSION_FILE) as f:
        session = json.load(f)

    # Find the earliest expiry among critical auth cookies
    earliest_expiry = None
    for cookie in session.get("cookies", []):
        if cookie.get("name") in CRITICAL_COOKIES:
            expires = cookie.get("expires", -1)
            if expires > 0:  # -1 means session cookie (no persistent expiry)
                if earliest_expiry is None or expires < earliest_expiry:
                    earliest_expiry = expires

    if earliest_expiry is None:
        return

    expiry_dt = datetime.fromtimestamp(earliest_expiry)
    days_left = (expiry_dt - datetime.now()).total_seconds() / 86400

    if days_left > SESSION_EXPIRY_WARN_DAYS:
        log.info("Session expires %s (%.1f days) — no action needed", expiry_dt.strftime("%Y-%m-%d"), days_left)
        return

    log.warning("Session expires %s (%.1f days) — re-run otter_auth.py to reauth", expiry_dt.strftime("%Y-%m-%d"), days_left)


def safe_filename(name: str) -> str:
    """Strip characters that are unsafe in file names."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def _build_dated_basename(created_at, title: str) -> str:
    """Build YYYY-MM-DD_HH-MM_{sanitized_title} filename stem."""
    if isinstance(created_at, (int, float)):
        dt = datetime.fromtimestamp(created_at)
    else:
        dt = datetime.fromisoformat(str(created_at))
    date_part = dt.strftime("%Y-%m-%d")
    time_part = dt.strftime("%H-%M")
    clean = safe_filename(title.strip())
    clean = re.sub(r"[_ ]{2,}", " ", clean).strip()
    return f"{date_part}_{time_part}_{clean}"


def month_dir(created_at) -> Path:
    """Return the YYYY-MM subdirectory under MEETINGS_DIR, creating it if needed."""
    if isinstance(created_at, (int, float)):
        dt = datetime.fromtimestamp(created_at)
    else:
        dt = datetime.fromisoformat(str(created_at))
    folder = MEETINGS_DIR / dt.strftime("%Y-%m")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_session(otter: OtterAI) -> bool:
    """
    Inject saved Playwright session cookies into the OtterAI client.
    Sets both otter._session.cookies and otter._cookies (needed for CSRF).
    Verifies the session is still valid and sets otter._userid.
    Returns True on success, False if session is missing or expired.
    """
    if not SESSION_FILE.exists():
        msg = "No session.json found. Run: python3 scripts/otter_auth.py"
        log.error(msg)
        notify("Otter Sync — Action Required", msg)
        return False

    with open(SESSION_FILE) as f:
        state = json.load(f)

    cookies_dict = {}
    for cookie in state.get("cookies", []):
        name = cookie["name"]
        value = cookie["value"]
        otter._session.cookies.set(
            name,
            value,
            domain=cookie.get("domain", "").lstrip("."),
            path=cookie.get("path", "/"),
        )
        cookies_dict[name] = value

    # download_speech() reads from otter._cookies for the csrftoken header
    otter._cookies = cookies_dict

    resp = otter._session.get(OTTER_USER_URL, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        msg = "Session expired. Run: python3 scripts/otter_auth.py"
        log.error("Session expired (HTTP %s). Re-authenticate: python3 %s/otter_auth.py", resp.status_code, SCRIPT_DIR)
        notify("Otter Sync — Action Required", msg)
        return False

    userid = resp.json().get("userid")
    if not userid:
        msg = "Could not read userid. Run: python3 scripts/otter_auth.py"
        log.error("Could not read userid from session. Re-authenticate: python3 %s/otter_auth.py", SCRIPT_DIR)
        notify("Otter Sync — Action Required", msg)
        return False

    otter._userid = str(userid)
    log.info("Session valid (userid=%s)", otter._userid)
    return True


def format_timestamp(ms: int) -> str:
    """Convert milliseconds offset to HH:MM:SS."""
    s = ms // 1000
    h, remainder = divmod(s, 3600)
    m, sec = divmod(remainder, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def extract_transcript(speech_data: dict) -> str:
    """Build a readable transcript from the speech API response."""
    speech = speech_data.get("data", {}).get("speech", {})

    # Build speaker ID → name map
    speaker_map = {
        str(s["id"]): s.get("speaker_name") or "Unknown"
        for s in speech.get("speakers", [])
    }

    utterances = speech.get("transcripts", [])
    if not utterances:
        return ""

    lines = []
    title = speech.get("title", "").strip()
    date_ts = speech.get("start_time") or speech.get("created_at")
    if date_ts:
        date_str = datetime.fromtimestamp(date_ts).strftime("%Y-%m-%d %H:%M")
        lines.append(f"# {title}")
        lines.append(f"Date: {date_str}")
        lines.append("")

    for u in utterances:
        speaker_id = str(u.get("speaker_id", ""))
        speaker = speaker_map.get(speaker_id, "Unknown")
        text = u.get("transcript", "").strip()
        ts = format_timestamp(u.get("start_offset", 0))
        if text:
            lines.append(f"[{ts}] {speaker}: {text}")

    return "\n".join(lines)


def main() -> None:
    if OtterAI is None:
        sys.stderr.write("otterai not installed — Otter sync unavailable on this machine. "
                         "Install with: pip install otterai\n")
        sys.exit(1)

    # ── Load session ───────────────────────────────────────────────────────────
    otter = OtterAI()
    # Set default timeout on all requests made through this session
    otter._session.request = _timeout_wrapper(otter._session.request, REQUEST_TIMEOUT)
    if not load_session(otter):
        sys.exit(1)

    # ── Check session expiry proactively ──────────────────────────────────────
    state = load_state()
    check_session_expiry(state)

    # ── Fetch speech list ──────────────────────────────────────────────────────
    try:
        speeches_result = otter.get_speeches()
    except Exception as exc:
        log.error("Failed to fetch speech list: %s", exc)
        notify("Otter Sync — Error", f"Failed to fetch speeches: {exc}")
        sys.exit(1)
    speeches = speeches_result.get("data", {}).get("speeches", [])
    log.info("Found %d speech(es) on Otter", len(speeches))

    new_count = 0

    for speech in speeches:
        speech_id = speech.get("otid") or speech.get("id") or speech.get("speech_id")
        if not speech_id:
            log.warning("Speech missing ID, skipping: %s", speech)
            continue

        speech_id = str(speech_id)
        if speech_id in state:
            continue  # already downloaded

        # Skip speeches that are still recording or being processed
        process_finished = speech.get("process_finished")
        is_ongoing = speech.get("recording") or speech.get("is_ongoing") or speech.get("ongoing")
        status = speech.get("status", "")
        if is_ongoing or status in ("in_progress", "recording") or process_finished is False:
            title = speech.get("title") or speech.get("summary") or "untitled"
            log.info("Skipping in-progress recording: %s (%s)", title, speech_id)
            continue

        title = speech.get("title") or speech.get("summary") or "untitled"
        created_at = speech.get("created_at") or speech.get("start_time")
        log.info("Downloading: %s (%s)", title, speech_id)

        try:
            folder = month_dir(created_at) if created_at else MEETINGS_DIR / "unknown"
            folder.mkdir(parents=True, exist_ok=True)
            if created_at:
                base_name = _build_dated_basename(created_at, title)
            else:
                base_name = safe_filename(title.strip())

            # ── TXT transcript ─────────────────────────────────────────────────
            speech_data = otter.get_speech(speech_id)
            transcript_text = extract_transcript(speech_data)

            txt_path = None
            if transcript_text:
                txt_path = folder / f"{base_name}.txt"
                txt_path.write_text(transcript_text, encoding="utf-8")
                log.info("  Saved TXT: %s", txt_path)
            else:
                log.warning("  No transcript text found for %s", speech_id)

            # ── Update state ───────────────────────────────────────────────────
            state[speech_id] = {
                "title": title,
                "downloaded_at": datetime.now().isoformat(),
                "folder": str(folder),
            }

            # ── Classify, add front matter, fire task-extract + qmd hooks ──────
            if txt_path:
                final_path = transcript_post.run_downstream(txt_path, speech_id, state, log)
                state[speech_id]["final_path"] = final_path
            save_state(state)
            new_count += 1

        except Exception as exc:
            log.error("  Failed to process %s: %s", speech_id, exc)

    if new_count == 0:
        log.info("No new speeches to download")
    else:
        log.info("Downloaded %d new speech(es)", new_count)
        notify("Otter Sync", f"Downloaded {new_count} new transcript(s) → {MEETINGS_DIR}")


if __name__ == "__main__":
    main()
