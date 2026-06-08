"""Microsoft 365 messaging adapter — Outlook email + Teams chat via mgc (Graph).

publish(draft) dispatches on draft["channel"]:
  - "email" -> Graph sendMail
  - "teams" -> create/reuse the chat + post the message

Both shell out through send_message_graph (the mgc seam). is_configured is just
"mgc present"; live auth is verified at send time by the mgc call itself
(send_message_graph surfaces the unified-scope login hint on an auth failure).
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import send_message_graph as graph  # noqa: E402
from adapters.messaging._contract import NotConfigured  # noqa: E402

# Cached signed-in UPN (needed to build the Teams chat member list). One resolve
# per process; messaging is low-volume so a module-level cache is plenty.
_ME_UPN = None


def is_configured(root=None) -> bool:
    return bool(shutil.which("mgc"))


def _resolve_me_upn():
    """The signed-in user's UPN, via `mgc me get` (cached)."""
    global _ME_UPN
    if _ME_UPN:
        return _ME_UPN
    # `users get` also requires --user-id ("me" = signed-in user).
    out = graph._run_mgc(["users", "get", "--user-id", "me", "--select", "userPrincipalName"]) or {}
    upn = out.get("userPrincipalName")
    if not upn:
        raise NotConfigured("could not resolve the signed-in user (mgc me get)")
    _ME_UPN = upn
    return upn


def publish(draft, root=None):
    """Send `draft` and return (message_id, url|None). Raises NotConfigured when
    mgc is unavailable or the channel is unknown; send_message_graph raises
    RuntimeError on an mgc/auth failure (caller surfaces the login hint)."""
    if not is_configured(root):
        raise NotConfigured("Microsoft Graph CLI (mgc) is not available")
    channel = (draft.get("channel") or "").lower()
    to = draft.get("to") or []
    body = draft.get("body") or ""
    if channel == "email":
        res = graph.send_email(to, draft.get("subject", ""), body)
        return (res.get("status", "sent"), None)
    if channel == "teams":
        me = _resolve_me_upn()
        res = graph.send_teams(me, to, body)
        return (res.get("message_id") or res.get("status", "sent"), None)
    raise NotConfigured(f"unknown messaging channel: {channel!r}")
