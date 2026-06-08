# Plan — Real Teams + Outlook-email sending from the send-message card (via mgc)

**Date:** 2026-06-08
**Status:** Actionable
**Branch:** `feat/message-send-mgc` (off main)

## Goal
Make the existing **"Send message"** button on `send-message` task cards actually
transmit — Outlook **email** and **Teams** chat — using the `mgc` Microsoft Graph
CLI, wired through the engine's **Tier-2 confirm** (invariant #5). Today the
button only records `message_sent_at` and archives (`handle_send_message`,
`task_server.py:793`); it transmits nothing. Both channels ship together.

## Decisions (locked)
- **Transport:** `mgc` (Graph CLI) — not the M365 MCP, which is read-only and
  unreachable from the board server. Mirrors the working calendar path
  (`create_calendar_event.py`).
- **Confirm cadence:** **one-time Tier-2** integration confirm (first send only),
  exactly like calendar/Jira. No per-send dialog — the visible draft preview +
  deliberate button click is the per-send check.
- **Scope:** email **and** Teams in one shippable unit.
- **Architecture:** a proper `messaging` adapter family through `adapters.publish()`
  — do NOT bypass the Tier-2 gate the way the calendar path does.

## Current-state anchors (verified)
- Card fields: `message_channel` ("Teams"|"Email"), `message_to`, `message_body`,
  `message_subject` (email only). Rendered at `tasks.js:206-223`.
- Button: `tasks.js:344` → `sendMessage()` `tasks.js:730` → `POST /api/tasks/{id}/send-message`.
- Handler: `handle_send_message` `task_server.py:793`; route `task_server.py:2191`.
- Adapter contract: `scripts/adapters/__init__.py` — `get()`, `publish(family, draft)`,
  `NeedsConfirmation`, `_is_confirmed()`. Provider implements `is_configured(root)`
  + `publish(draft, root) -> (id, url)`. Exemplar: `adapters/project_management/jira.py`.
- Tier-2 confirm card: `_emit_confirm_card()` `task_server.py:1384`, `handle_confirm`
  re-drives `confirm_source_task`; card kind `confirm` in `cardtypes/registry.json`.
- Confirm flag: `profile_lib.set_integration_confirmed(category, bool, provider=...)`.
- mgc-subprocess precedent: `create_calendar_event.py` (payload build → `mgc ... --body <json>`
  → parse → return id; dry-run; auth-error detection).
- Recipient resolution: `_load_email_cache()` `task_server.py:1490`
  (`datasets/people/email_cache.json`, name→email).

## mgc command reference (verified, mgc 1.9.0)
- **Email:** `mgc users send-mail post --body '<json>'`
  payload: `{"message":{"subject":S,"body":{"contentType":"Text|HTML","content":B},
  "toRecipients":[{"emailAddress":{"address":A}}]},"saveToSentItems":true}`
  scope: `Mail.Send`.
- **Teams (1:1):** `mgc chats create --body '<json>'` (chatType `oneOnOne`; Graph
  de-dupes to the existing chat) → parse `id` → `mgc chats {id} messages create
  --body '{"body":{"contentType":"text|html","content":B}}'`.
  Chat-create members need the signed-in user's UPN (`mgc me get` →
  `userPrincipalName`, cached) and the recipient's UPN/email. Multiple recipients
  → chatType `group`. scope: `Chat.ReadWrite`.

## The draft contract (what handle_send_message passes to publish)
```
{
  "channel": "email" | "teams",
  "to":         ["resolved@addr", ...],   # via email_cache; falls back to raw if no @
  "to_display": "<original message_to>",
  "subject":    "<message_subject>",       # email only
  "body":       "<message_body>",
  "task_id":    "TASK-XXXX",
}
```
`messaging.m365.publish(draft)` returns `(message_id, None)`.

## Task breakdown (TDD; 3 gates green before every commit — pytest · card_schema.py · test_engine_no_jay.py)

### Task 1 — `scripts/send_message_graph.py` (the mgc seam)
Mirror `create_calendar_event.py`. Pure payload builders + impure mgc runner.
- `build_email_payload(to, subject, body, html=False) -> dict` (Graph sendMail shape).
- `build_chat_create_payload(me_upn, recipient_upns) -> dict` (oneOnOne/group).
- `build_chat_message_payload(body, html=False) -> dict`.
- `send_email(payload, dry_run=False)` → `mgc users send-mail post --body ...`
  (sendMail returns empty body on success → synthesize an id/“sent” marker).
- `send_teams(me_upn, recipient_upns, body, dry_run=False)` → create chat, parse
  `id`, post message, return message id.
