#!/usr/bin/env python3
"""Send an Outlook email or a Teams chat message via the `mgc` Microsoft Graph CLI.

This is the message-sending sibling of create_calendar_event.py: pure payload
builders + a thin, mockable mgc subprocess runner, callable as a library (from
the messaging adapter / board handler) or from the CLI with --dry-run.

It performs an EXTERNAL WRITE. It is only ever reached through the Tier-2 gate
(adapters.publish("messaging", ...) → m365 provider → here); this module itself
does not gate — it just sends.

Graph references:
  - email: POST /me/sendMail            (scope Mail.Send)
  - teams: POST /chats (oneOnOne/group) then POST /chats/{id}/messages
                                         (scope Chat.ReadWrite)
"""
import argparse
import json
import shutil
import subprocess
import sys

# The unified mgc scope set for the whole engine — calendar + email + Teams +
# attendee/recipient lookup. One `mgc login` with these grants every Graph
# feature, so a single re-auth fixes any "auth" failure rather than a per-feature
# subset. doctor.py / onboarding present this; the per-feature scripts reference
# it so their error messages stay consistent.
MGC_SCOPES = "Calendars.ReadWrite Mail.Send Chat.ReadWrite User.Read.All"

_LOGIN_HINT = f'mgc login --scopes "{MGC_SCOPES}"'
_GRAPH_USER = "https://graph.microsoft.com/v1.0/users('{upn}')"


# ── Pure payload builders ────────────────────────────────────────────────────

def build_email_payload(to, subject, body, html=False):
    """Graph sendMail payload. `to` is a list of email addresses."""
    return {
        "message": {
            "subject": subject or "",
            "body": {"contentType": "HTML" if html else "Text", "content": body or ""},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        },
        "saveToSentItems": True,
    }


def build_chat_create_payload(me_upn, recipient_upns):
    """Graph chat-create payload. oneOnOne when there's a single recipient (Graph
    de-dupes to the existing 1:1 chat), else a group chat. Every member is an
    aadUserConversationMember with the owner role, bound by UPN."""
    members = [me_upn] + list(recipient_upns)
    return {
        "chatType": "oneOnOne" if len(members) == 2 else "group",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": _GRAPH_USER.format(upn=upn),
            }
            for upn in members
        ],
    }


def build_chat_message_payload(body, html=False):
    """Graph chatMessage payload (note: chat bodies use lowercase contentType)."""
    return {"body": {"contentType": "html" if html else "text", "content": body or ""}}


# ── Impure: the mgc runner ───────────────────────────────────────────────────

def _run_mgc(args, dry_run=False):
    """Run `mgc <args>` and return parsed JSON (or {} on an empty success body).

    Mirrors create_calendar_event.create_event: checks mgc presence, 30s timeout,
    detects auth failures and surfaces the unified-scope login hint. Raises
    RuntimeError on any failure.
    """
    if dry_run:
        return {"dry_run": True, "args": args}
    if not shutil.which("mgc"):
        raise RuntimeError(
            "mgc (Microsoft Graph CLI) not found.\n"
            "Install: download from https://aka.ms/get/graphcli/latest/ and add to PATH\n"
            f"Auth:    {_LOGIN_HINT}"
        )
    try:
        result = subprocess.run(
            ["mgc", *args], capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("mgc command timed out after 30 seconds")
    except FileNotFoundError:
        raise RuntimeError("mgc command not found in PATH")

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        low = stderr.lower()
        if "auth" in low or "token" in low or "login" in low or "forbidden" in low:
            raise RuntimeError(f"Authentication error. Run: {_LOGIN_HINT}\nDetails: {stderr}")
        raise RuntimeError(f"mgc failed (exit {result.returncode}): {stderr}")

    out = (result.stdout or "").strip()
    if not out:
        return {}  # sendMail returns 204 No Content on success
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"raw_output": out}


# ── Send paths ───────────────────────────────────────────────────────────────

def send_email(to, subject, body, html=False, dry_run=False):
    """Send an email via Graph sendMail. Returns a dict (success marker / dry-run)."""
    payload = build_email_payload(to, subject, body, html=html)
    if dry_run:
        return {"dry_run": True, "channel": "email", "payload": payload}
    # sendMail lives under the users resource and REQUIRES --user-id ("me" =
    # the signed-in user); the body is the sendMail request payload.
    _run_mgc(["users", "send-mail", "post", "--user-id", "me", "--body", json.dumps(payload)])
    # sendMail returns 204 No Content — there is no message id to return.
    return {"status": "sent", "channel": "email", "to": list(to)}


def send_teams(me_upn, recipient_upns, body, html=False, dry_run=False):
    """Create (or reuse) the chat and post the message. Returns the message id."""
    chat_payload = build_chat_create_payload(me_upn, recipient_upns)
    msg_payload = build_chat_message_payload(body, html=html)
    if dry_run:
        return {"dry_run": True, "channel": "teams",
                "chat": chat_payload, "message": msg_payload}
    chat = _run_mgc(["chats", "create", "--body", json.dumps(chat_payload)])
    chat_id = chat.get("id")
    if not chat_id:
        raise RuntimeError(f"Could not resolve a chat id from mgc response: {chat!r}")
    # The chat id is a REQUIRED option (--chat-id), not a path segment.
    msg = _run_mgc(["chats", "messages", "create", "--chat-id", chat_id,
                    "--body", json.dumps(msg_payload)])
    return {"status": "sent", "channel": "teams",
            "chat_id": chat_id, "message_id": msg.get("id")}


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Send email/Teams via mgc (Graph).")
    ap.add_argument("--channel", required=True, choices=["email", "teams"])
    ap.add_argument("--to", required=True, help="comma-separated recipients (emails/UPNs)")
    ap.add_argument("--body", required=True)
    ap.add_argument("--subject", default="")
    ap.add_argument("--me", default="", help="signed-in UPN (teams only)")
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    recipients = [r.strip() for r in a.to.split(",") if r.strip()]
    if a.channel == "email":
        out = send_email(recipients, a.subject, a.body, html=a.html, dry_run=a.dry_run)
    else:
        out = send_teams(a.me, recipients, a.body, html=a.html, dry_run=a.dry_run)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
