# Granola transcript fetch redesign — design

**Date:** 2026-06-22
**Status:** Approved (brainstorm)
**Branch:** `fix/granola-sync-ledger` (continues from the `_prompt_ids` crash fix)
**Surface:** platform / backend — `scripts/granola_sync.py` fetch seam, plus a dependency add and a data cleanup.

## Problem

`granola_sync.py` runs hourly (LaunchAgent) to pull Granola transcripts and create tasks. Three problems compounded:

1. **(Fixed)** `_prompt_ids` crashed on the legacy string-valued ledger, killing every run before any fetch. Resolved and committed earlier on this branch.
2. **The fetch returns placeholders, not transcripts.** `_fetch_new_meetings` asks one headless `claude -p` to return up to 20 full transcripts as a single JSON blob. Under that volume the model substitutes one-line summaries (`[Full transcript available - ...]`). Every fetched file is a ~200-byte stub, so task extraction has no content and (correctly) creates zero tasks.
3. **Classification is skipped.** The `openai` package is not installed, so `otter_classify` is bypassed — meetings land as raw `.txt` in `datasets/meetings/unknown/` with no frontmatter or domain filing.

Proven during diagnosis: the Granola MCP `get_meeting_transcript` returns **full verbatim transcripts reliably** when called for one meeting. The failure is purely the batch-many-into-one-response approach.

A direct-local-cache alternative was probed and rejected: Granola encrypts at rest (`granola.db` is non-SQLite/encrypted; the plaintext cache has empty `transcripts`; keys live behind `storage.dek` + Keychain). Reading it would mean reverse-engineering the app's encryption — fragile and out of scope.

## Goals

- Fetch **real verbatim transcripts** reliably, so task extraction has content to work from.
- Keep the change contained to the `_fetch_new_meetings` seam — the downstream (`run_downstream` -> classify -> task-extract) is unchanged.
- Restore classification (install `openai`).
- Clean up the 15 stub files + ledger entries so real transcripts re-fetch.
- Guard against silent re-pollution if the model ever summarizes again.

## Non-goals

- Decrypting / reading Granola's local store (rejected — encrypted).
- Changing the downstream pipeline, the meeting schema, or task extraction.
- Changing the LaunchAgent schedule or the provider gate.

## Approach (selected: per-meeting `claude -p` fetch)

`granola_sync` is a standalone script run by a LaunchAgent, so it reaches the MCP only via `claude -p`. Split the one fat call into two phases:

### Components

- **`_list_new_meetings(state_or_ids, root=None) -> list[dict]`** — one `claude -p` calling `list_meetings(time_range='last_30_days')`, returning metadata-only dicts `{id, title, created_at, attendees}` (NO transcript). Small response -> no summarization. Filters out already-seen ids (full `seen` set is authoritative) and caps at `MAX_NEW_PER_RUN`. A mockable seam (like the current `_fetch_new_meetings`).
- **`_fetch_one_transcript(meeting_id, root=None) -> str | None`** — one `claude -p` calling `get_meeting_transcript(meeting_id)`, returning that single verbatim transcript string. One transcript per response = reliable. Returns `None` on failure/empty/placeholder. A mockable seam.
- **`_looks_like_placeholder(text) -> bool`** — anti-regression guard. Returns True for content that is empty, below a minimum length threshold, or matches the known summary-stub shape (e.g. starts with `[Full transcript available`). Used to reject bad transcripts.
- **`_fetch_new_meetings(state_or_ids, root=None) -> list[dict]`** — rewritten orchestrator: call `_list_new_meetings`, then for each new meeting call `_fetch_one_transcript`; if the transcript is missing or `_looks_like_placeholder`, **skip the meeting (do NOT include it)** so it is not marked seen and retries next run. Assemble and return the same `{id,title,created_at,attendees,transcript}` dicts main() already consumes — so main() and downstream are untouched.

### Fetch prompts

- List prompt: "Use the Granola MCP. Call list_meetings(time_range='last_30_days'). Return STRICT JSON: an array of {id,title,created_at,attendees} for ALL meetings, and NOTHING else." (No transcript field requested -> small, reliable.)
- Transcript prompt: "Use the Granola MCP. Call get_meeting_transcript(meeting_id='<id>'). Return STRICT JSON: {\"transcript\": \"<the full verbatim transcript text>\"} and NOTHING else. Do NOT summarize or abbreviate. If unavailable, return {\"transcript\": null}." ASCII-safe wording.

### Dependency + cleanup

- Add `openai` to the project's Python dependencies (requirements file) and confirm it imports — restores `otter_classify` (local Ollama client + keyword fallback; no cloud/cost).
- Purge the 15 stub `.txt` files written to `datasets/meetings/unknown/` during the broken run, and remove their 15 entries from `profile/transcript/granola_downloaded.json`, so the next sync re-fetches them as real transcripts. (These are contentless failed-fetch stubs created in this session, not durable artifacts.)

## Testing

- **Unit (pytest, mocking the two `claude -p` seams):**
  - `_list_new_meetings` filters seen ids and caps at `MAX_NEW_PER_RUN`.
  - `_fetch_one_transcript` returns the transcript on good output; `None` on malformed/empty.
  - `_looks_like_placeholder` flags empty, too-short, and `[Full transcript available` stubs; passes a real multi-line transcript.
  - `_fetch_new_meetings` orchestration: assembles full dicts for good meetings; **skips** meetings whose transcript is missing/placeholder (not returned -> not marked seen).
  - Existing `test_granola_sync.py` cases (provider gate, dedup, basename, downstream isolation, `_prompt_ids`) stay green.
- **Live verification:** purge stubs, run `python3 scripts/granola_sync.py`, confirm: real KB-sized transcripts written, classified into `meetings/<domain>/<YYYY-MM>/` `.md` with frontmatter, and tasks actually created in `datasets/tasks/`.

## Invariants

- #2 gates: new pytest cases; `card_schema.py` / `portability_gate.py` unaffected (no card/OS-seam change; `claude -p` invocation unchanged in mechanism).
- #1/#4 de-personalization: transcripts are operator data; no identity baked into code.
- #8 portability: keeps the existing `subprocess` + `transcript_post._hook_env()` pattern; no new OS-specific code.
- ASCII-safe prompts and runtime strings (hyphen not em-dash).

## Files touched

- `scripts/granola_sync.py` — rewrite `_fetch_new_meetings`; add `_list_new_meetings`, `_fetch_one_transcript`, `_looks_like_placeholder`; split `_fetch_prompt` into list/transcript prompts.
- `tests/test_granola_sync.py` — new unit tests; update any test that mocked the old single-call `_fetch_new_meetings` shape.
- requirements file — add `openai`.
- `datasets/meetings/unknown/` (remove 15 stubs) + `profile/transcript/granola_downloaded.json` (remove 15 entries) — one-time cleanup (done as a verification/build step, not code).