- `_run_mgc(args, dry_run)` shared: `shutil.which` check, 30s timeout, auth-error
  detection (reuse calendar's stderr heuristic), JSON parse with raw fallback.
- CLI entrypoint + `--dry-run`.
- **Tests** (`tests/test_send_message_graph.py`): payload shapes (pure, exact JSON);
  dry-run returns payload without shelling; missing-mgc raises the actionable error
  (monkeypatch `shutil.which`→None). No real mgc.

### Task 2 — `messaging` adapter family
- `scripts/adapters/messaging/__init__.py`, `_contract.py` (Protocol: `is_configured`,
  `publish(draft, root) -> (id, url)`), `m365.py`.
- `m365.is_configured(root)` → `bool(shutil.which("mgc"))` (auth verified at send).
- `m365.publish(draft, root)` dispatches on `draft["channel"]` → `send_message_graph`
  (`send_email` / `send_teams`), resolving `me_upn` once (cached). Raises
  `NotConfigured` when mgc absent.
- **Tests** (`tests/test_messaging_adapter.py`): channel dispatch (monkeypatch
  send_message_graph), is_configured true/false, unknown channel raises.

### Task 3 — Tier-2 arm + integrations.yaml
- Add to `profile/integrations.yaml`:
  ```yaml
  messaging:
    provider: "none"   # m365 | none   (set m365 to enable; arms confirm)
    m365:
      confirmed: false
  ```
  (Ship as `none` so a fresh clone degrades gracefully; enabling = set `m365`.)
- **Tests** (`tests/test_messaging_tier2.py`): `adapters.publish("messaging", draft)`
  → `None` when provider none; `NeedsConfirmation` when m365 + `confirmed:false`;
  delegates when `confirmed:true` (mgc mocked).

### Task 4 — Rewire `handle_send_message` + `handle_confirm` re-drive
- `handle_send_message`: read channel/to/subject/body, resolve `to` via email_cache,
  build draft, `result = adapters.publish("messaging", draft)`.
  - `result is None` (provider none) → **legacy fallback**: record `message_sent_at`
    + archive (today's behavior; nothing breaks without mgc).
  - `NeedsConfirmation` → `_emit_confirm_card("messaging", task_id)`, return
    `{status:"needs_confirm", confirm_task: cid}` (no send, no archive).
  - success → stamp `message_sent_at` + `message_id`, archive, return ok.
  - mgc/auth `RuntimeError` → 502 with the actionable mgc-login message; do NOT archive.
- `handle_confirm`: ensure the `confirm_family == "messaging"` branch re-drives the
  send for `confirm_source_task` (set confirmed → re-run handle_send_message logic).
  Verify/extend the existing re-drive switch.
- **Tests** (`tests/test_send_message_route.py`, extend `test_chat_route` style):
  provider-none→record+archive; m365-unconfirmed→confirm card emitted, task NOT
  archived; confirmed+success (mgc mocked)→message_id stamped + archived;
  mgc failure→error, task survives. handle_confirm messaging re-drive sends + archives.

### Task 5 — Frontend send UX
- `sendMessage()` already POSTs; handle the new responses:
  - `needs_confirm` → toast "One-time confirm added to your queue — approve it to send"
    (+ optionally surface/scroll to the confirm card). Re-enable button.
  - success → existing "Message sent." toast + refresh.
  - 502/auth error → show the actionable error (mgc login) instead of a generic fail.
- No per-send dialog (decision: one-time Tier-2). Keep the existing preview bubble.
- **Verify** via headless-Chrome render of the states (no JS test harness; visual pass).

### Task 6 — Doctor + ONBOARDING scope capture (one canonical login)
The send scopes (`Mail.Send`, `Chat.ReadWrite`) must be granted at FIRST-TIME
setup, not discovered later. Today the `mgc login` scopes are scattered across
the calendar/scheduler scripts (each showing only its own scope) and absent from
onboarding entirely. Unify them so one login grants everything.
- **Canonical scope set** in ONE place (e.g. `MGC_SCOPES` const in `doctor.py`):
  `Calendars.ReadWrite Mail.Send Chat.ReadWrite User.Read.All`
  (Calendars = events; Mail.Send = email; Chat.ReadWrite = Teams; User.Read.All =
  attendee/recipient resolution the scheduler already needs).
- `scripts/doctor.py`: add `messaging: m365` to `_REMOTE_FROM_INTEGRATION`; the
  mgc-auth remedy presents the full `mgc login --scopes "<MGC_SCOPES>"`. Degrade
  gracefully (advisory; `required: false`).
- `.claude/skills/meta-onboard/SKILL.md`: in the M365 authorize step (line ~53/77),
  state the explicit `mgc login --scopes "<MGC_SCOPES>"` so first-time M365 setup
  grants Teams+Outlook SEND, not just calendar/read.
- `.claude/skills/workflow-doctor/SKILL.md`: note the mgc auth/scopes remedy.
- **Standardize the auth-error remedy** across `create_calendar_event.py`,
  `find_meeting_times.py`, and the new `send_message_graph.py` to the unified
  scope set, so a single re-login fixes every feature (not a per-script subset).
- **Tests:** assert the unified scope string contains Mail.Send + Chat.ReadWrite +
  Calendars.ReadWrite; doctor messaging seed appears when provider=m365.

### Task 7 — Gates + live e2e
- 3 gates green. Restart dev board (:8743) — it caches chat_runner/server.
- `send_message_graph.py --dry-run` for both channels (payload sanity).
- **Prereq (user runs):** `mgc login --scopes "Calendars.ReadWrite Mail.Send Chat.ReadWrite User.Read.All"` (the unified set from Task 6).
- Real send to **yourself** (email + a Teams self/test chat) from a dev send-message
  card: first send → confirm card → confirm → delivered; second send → straight
  through. Confirm archive + `message_id` recorded.

## Risks / edge cases
- **mgc scopes:** current login is Calendars-only; email/Teams fail until re-login
  with added scopes. Surfaced by doctor + the actionable send error.
- **Teams "me" UPN:** one `mgc me get` to resolve the signed-in UPN; cache it.
- **oneOnOne idempotency:** Graph returns the existing 1:1 chat on re-create, so we
  don't spawn duplicate chats. Verify in e2e.
- **Recipient not in email_cache:** if `message_to` has no `@` and isn't in cache,
  fail with a clear "couldn't resolve recipient" error rather than sending to a bad
  address.
- **HTML vs text:** default `Text` for email body, `text` for Teams; revisit if the
  drafter emits markdown/HTML.

## Out of scope (future)
- Teams **channel** posts (team-id/channel-id targeting) — this plan does person
  chats only.
- Per-send confirmation dialog (decided against).
- Slack / other providers (the family makes them drop-in later).
- Routing the calendar path back through `publish()` (separate cleanup).
