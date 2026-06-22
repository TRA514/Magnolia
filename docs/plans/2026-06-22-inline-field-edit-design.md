# Inline field editing for task cards — design

**Date:** 2026-06-22
**Status:** Approved (brainstorm)
**Surface:** Platform UI (board front end) + task server backend. No card-registry or schema-gate changes.

## Problem

Today only the task **description** is editable, via an edit/save toggle in the task detail modal. Every other field (title, priority, status, due, domain, project, tags, and the "waiting on" third party) is display-only. The operator wants to edit any task field directly — both on the card face while scanning the board, and in the detail modal.

The primary workflow: tasks parked in the **waiting** queue as reminders to follow up with a third party. The operator needs to edit *who they are waiting on* directly. This is the `waiting_on` field — a real, stored, free-text field — not the queue/assignee model. (The board is effectively single-operator today; there is no team to route tasks to, so queue/assignee routing is out of scope — see Non-goals.)

## Goals

- Edit task fields inline on **two surfaces**: the card face on the board (a focused high-value subset) and the modal Details section (the full set).
- Support every field **type**: free text, enum, date, and tag list.
- One reusable edit mechanism, not a copy of the description toggle per field.
- A single server-side gatekeeper for which fields may be written and what values are valid.
- No regression to existing behavior (description editing, mark-done side effects).

## Non-goals (v1)

- **Queue / assignee editing.** Changing `queue` physically moves the task's file between queue directories and re-derives `assignee`; it is a structural "move" operation, not a field edit. Excluded from v1 (single-operator board; not needed). Could be a fast-follow "Move to queue" action.
- Bulk / multi-task editing.
- New card types, signals, actions, or body renderers (no card-registry changes).

## Approach (selected: generalized inline-field editor)

A declarative field config drives a single edit module shared by both surfaces, backed by one generic update endpoint. Chosen over per-field duplication (doesn't scale to "any field") and a config-less helper (scatters type logic at call sites).

### Editable field config

| Field | Type | Surface | Allowed values / notes |
|---|---|---|---|
| `title` | text | card + modal | length-bounded (200, matching existing cap) |
| `priority` | enum | card + modal | critical / high / medium / low |
| `status` | enum | card + modal | open / in-progress / blocked — done & cancelled route through existing handlers (see below) |
| `due` | date | card + modal | ISO `YYYY-MM-DD` |
| `waiting_on` | text | card *(waiting queue only)* + modal | the follow-up third party |
| `waiting_expected` | date | card *(waiting queue only)* + modal | when a reply is expected |
| `domain` | enum | modal | the 8 domain values in `task_lib` |
| `project` | text | modal | free text |
| `tags` | list | modal | chip add / remove |

## Components

### Frontend — `ui/task-board/js/field-edit.js` (new)

- Holds the field config above (types + which surface).
- Single entry point `editField(taskId, fieldName, currentValue, anchorEl)` that swaps the displayed value for a type-appropriate control in place:
  - **text** → inline `<input>` (or `<textarea>` if long); commit on Enter or blur-with-change; Esc cancels.
  - **enum** → `<select>`; commit on change.
  - **date** → `<input type="date">`; commit on change / blur.
  - **tags** → chip row with per-chip remove control and an add input.
- On commit, `POST`s to the generic endpoint, then refreshes the modal (preserving chat) and the board — reusing the existing post-save refresh pattern from `saveDescription()`.
- All new styling references **theme tokens only** (invariant #3) and is ASCII-safe.

### Frontend wiring

- `ui/task-board/js/tasks.js` — modal Details rows (currently read-only spans) become click-to-edit, calling `editField`.
- `ui/task-board/js/card-registry.js` — card-face fields (title, priority, status, due; plus `waiting_on` / `waiting_expected` for waiting-queue cards) become click-to-edit. Editable regions call `stopPropagation()` so an edit click does **not** also open the modal. Only an explicit commit writes; clicking away or Esc cancels with no write, so scanning past a card never mutates it.

### Backend — `scripts/task_server.py` + `scripts/task_lib.py`

- New route `POST /api/tasks/{id}/field` → `handle_update_field(handler, task_id)`:
  1. Read `{field, value}` from the body.
  2. Reject if `field` not in a server-side **`EDITABLE_FIELDS` allowlist** (defined in `task_lib.py`). The allowlist excludes `id`, `created`, `updated`, `creator`, `agent_*`, `judge_*`, `card_type`, `queue`, derived `assignee`, and all other system-managed fields.
  3. Validate `value` by type: enums checked against the canonical lists already in `task_lib` (`PRIORITIES`, statuses, domains); free text length-bounded; dates parsed as `YYYY-MM-DD`; tags coerced to a list of strings.
  4. Persist via the existing `task_lib.update_task(task_id, changes={field: value}, actor="human")`, which already appends an activity-log entry (audit trail preserved).
  5. Respond `{"status": "ok"}`; `404` unknown task, `400` bad field/value.
- The description keeps its existing dedicated endpoint (it is a markdown body section, not frontmatter).

## The status edge case

Setting status to **done** or **cancelled** has side effects today (the mark-done flow logs completion and can move the task). The inline status editor therefore offers only `open / in-progress / blocked` for direct generic writes; selecting **done** routes through the **existing done action/handler**, not the generic field write. No regression to current mark-done behavior.

## Validation & security

The `EDITABLE_FIELDS` allowlist is the single gatekeeper — the generic endpoint can only write opted-in fields, so a hand-crafted request cannot touch `id`, `queue`, `judge_*`, etc. Enum values are validated server-side against `task_lib`'s constants (the server is the source of truth; the frontend config mirrors it). Free-text fields are length-bounded.

## Testing

- **Backend (TDD, Python):**
  - allowlist rejects protected fields (`id`, `queue`, `created`, `agent_status`, …) with `400`;
  - enum validation rejects bad `priority` / `status` / `domain`;
  - valid edit persists the change and appends an activity-log entry;
  - unknown task → `404`; missing/empty field or value → `400`;
  - status → `done` continues to route through the existing done handler (side effects intact).
- **Frontend:** verified via live e2e on the dev board (`localhost:8743`): click → edit → save for each field type on both the card face and the modal; confirm scanning past / Esc / click-away cancels with no write.

## Invariant check

- #1 / #4 de-personalization: `waiting_on` is operator data, not engine identity; no person/team identity is baked into code. Passes `test_engine_no_jay.py`.
- #2 gates: backend changes covered by new pytest cases; `card_schema.py` unaffected (no registry change); `portability_gate.py` unaffected (no OS/shell code).
- #3 token-only: all new CSS references theme tokens.
- #7 dev/prod: e2e runs on the dev board only (`:8743`).
- #8 portability: no `platform_lib` bypass; new code is pure HTTP/JS.

## Files touched

- `scripts/task_server.py` — new route + `handle_update_field`.
- `scripts/task_lib.py` — `EDITABLE_FIELDS` allowlist + value validation helper (reuses `update_task`).
- `ui/task-board/js/field-edit.js` — new edit module + field config.
- `ui/task-board/js/tasks.js` — wire modal Details fields.
- `ui/task-board/js/card-registry.js` — wire card-face fields with `stopPropagation`.
- Theme-token CSS for the inline editors (shared stylesheet, not per-Mood).
