# Magnolia Phase 3 — Adapters + Declarative Card Registry (Design)

**Date:** 2026-06-06
**Status:** Design approved (brainstorm complete) — ready to plan implementation
**Branch off:** `main` (merged Phase 2)
**Master design:** `2026-06-05-pm-os-portability-design.md` §6, §9, §11.3
**Closes residuals from:** `2026-06-05-phase-2-residual.md` (Granola seam, Pendo/Databricks
integration facts, `msgraph_cli` install route)

---

## Goal

Make the two highest-value integration families pluggable behind one interface
(**project-management**: Jira/Asana; **transcript**: Otter/Granola), and replace
hardcoded card rendering with a **declarative card registry** so future card types
render consistently with zero new rendering code. Fold in the Phase-2 residuals that
belong to this layer.

Everything reads identity/integration facts through `profile_lib`. The work stays on
the non-negotiable principles: **simplicity is the architecture** (simple Python +
data files, no plugin framework), **local-first**, **markdown/JSON + git over
databases/Docker**.

### Scope decisions (from brainstorm)

1. **Adapter breadth: interface + Jira/Otter only.** Define the interface cleanly,
   port the two providers already in use onto it. Asana and Granola ship as
   documented, interface-conforming **drop-in stubs** — the seam is proven by the
   contract + the loader, not by a speculative second integration. (Granola is thus a
   *wired, ready* seam, which closes the Phase-2 Granola residual.)
2. **Card registry: full build.** Define the declarative schema, refactor the JS
   renderer to consume it, verify every existing card renders through it unchanged
   (including the messaging card), and add a tested Python validator that gates future
   (factory-generated) card types.
3. **Schema home: standalone JSON file** (`cardtypes/registry.json`). The single
   source of truth both the JS renderer and the Python validator read natively, and
   that the future factory writes to without code generation. JS owns *rendering*, the
   JSON owns *vocabulary*, Python owns *validation*.
4. **No `when` mini-DSL.** A signal's trigger condition is a one-line JS predicate in a
   `signalPredicates` map keyed by signal id. The registry references signals by id;
   everything the factory composes (which signals/actions/body a card type uses, plus
   theme tokens) is declarative JSON. A genuinely new trigger = one new signal = one
   honest line of JS. Promote to a DSL later only if a real need appears.

### Dual-context constraint (load-bearing)

The operator runs this repo **two ways**: (a) the headless task-board dispatch, and
(b) a bare interactive Claude Code session in the terminal for ad-hoc skill use. **Every
skill edit in Phase 3 must work identically in both.** Because in both the consumer is
Claude reading `SKILL.md` and running commands, the de-hardcoding mechanism (read the
live value from `profile/` via `profile_lib`) is context-agnostic by construction. Skills
must also **degrade gracefully**: when a provider is `none`, the skill tells the user it
is not configured rather than failing.

---

## 1. Adapter interface

Lightweight **module-per-provider**, dispatched by profile. No plugin framework,
no entry-point discovery — a loader keyed on `profile_lib.provider(family)`.

```
scripts/adapters/
  __init__.py                 # get(family, root) -> module | None, keyed on profile_lib.provider
  project_management/
    __init__.py
    _contract.py              # typing.Protocol (zero runtime cost, pure legibility)
    jira.py                   # jira_publish.py logic moves here
    asana.py                  # stub: is_configured()->False; publish() raises NotConfigured
  transcript/
    __init__.py
    _contract.py              # typing.Protocol
    otter.py                  # wraps existing otter_sync
    granola.py                # documented drop-in stub -> {status:"unsupported"}
```

### Contracts (Protocols)

- **project-management** — `is_configured(root) -> bool`, `publish(draft, root) -> {"key","url"}`.
  Raises `NotConfigured` when the provider/profile isn't set up. (Publish-out only; this
  adapter is the *external* team system of record, not the internal task system.)
- **transcript** — `sync(root) -> {"status","provider", ...}` where status ∈
  `{ok, skipped, error, unsupported}`.

`typing.Protocol` documents the exact shape an adapter must satisfy with no runtime
machinery; future agents read `_contract.py` to know what to implement.

### Shims preserve every call site

- **`jira_publish.py`** keeps its CLI (`--task`, `--dry-run`) and its draft-parsing /
  prompt-building helpers, but the actual publish delegates to
  `adapters.project_management.<provider>.publish(...)`. The task-server "Publish to
  Jira" button is unchanged.
