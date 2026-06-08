# Granola Transcript Adapter — Design

**Date:** 2026-06-08
**Status:** Approved (brainstorm complete; proceeding to implementation plan)
**Author:** Jay Jenkins

## Goal

Add Granola as a transcript provider that mirrors Otter: pull meeting transcripts
on an hourly schedule, dedup so no transcript is downloaded twice, and run the
**identical** downstream Otter uses (domain classification → YAML front matter →
task extraction → qmd index). Selectable from the Engine tab; only runs when
Granola is the active transcript provider.

## Transport decision

The hourly job fetches via **headless `claude -p` + the Granola MCP** (operator's
choice). Rationale and rejected alternatives:

- The local Granola cache (`cache-v4.json`) was evaluated and **rejected for
  content**: in current Granola (v7.41 / cache-v4) the `transcripts` table is
  empty and document objects carry only `external_transcription_id` /
  `transcript_deleted_at` pointers — no transcript text, and notes are sparse
  (149/795 docs). The cache also only refreshes while the desktop app runs. It is
  therefore unreliable for reproducing Otter's full transcript output.
- The Granola MCP (`https://mcp.granola.ai/mcp`) is the authoritative, server-backed
  source. It requires a one-time `granola.ai/mcp-signup` per account, and
  `get_meeting_transcript` is **paid-plan only** — both verified at e2e.

### MCP tool surface (live schemas)

- `list_meetings(time_range: this_week|last_week|last_30_days)` → meeting UUID + title + date + attendees
- `get_meetings(meeting_ids: [UUID] max 10)` → notes / enhanced notes / summary
- `get_meeting_transcript(meeting_id: UUID)` → raw transcript (**paid plan only**)
- `query_granola_meetings`, `list_meeting_folders`, `get_account_info` (unused by sync)

Transcript segment shape (from the underlying API): `{source: microphone|system,
text, start_timestamp, end_timestamp}` — Granola labels mic-vs-system audio, not
named speakers.

## Architecture (Option A — thin `claude -p` fetch boundary, fat deterministic Python)

Mirrors the Otter wiring exactly.

- **`scripts/granola_sync.py`** (new) — structured like `otter_sync.py`. Profile-driven
  paths (`transcript_state_dir()`, `transcript_config()["target"]`). Owns all stateful
  work: state load/save, the `claude -p` invocation, JSON validation, file write,
  classify, downstream hooks. `main()` is the entrypoint.
- **`scripts/adapters/transcript/granola.py`** — replaces the stub; `sync(root)`
  delegates to `transcript_sync._run_granola(root)` and returns `{status, provider}`,
  exactly like `otter.py`.
- **`scripts/transcript_sync.py`** — add `_run_granola(root)` (lazy-imports
  `granola_sync`, calls `.main()`). Dispatch already routes `provider="granola"` → the
  adapter via the loader; no loader change.

### The `claude -p` fetch boundary

One Python function `_fetch_new_meetings(seen_ids) -> list[dict]` shells out:

```
claude -p --model <config: claude-haiku-4-5> --output-format json \
  --allowedTools mcp__claude_ai_Granola__list_meetings,mcp__claude_ai_Granola__get_meeting_transcript \
  "<prompt>"
```

Prompt: *list_meetings(last_30_days); for each meeting whose id is NOT in the
seen-list (passed via stdin / temp file), call get_meeting_transcript; return STRICT
JSON `[{id,title,created_at,attendees,transcript}]`. Cap N new per run.* Python
validates the JSON (schema check + one retry on malformed). **This is the single
mockable seam for tests.**

Model defaults to `claude-haiku-4-5` (config-driven; bump if Haiku struggles with
MCP tool-calling).

## Dedup + data flow

- State: `<transcript_state_dir>/granola_downloaded.json`, keyed by meeting **UUID** →
  `{title, downloaded_at, folder, domain, final_path}`. Separate file from Otter's
  `downloaded.json` (distinct ID namespaces), same dir.
