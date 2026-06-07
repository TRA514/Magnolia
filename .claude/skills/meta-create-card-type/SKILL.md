---
name: meta-create-card-type
description: Use when the operator asks to add, build, or scaffold a new card type / card kind for the board - composes a new entry in the declarative card registry from existing pieces, validates the design-system gate, and emits a Keep/Undo receipt
---

# Create Card Type

Add a new card type by composing one entry in the declarative card registry
(`ui/task-board/cardtypes/registry.json`). **Read `meta-factory-core` first** — this
skill is its card-type specialization. Reuses `meta-create-skill`'s RED-GREEN-REFACTOR
spine.

The board renders any registered card type generically (`js/card-registry.js` walks
the slot order and renders from existing slot builders / signal predicates / action
handlers / body renderers). So a card type composed from **existing** pieces needs
**zero new render code** — just a registry entry that the design-system gate accepts.

## When to Use

- The operator wants a new card kind that reuses existing signals/actions/bodies
  (e.g. "a card that just shows a title with a Keep/Undo", "a reminder card with the
  due chip and Mark done").
- **Not** for a new worker (`meta-create-worker`) or external integration
  (`meta-create-adapter`).

## Composition-only (the hard boundary)

You may ONLY compose from pieces that already exist:

- **signals**: `due`, `overdue`, `waiting_on`, `waiting_due`, `schedule`, `message`,
  `jira_draft`, `cron` — or `"auto"` (all matching, in canonical order).
- **actions**: `mark_done`, `open_output`, `publish_jira`, `accept`, `reject`,
  `keep`, `undo`, `graduate`.
- **body**: `null`, or one of `diff`, `preview`, `agreement`.

A **new** signal predicate, action handler, body renderer, or head-kind label is
JavaScript work (in `js/card-registry.js`) and is **out of scope** for the factory.
If the operator needs one, say so plainly and hand it to engineering — do not invent
a registry entry that references a piece that doesn't exist (the gate will reject it
anyway).

## The Gate (must be green before commit)

1. `python3 scripts/factory_lib.py validate-card-type <name>` → `ok`.
2. `python3 scripts/card_schema.py` → `registry.json OK` (token-only design-system
   gate; rejects unknown signals/actions/renderers and any hardcoded color/size).

## Workflow

1. **Capture the spec.** Ask the card type's `<name>` and which existing signals,
   actions, and body renderer (or `null`) it composes. (Card types carry no per-team
   nuance, so there is usually nothing to capture into the profile here.)
2. **Compose** the entry. Add one key to the `cardTypes` object in
   `ui/task-board/cardtypes/registry.json`:

       "<name>": { "signals": [ ... ] | "auto", "actions": [ ... ], "body": null | "diff" | "preview" | "agreement" }

   Keep the JSON valid and the existing entries untouched.
3. **Gate** — run both checks above. Fix until green.
4. **Commit + receipt** — `python3 scripts/factory_lib.py commit-and-receipt --summary "a <name> card type" --kind card-type ui/task-board/cardtypes/registry.json`
5. **Hand back** — tell the operator: *"Built you a `<name>` card type → reload the
   board to see it; there's a receipt card. Keep / Undo."* Never mention git. Note
   that a brand-new card type renders with the default head (no custom kind label)
   unless engineering adds one in JS.

## Iron Laws

1. **Compose from existing pieces only** — never reference a signal/action/renderer
   that isn't already in the registry / JS.
2. **Gate green before commit** (`validate-card-type` + `card_schema.py`).
3. **Stage only `registry.json`** via `factory_lib`.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Inventing a new signal/action/body renderer in the entry | Compose from existing pieces; new ones are JS work, hand to engineering |
| Hardcoding a color/radius in a signal/action spec | The registry is token-only; the gate rejects raw colors/sizes |
| Editing `js/card-registry.js` | Out of scope — registry-composition-only this PR |
| Telling the operator about the commit | Speak in Keep / Undo |

## Related Skills

- **meta-factory-core**: the shared lifecycle + receipt mechanism (read first).
- **meta-create-skill**: the TDD spine.