- **`transcript_sync.py`** keeps `sync(root)` as its public entrypoint (cron /
  onboarding), delegating to `adapters.transcript.<provider>.sync(root)`. Today's
  inline provider `if`-ladder moves into the loader.

The loader is the **only** place that maps provider-name → module. Adding Granola later
= write the impl in `granola.py`; it is already wired.

### Out of scope (named for later)

`calendar` (m365/google) and `doc_sync` keep their current modules; the
`adapters/<family>/` shape generalizes to them when their turn comes. Noted in the
contract docstrings.

---

## 2. Declarative card registry

**`cardtypes/registry.json`** is the design system as data.

```jsonc
{
  "slotOrder": ["head", "title", "context", "signals", "body", "actions"],

  "signals": {                       // reusable catalog; rendering metadata only
    "due":        { "icon": "due",      "variant": "due",      "tokens": ["--..."] },
    "overdue":    { "icon": "overdue",  "variant": "overdue",  "tokens": ["--..."] },
    "waiting_on": { "icon": "hourglass","variant": "waiting",  "tokens": ["--..."] },
    "schedule":   { "icon": "meeting",  "variant": "meeting",  "tokens": ["--..."] },
    "message":    { "icon": "chat",     "variant": "message",  "tokens": ["--q-human"] },
    "jira_draft": { "icon": "jira",     "variant": "accent",   "tokens": ["--accent","--accent-soft"] },
    "cron":       { "icon": "cron",     "variant": "cron",     "tokens": ["--..."] }
  },

  "actions": {
    "mark_done":   { "label": "Mark done",   "handler": "quickDone",  "primary": true, "tokens": ["--..."] },
    "open_output": { "label": "Open output", "handler": "outputLink", "truncatePath": true, "tokens": ["--..."] },
    "publish_jira":{ "label": "Publish to Jira", "handler": "publishJira", "tokens": ["--accent"] }
  },

  "cardTypes": {
    "task":           { "signals": "auto", "actions": ["mark_done", "open_output"], "body": null },
    "recommendation": { "body": "diff",      "actions": ["accept", "reject"] },
    "receipt":        { "body": "preview",   "actions": ["keep", "undo"] },
    "graduation":     { "body": "agreement", "actions": ["graduate"] }
  }
}
```

- A task picks its type via `task.card_type` (default `"task"`). Every existing card is
  `"task"` → no behavioral change.
- **Signal trigger conditions live in JS** as `signalPredicates[id] = (task) => bool`.
  The registry references signals by id only. `"signals": "auto"` means "render every
  signal whose predicate matches this task" (today's behavior); an explicit list pins a
  fixed set for a typed card.
- **Body layouts** live in a small named-renderer map in JS (`bodyRenderers["diff"]`,
  `["preview"]`, `["agreement"]`). The one place body markup lives.
- **`recommendation` / `receipt` / `graduation` are defined now** even though their
  board surfaces ship in Phase 4–6: §11.5 requires these card kinds *defined* before the
  UI commission so the spec is complete. Bodies can be minimal placeholders here; the
  point is the registry entries + slot contract exist.

### JS renderer refactor

`ui/task-board/js/card-registry.js` (new) holds: the loaded registry, `signalPredicates`,
`bodyRenderers`, and a generic `renderCardFromRegistry(task)` that walks `slotOrder`.
`board.js::renderCard()` becomes a thin call into it. `now.js` and `board.js` callers are
unchanged (same `renderCard(task, queue)` signature).

The registry JSON is **served by the task server** (static file under a path the board
fetches) and **read from disk by the Python validator** — same file, two consumers.

### Theme-token hard rule (§9)

Signals/actions/cardTypes may reference **theme tokens only** — never a hardcoded color,
radius, or transition. This is what guarantees every present and future card type is
100% theme-aware across all moods. Enforced by the validator (§3).

---

## 3. Python validator (tested)

`scripts/card_schema.py` + `tests/test_card_schema.py`. Loads `registry.json` and asserts:

- Referential integrity: every signal/action a `cardType` references exists in its catalog.
- Predicate coverage: every signal id in the catalog has a matching `signalPredicates`
  entry. (Linked via a co-located `cardtypes/signal-ids.txt` or a JS-exported manifest —
  least-fragile mechanism chosen during planning.)
