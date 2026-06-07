---
name: meta-create-adapter
description: Use when the operator asks to add, build, or scaffold a new external integration / adapter (a new provider for project-management, transcripts, calendar, etc.) - scaffolds scripts/adapters/<family>/<provider>.py from the contract exemplar, arms the Tier-2 confirm, validates conformance, and emits a Keep/Undo receipt card
---

# Create Adapter

Scaffold a new integration adapter (`scripts/adapters/<family>/<provider>.py`) that
the loader can dispatch to. **Read `meta-factory-core` first** — this skill is its
adapter specialization. Reuses `meta-create-skill`'s RED-GREEN-REFACTOR spine.

Adapters write to the **outside world**, so they are **Tier-2**: the first time an
adapter actually publishes, a one-time plain-language confirm fires on the collab
queue (handled by the general publish gate — you do not build it per adapter).
Scaffolding only writes local files, so creating an adapter is itself Tier-1.

## When to Use

- The operator wants a new provider for an existing family ("add a Linear adapter",
  "support Asana for issues") or a new external integration generally.
- **Not** for a new worker (use `meta-create-worker`) or a new card type
  (use `meta-create-card-type`).

## The Gate (must be green before commit)

1. `python3 scripts/factory_lib.py validate-adapter <family> <provider>` -> `ok`
   (the module imports and exposes every method of the family's `_contract` Protocol
   as a callable with the right parameters — import-only, no external creds).
2. `python3 -m pytest tests/test_engine_no_jay.py -q` -> passes (the adapter is
   denylist-clean: it reads identity/team specifics from `profile/`, never hardcodes).

## Workflow

1. **Capture the spec.** Ask which family (`project_management` | `transcript` |
   `calendar` | ...) and provider name, and what external system it targets. Look at
   the family's `_contract.py` for the methods to implement and at the existing
   exemplar (`scripts/adapters/project_management/asana.py`) for the shape. Structured
   targets (cloud id, project key, assignee) live in `profile/integrations.yaml` — the
   adapter reads them at runtime. Fuzzy team nuance with no field goes to the profile
   `conventions` slot via `profile_lib.set_integration_conventions(...)` — never the
   adapter.
2. **Scaffold** `scripts/adapters/<family>/<provider>.py` from the skeleton below.
   Keep it a documented stub (raises `NotConfigured` until creds are wired) unless the
   operator wants a real implementation now — mirror `jira.py` if so.
3. **Arm the Tier-2 gate.** Write `confirmed: false` for the new provider so the
   first external write triggers the one-time confirm (do NOT skip this — without it
   the grandfather rule would auto-confirm the adapter once creds are added):
   `python3 -c "import sys; sys.path.insert(0,'scripts'); import profile_lib; profile_lib.set_integration_confirmed('<family>', False, provider='<provider>')"`
   This does **not** switch the active provider — the operator selects it later via
   onboarding/Doctor.
4. **Gate** — run both gate checks above. Fix until green.
5. **Commit + receipt** — stage BOTH the adapter and the profile change:
   `python3 scripts/factory_lib.py commit-and-receipt --summary "a <provider> <family> adapter" --kind adapter scripts/adapters/<family>/<provider>.py profile/integrations.yaml`
6. **Hand back** — tell the operator: *"Built you a `<provider>` adapter -> there's a
   receipt card. Keep / Undo. The first time it posts to <system>, I'll ask you to
   confirm once."* Never mention git.

## Adapter Skeleton (contract-conformant, profile-driven, denylist-clean)

```python
"""<Provider> <family> adapter — documented drop-in stub.

The seam is wired: select provider "<provider>" in integrations.yaml and the loader
finds this module. To make it real, implement publish() against the <provider> API/MCP
(mirror jira.py: read config from profile_lib, push the draft, return (id, url)) and
flip is_configured() to check the profile. Until then it degrades gracefully. Read all
target/identity specifics from profile/ at runtime — never hardcode them here.
"""
from adapters.<family>._contract import NotConfigured


def is_configured(root=None) -> bool:
    return False


def publish(draft, root=None):
    raise NotConfigured(
        "<Provider> adapter is a stub — implement publish() against the <provider> API")
```

> Transcript-family adapters implement `sync(root) -> dict` instead of
> `is_configured`/`publish` — check the family's `_contract.py` and mirror `otter.py`/
> `granola.py`. `validate-adapter` derives the required methods from that contract.

## Iron Laws

1. **The adapter reads target/identity specifics from `profile/`** — never hardcoded.
2. **Gate green before commit** (validate-adapter + test_engine_no_jay).
3. **Arm the Tier-2 gate** — write `confirmed: false` for the new provider.
4. **Stage only the adapter file + the profile change** via `factory_lib`.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Hardcoding the cloud id / project key in the adapter | Read from `profile/integrations.yaml` at runtime |
| Forgetting `confirmed: false` | The factory adapter would bypass the Tier-2 confirm — always arm it |
| Building a per-adapter confirm prompt | The general publish gate handles Tier-2 — you don't |
| Telling the operator about the commit | Speak in Keep / Undo |

## Related Skills

- **meta-factory-core**: the shared lifecycle + capture-to-profile rule (read first).
- **meta-create-skill**: the TDD spine.
- **meta-create-worker** / **meta-create-card-type**: the sibling factories.