- A UUID already in state is skipped — identical to Otter's `speech_id` check.
- Transcripts written to the **same** meetings target dir (one corpus, one qmd index),
  `YYYY-MM/` subdir, same dated-basename scheme as Otter.

## Downstream — shared with Otter (not copied)

Extract Otter's post-write steps — `otter_classify.process_file` + the
`task-extract-meetings.sh` and qmd `Popen` hooks — into **one shared helper** that both
`otter_sync` and `granola_sync` call. The Granola UUID is passed as the `speech_id` key
into `process_file`. Light refactor of `otter_sync`, kept green by its existing tests.
This *guarantees* parity rather than hoping for it.

## Error handling (mirrors Otter's structured-error contract)

- `claude -p` failure / malformed JSON after retry → log, return `{status:error,
  provider:granola}`, **no state mutation** → retried next hour.
- Per-meeting failure (incl. empty transcript from the paid-plan restriction, or
  `Unauthorized` until mcp-signup is done) → log, skip, **don't mark seen** →
  auto-backfills once plan/account is live.
- **Tier:** sync only **reads** Granola → **Tier-1**, no publish confirm (transcript
  adapters have no `publish()`).

## Frontend + lifecycle (Engine tab)

Single active transcript `provider` (one feed at a time: Otter **or** Granola),
chosen at onboarding, switchable later via Claude Code / future UI. **No Off button**
(turning the feed off defeats the app's purpose; switching is an edge case).

Already wired (no work): Granola listed under Transcripts in `_INTEGRATION_OPTIONS`;
generic `build_profile` payload emits it (status `available` → "Connect" → `fix granola`);
`POST /api/profile/integrations/transcripts {active}` switches the provider; onboarding
already asks "Otter or Granola?". **`profile.js` needs no changes** — it renders whatever
`/api/profile` returns.

To build:

1. **Provider-gated hourly job** — the Granola LaunchAgent runs a provider-aware
   entrypoint that **exits immediately unless `transcript.provider == "granola"`**. The
   UI provider selection *is* the on/off switch. (Otter's existing agent untouched.)
2. **Granola-aware `doctor.probe_transcript`** — branch by provider. Otter keeps the
   `session.json` check; Granola reflects MCP connectivity (stamped remote-connector
   status + a successful-sync marker), else `needs_reauth` with remedy: *"connect Granola
   via `/mcp` and finish granola.ai/mcp-signup."* Drives the correct status dot +
   Connect/Re-authorize on the tab.
3. **`fix granola` + onboarding copy** — conversational fix path (select provider →
   connect MCP → mcp-signup → verify via `get_account_info`); update onboarding note so
   both Otter and Granola read as fully wired.
4. **Recurring job artifact** — a **de-personalized** LaunchAgent plist template
   (profile-resolved paths, no hardcoded user — denylist-clean), committed to the repo;
   the actual `launchctl` install on the operator's machine is a live, non-committed step.
   Cadence mirrors Otter (weekday business hours, hourly).

## Testing & gates

- Unit tests mock the `_fetch_new_meetings` seam → assert dedup skips seen IDs, writes
  files, calls classify (mocked), fires hooks (mocked). Mirror
  `tests/test_transcript_sync.py`'s `_run_otter` monkeypatch with a `_run_granola`
  equivalent. Add a `probe_transcript` granola-branch test.
- Green gates before every code commit: `python3 -m pytest` · `python3 scripts/card_schema.py`
  (→ `registry.json OK`) · `python3 -m pytest tests/test_engine_no_jay.py` (both new files
  denylist-clean) · `python3 scripts/factory_lib.py validate-adapter transcript granola` → `ok`.

## Risks (confirmed only at e2e once MCP account is live)

- **Headless `claude -p` + claude.ai-MCP survival** — claude.ai connectors are built for
  interactive sessions; the OAuth token may not work in a non-interactive cron context.
- **Paid-plan transcript gate** — `get_meeting_transcript` requires Business/Enterprise.

Both degrade gracefully (log + retry, no state mutation) so nothing breaks; the feed just
won't pull until resolved.