- **Token-only rule:** every `tokens` entry is a real theme variable (parse `--var` names
  from `ui/task-board/themes/_TEMPLATE.css`); regex-reject hex / `rgb(` / `px` literals in
  any registry string.
- Slot integrity: `slotOrder` is exactly the known slots; every cardType `body` names a
  known body-renderer or `null`.

This is the gate the future factory (Phase 8) runs before writing a new card type.

---

## 4. Integration-fact migration (Pendo / Databricks)

Extend `integrations.yaml` with an `analytics` group:

```yaml
analytics:
  pendo:
    provider: "none"          # pendo | none
    subscription_id: ""        # was hardcoded 4818486697721856
    app_ids: {}                # name -> id
  databricks:
    provider: "none"          # databricks | none
    catalog: ""                # was hardcoded is_prod
    sources: {}                # gong/zendesk/devops -> table refs
```

- Add `profile_lib.pendo_config()` / `databricks_config()` accessors + CLI flags
  (`--pendo-subid`, etc.) so headless **and** interactive Claude can read live values.
- Sweep `context-pendo-analytics`, `context-databricks-analytics`,
  `metric-quarterly-rocks`, and affected workers: replace literal IDs/catalog/table-maps
  with "read from profile via `profile_lib`." Template ships blank; real values live only
  in `profile/`.
- Honor the **dual-context constraint** and graceful degradation (provider `none` →
  skill says "not configured").

---

## 5. Smaller residual fold-ins

- **`msgraph_cli` (`mgc`) install route** in `doctor.py` — replace the placeholder remedy
  with the real macOS install command (confirm during the work).
- **Word-document-box horizontal-scroll regression** (agent card output path too wide) —
  the `open_output` action carries a `truncatePath` presentation contract (CSS `max-width`
  + ellipsis on the path span). Fix lands as part of moving the actions row into the
  registry, so the registry's presentation contract is what prevents recurrence.

---

## 6. Test & verification plan

- Reuse `tests/conftest.py::profile_root`.
- New Python suites:
  - `test_adapters.py` — loader dispatch by provider; contract conformance; jira/otter
    shim parity with pre-refactor behavior; asana/granola stub behavior (`is_configured`
    False, `publish` raises, granola `sync` → unsupported).
  - `test_card_schema.py` — the validator (referential integrity, predicate coverage,
    token-only rule, slot integrity), with intentionally-broken fixtures that must fail.
  - Extended `test_profile_lib.py` — pendo/databricks accessors + CLI flags.
- **No JS test harness** (rejected adding Node infra to a Python repo). The renderer
  refactor is verified by (a) the Python validator gating the data and (b) a manual visual
  pass on a seeded board covering all existing card variants incl. messaging + the
  Word-box fix. This is stated honestly as manual-verified.
- Each implementation task: fresh implementer subagent + two-stage review
  (spec-compliance → code-quality) with fix/re-review loops.

---

## 7. File inventory

**New:** `scripts/adapters/**`, `cardtypes/registry.json`, `cardtypes/signal-ids.txt`
(or JS manifest), `scripts/card_schema.py`, `ui/task-board/js/card-registry.js`,
`tests/test_adapters.py`, `tests/test_card_schema.py`.

**Changed (shims / refactor / sweep):** `jira_publish.py`, `transcript_sync.py`,
`ui/task-board/js/board.js`, `scripts/profile_lib.py`,
`profile.example/integrations.yaml`, `scripts/doctor.py`, `scripts/task_server.py`
(serve the registry file), `.claude/skills/context-pendo-analytics`,
`.claude/skills/context-databricks-analytics`, `.claude/skills/metric-quarterly-rocks`,
affected `scripts/workers/*.md`.

---

## 8. Open questions carried into planning

- Predicate-coverage link mechanism: co-located `signal-ids.txt` vs. JS-exported manifest
  the validator parses. Pick least-fragile.
- Exact static-serve path for `registry.json` from `task_server.py` (and the board's
  fetch URL).
- `mgc` real macOS install command (confirm live).
- Whether `recommendation/receipt/graduation` bodies are stubbed empty or given minimal
  placeholder markup now (lean: minimal placeholder so the slot contract is exercised).
