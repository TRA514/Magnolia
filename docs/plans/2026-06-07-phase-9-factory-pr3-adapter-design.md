# Magnolia — Phase 9 PR3: `meta-create-adapter` + Tier-2 publish gate (Design)

**Date:** 2026-06-07
**Status:** Design approved (brainstorm complete) — ready for implementation plan
**Builds on:** Phase 9 PR1 (`meta-factory-core` + `meta-create-worker`, #15) and PR2 (`meta-create-card-type`, #16), both merged to `main` (latest merge `7bb9b14`).
**Phase design:** `2026-06-07-phase-9-factory-design.md` §4 (Tier-2 confirm) + the Open Questions section — this doc resolves them.
**Master design:** `2026-06-05-pm-os-portability-design.md` §6 (the factory), capability tiers (anything writing to the outside world is Tier-2).

This is the **last slice of the last build-sequence phase.** After it merges, Phase 9 — and the whole build sequence — is complete.

---

## Goal

Two interlocking parts:

1. **`meta-create-adapter`** — the third factory sibling. Scaffolds `scripts/adapters/<family>/<provider>.py` from the `asana.py` exemplar, gates on `_contract.py` conformance, commits + emits a Keep/Undo receipt. Pure local files → **Tier-1**, no confirm to scaffold.
2. **The general Tier-2 publish gate** — the first time *any* adapter actually publishes externally, a one-time plain-language confirm fires. This is general adapter infrastructure, not adapter-specific code.

Highest blast radius in Phase 9 because adapters write to the **outside world**. Most careful PR.

---

## The six locked decisions

### 1. Where the gate sits — a loader wrapper

A new `adapters.publish(family, draft, root=None)` in `scripts/adapters/__init__.py` wraps the confirmed-check around `get(family).publish()`. `adapters/__init__.py` already owns "provider-name → module," so it is the natural home for "is this provider cleared to write externally." Generated adapters inherit the gate **for free** — they never implement it, so a scaffolded adapter cannot forget it. This is the "general infrastructure, not per-adapter" property the phase design requires.

```python
# scripts/adapters/__init__.py
class NeedsConfirmation(RuntimeError):
    """Raised when publish() is attempted but the integration has not been
    confirmed for external writes (Tier-2). Stops BEFORE any external call."""
    def __init__(self, family):
        self.family = family
        super().__init__(f"{family} integration needs a one-time confirm before its first external write")


def publish(family, draft, root=None):
    """Tier-2 gated publish. Returns None if no provider is configured (caller
    handles), raises NeedsConfirmation if configured-but-unconfirmed, else
    delegates to the provider adapter's publish()."""
    mod = get(family, root)
    if mod is None:
        return None  # not configured — caller degrades gracefully (unchanged)
    if not _is_confirmed(family, mod, root):
        raise NeedsConfirmation(family)
    return mod.publish(draft, root)
```

**Rejected:** gate inside each adapter's `publish()` (every generated adapter must remember it — a forgotten call writes externally silently); gate at the call site (works for the one site today but each future family re-implements it).

### 2. How `NeedsConfirmation` becomes a card — handler catches, new `confirm` card type, re-drive on confirm

- **The handler catches, not the gate.** `adapters.publish()` stays a pure low-level seam (no `task_lib` dependency) and just raises the typed exception. `handle_publish_jira` already catches `NotConfigured`/`RuntimeError`; it catches `NeedsConfirmation` the same way and writes the confirm card. Clean layering.
- **The confirm card lands on the COLLAB queue** — collab already means "supervised agent action requiring human approval," which is exactly a Tier-2 external-write confirm.
- **A purpose-built `confirm` card type**, not a reused `recommendation`. `recommendation`'s `accept` routes to `handle_accept`, which *applies a git patch* — wrong semantics for "flip a consent flag and publish." The confirm card needs a new `confirm` action + small `cardConfirm` JS handler + `POST /confirm` route — i.e. **new JS**, which is precisely the case `meta-create-card-type` (PR2) declared out of scope. We hand-author it here; PR3 is allowed to touch JS/backend. The card-type *factory* is composition-only; PR3 is not.
- **Confirm re-drives the blocked publish.** The confirm card carries `confirm_family` (which integration to clear) and `source_task` (the draft that was blocked). Clicking **Confirm** flips `confirmed: true` **and** re-publishes `source_task`, giving the seamless "confirm → it posts" flow rather than "confirm, now go re-click Publish."

```jsonc
// ui/task-board/cardtypes/registry.json
"actions": {
  // ...existing...
  "confirm": { "label": "Confirm", "handler": "cardConfirm", "primary": true }
},
"cardTypes": {
  // ...existing...
  "confirm": { "signals": [], "actions": ["confirm", "reject"], "body": "preview" }
}
```

### 3. The `confirmed` flag — provider-level, grandfather-by-config

- **Location: provider-level** (`project_management.jira.confirmed`), not family-level. "Confirmed" means *this external system is cleared to write*; switching `jira → asana` is a different system and earns its own confirm.
- **Grandfather-by-config semantics:** an explicit `confirmed: false` blocks; an *absent* flag means "confirmed iff the integration has creds configured" (`mod.is_configured(root)`). Consequences:
  - The factory scaffolds new adapters with an explicit `confirmed: false` → those are the **only** things that arm the Tier-2 gate.
  - An integration the operator typed creds into is self-evidently consented → never retroactively blocked. **Zero onboarding/Doctor changes, zero profile migration.**

```python
# scripts/adapters/__init__.py
def _is_confirmed(family, mod, root=None):
    provider = profile_lib.provider(family, root)
    block = profile_lib.integration_block(family, provider, root)  # {} if absent
    if "confirmed" in block:
        return bool(block["confirmed"])      # factory wrote false -> blocks
    return mod.is_configured(root)           # grandfather: creds = consent
```

**Rejected:** default-false everywhere + active migration (couples PR3 to onboarding + Doctor + a profile edit; any path that forgets the flag silently blocks a live integration).

### 4. `validate_adapter` — derive required methods from the Protocol

`validate_adapter(family, provider)` in `factory_lib.py` introspects the family's `_contract.py` for its `Protocol` subclass, reads its public method names (`ProjectManagementAdapter` → `{is_configured, publish}`; `TranscriptAdapter` → `{sync}`), imports the scaffolded module, and asserts each method exists, is callable, and has the expected param names (light `inspect.signature` check). **Import-only — never calls `publish()`, so no external creds.** General across families; the contract stays the single source of truth, mirroring how `validate_card_type` delegates to `card_schema`. New `validate-adapter` CLI subcommand on `factory_lib`.

**Rejected:** hardcoding `{is_configured, publish}` (project_management-specific; next family needs a code change; the list can drift from the actual Protocol).

### 5. Guard coverage — extend the existing guard

Extend `tests/test_engine_no_jay.py`'s globs with `scripts/adapters/**/*.py` so generated adapters are denylist-clean by construction. One canonical guard; also covers future hand-written adapters. **Verify existing adapter code passes the denylist before extending** (if it trips, that is either a real leak to fix or a scoping call). The skeleton inside `meta-create-adapter` is *already* guarded (it lives under `.claude/skills/**`) — belt-and-suspenders: skeleton guarded at the skill level, generated output guarded at the adapters level.

**Rejected:** a sibling `test_adapters_clean.py` (duplicates the denylist machinery; splits the guard across two files).

### 6. `meta-create-adapter` also writes `confirmed: false` into `integrations.yaml` (arms the gate)

The factory scaffolds **two** things: the `.py` module **and** a provider sub-block in `integrations.yaml` carrying `confirmed: false` (+ empty cred placeholders), via a new `profile_lib.set_integration_confirmed(...)`.

**This is load-bearing.** Under the grandfather rule (Decision 3), if the factory wrote only the `.py` and the user later configured creds with no `confirmed` key, the adapter would be *auto-grandfathered* and bypass Tier-2. Writing an explicit `confirmed: false` is what *arms* the gate for factory-built adapters.

It does **not** flip the active `provider` (switching tools stays a user/onboarding/Doctor choice). The receipt covers **both** files (the `.py` + the `integrations.yaml` edit), so Undo reverts both atomically.

---

## What is *not* receipted

Only the **scaffold** (Tier-1, local) gets a receipt + Undo (git revert of both scaffolded files). The downstream external actions do not, mirroring today's `handle_publish_jira`:

| Action | Tier | Affordance |
|---|---|---|
| Scaffold adapter (`.py` + `integrations.yaml` block) | Tier-1, local | Receipt card → Keep / Undo (git revert) |
| First publish via confirm | Tier-2, external | Task marked published + Jira link (no receipt — external, can't git-revert) |
| Consent flip `confirmed: true` | profile edit | Silent (one-way consent, not a revertable code change) |

---

## Data flow (the confirm round-trip)

```
User clicks "Publish to Jira" on a jira_draft card (integration configured, confirmed:false)
  └─> POST /api/tasks/{id}/publish-jira  →  handle_publish_jira
        └─> adapters.publish("project_management", draft)
              └─> _is_confirmed -> False  →  raise NeedsConfirmation   (NO external call)
        └─> except NeedsConfirmation:
              write COLLAB card_type=confirm  {confirm_family, source_task=<draft id>}
              return 200 "needs confirmation"

User clicks "Confirm" on the collab confirm card
  └─> POST /api/tasks/{id}/confirm  →  handle_confirm
        ├─> profile_lib.set_integration_confirmed("project_management", provider, True)
        ├─> _publish_and_record(source_task)            # shared core, refactored out of handle_publish_jira
        │     └─> adapters.publish(...) -> now passes -> (issue_key, issue_url)
        │     └─> mark source_task published + Jira link
        └─> complete the confirm card
```

A second publish (now `confirmed:true`) flows straight through `adapters.publish()` — one confirm, ever, per integration.

---

## Refactor: shared publish-and-record core

`handle_publish_jira` today does: parse draft → `adapters.get(...).publish()` → on success mark task published + Jira link + complete + trace; on error log + trace. PR3 extracts the **publish-and-record** body into a helper callable from both `handle_publish_jira` and `handle_confirm`, so the confirm re-drive reuses the exact success/trace path. The only behavioural change in `handle_publish_jira` is: call `adapters.publish(...)` (gated) instead of `adapters.get(...).publish()`, and add the `except NeedsConfirmation` branch.

---

## Testing & verification posture

**Units (pytest):**
- `adapters.publish` gate: raises `NeedsConfirmation` when configured-but-unconfirmed; passes through when confirmed; returns `None` when no provider; grandfather path (absent flag + configured → allowed).
- `_is_confirmed` semantics: explicit `false` blocks, explicit `true` allows, absent → delegates to `is_configured`.
- `profile_lib.set_integration_confirmed` + `integration_block` accessor (round-trips YAML, preserves siblings/comments).
- `validate_adapter`: passes on real `asana.py`; fails on (a) missing `publish`, (b) wrong signature, (c) import error — all cred-free fixtures.
- Guard extension: `test_engine_no_jay.py` now scans `scripts/adapters/**/*.py` and is green.

**Gates stay green throughout:** `python3 -m pytest`, `python3 scripts/card_schema.py`, `tests/test_engine_no_jay.py`.

**Live e2e (mandatory — verify the interaction through the real HTTP handlers, not just render):**
1. Seed a configured-but-`confirmed:false` project_management provider + a throwaway `jira_draft` task.
2. `POST /publish-jira` → assert **no external write**, response is "needs confirmation", a `confirm` card appears on the collab queue with `confirm_family` + `source_task`.
3. Chrome headless against `:8743` → the confirm card renders with a Confirm action.
4. `POST /confirm` → assert the flag flips to `true`, the publish re-drives (stub/dry-run the actual Jira MCP call so **no real ticket is created**), the source task is marked published, the confirm card completes.
5. Restart the board on `:8743` after backend changes (PR3 touches `task_server`/`adapters`, unlike PR2 which was static-only).

**Process:** subagent-driven-development — fresh implementer per task + two-stage review (spec-compliance, then code-quality). Mirror PR1/PR2 TDD task structure.

---

## Files touched

| File | Change |
|---|---|
| `scripts/adapters/__init__.py` | `NeedsConfirmation`, `publish()`, `_is_confirmed()` |
| `scripts/profile_lib.py` | `set_integration_confirmed()`, `integration_block()` accessor |
| `scripts/task_server.py` | `handle_publish_jira` (gated call + `except NeedsConfirmation`); extract `_publish_and_record`; new `handle_confirm` + `/confirm` route in `_card_handlers` |
| `ui/task-board/cardtypes/registry.json` | `confirm` action + `confirm` card type |
| `ui/task-board/js/*` | `cardConfirm` handler → `POST /confirm` |
| `scripts/factory_lib.py` | `validate_adapter()` + `validate-adapter` CLI subcommand |
| `.claude/skills/meta-create-adapter/SKILL.md` | new sibling skill (embedded `asana`-shaped skeleton, profile-read + token-clean) |
| `.claude/packs.yaml` | register `meta-create-adapter` in the `core` pack |
| `tests/test_engine_no_jay.py` | extend globs with `scripts/adapters/**/*.py` |
| `tests/` | new unit tests for the gate, profile accessors, `validate_adapter`, guard |

---

## Out of scope (unchanged from phase design)

- M365 calendar scheduling writes externally but bypasses the adapter seam — not gated in PR3.
- Personalizing an arbitrary third-party dropped skill (separate card-driven flow).
- Novel card body renderers/predicates (the `confirm` card reuses the `preview` renderer).
- Pre-existing carryovers listed in the phase design.

## Sequencing (risk-ordered, mirrors PR1/PR2 task structure)

1. `NeedsConfirmation` + `adapters.publish` gate + `_is_confirmed` + `profile_lib` accessors (units first, RED→GREEN).
2. `validate_adapter` + CLI (units against `asana.py` + broken fixtures).
3. `handle_publish_jira` refactor + `handle_confirm` + `/confirm` route + `confirm` card type + JS handler.
4. `meta-create-adapter` skill (embedded skeleton; arms `confirmed:false`); register in `core` pack.
5. Guard extension + full-suite green + live e2e confirm round-trip.
