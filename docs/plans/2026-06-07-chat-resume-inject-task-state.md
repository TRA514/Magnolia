# Inject task state into resumed chat prompts (kill the metadata tool-call)

**Date:** 2026-06-07
**Branch:** `feat/chat-resume-inject-task-state` (off `main`)
**Ship:** PR for Jay to merge.

## Problem

The chat panel's `build_context_prompt` injects a ~9-field task-context block, but
ONLY on the first turn of a brand-new session. On the **resume path** —
every follow-up turn, and the first chat turn that resumes the *worker's* `claude -p`
session after a background run — `run_turn` sends the bare user message. So when the
model needs task state in a resumed session it burns a tool call (`./scripts/task.sh
show` / `Read`) to re-fetch metadata we already hold in `fm`. That state can also be
**stale** in session history (status/priority/queue/due change between turns).

## Design (approved Option A)

Re-inject a compact, **current** task-state block on **every** resume-path turn.
Cheap (~8 lines/turn), keeps the model on fresh state inline, eliminates the tool call.

1. **Extract** `_task_context_block(task, *, include_description=True, heading="## Task context")`
   — pure, returns the bulleted field lines. `build_context_prompt` refactors to call it
   with defaults, so its output is byte-for-byte unchanged (existing tests stay green).
2. **Add** `build_resume_prompt(task, user_message)` — prepends a
   `## Current task state` block (volatile metadata only, `include_description=False`
   — the body already lives in session history from turn 1) + a one-line "these are
   current values, trust them over earlier context" note + the `## {name}'s message`
   section. Does NOT replay the persona preamble (the session already has it). Identity
   via `profile_lib` only (invariant #1).
3. **Wire** `run_turn`'s resume branch: `sent_message = build_resume_prompt(fm, message)`
   (was the bare `message`). The persisted user transcript event is unchanged — it still
   stores the operator's ORIGINAL `message`, not the wrapper.

## Tests (RED first)

- `_task_context_block`: required fields + optional gating; description included/omitted.
- `build_resume_prompt`: contains `## Current task state`, the status value, and the
  message; omits the persona preamble ("task execution assistant"); de-personalized.
- `run_turn` resume integration: the argv message (`cmd[1]`) carries the injected state
  block AND the original message; the persisted user event still stores the bare message.
- Existing `build_context_prompt` / resume tests stay green (refactor is behavior-preserving).

## Gates

`python3 -m pytest` · `python3 scripts/card_schema.py` · `python3 -m pytest tests/test_engine_no_jay.py`.
No card/theme or external-write surface touched — Tier-1, no new Tier-2 confirm.
