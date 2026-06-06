# Magnolia Phase 3 — Residual Triage & Definition of Done

Date: 2026-06-06
Branch: `feat/phase-3-adapters-card-registry`

This document closes out Magnolia Phase 3 (Adapters + Declarative Card Registry). It
records the Definition of Done and the residual / deferred items surfaced by the
per-task two-stage reviews and the final whole-branch review.

---

## Definition of Done

Verified on macOS at Phase 3 close.

- [x] `python3 -m pytest` passes from a clean checkout — **104 passed** (was 86 at Phase 2
      close; +18 across adapters, card-schema, profile accessors, tenant guard, doctor).
- [x] `python3 scripts/card_schema.py` → `registry.json OK`.
- [x] **Adapter seam, both families, wired into production paths.** A single loader
      (`scripts/adapters/__init__.py::get(family, root)`) maps `profile_lib.provider(family)`
      → a `scripts/adapters/<family>/<provider>.py` module. `typing.Protocol` contracts
      (`_contract.py`) document each family's shape.
  - project-management: `jira.py` (wraps `jira_publish.publish_to_jira`), `asana.py` stub.
    **`task_server.handle_publish_jira` now dispatches via the loader** (commit 13f2083) —
    not a direct `jira_publish` call — so the Asana stub / `NotConfigured` graceful
    degradation are reachable in production.
  - transcript: `otter.py` (delegates to `transcript_sync._run_otter`), `granola.py` stub.
    `transcript_sync.sync()` dispatches via the loader.
- [x] **Declarative card registry.** `ui/task-board/cardtypes/registry.json` (+ `signal-ids.txt`)
      is the single source of truth; `scripts/card_schema.py` validates it (token-only §9 rule
      incl. rgba/hsla/oklch/rem/%, referential integrity, exact `slotOrder` order,
      signal→predicate cross-check) and is tested. `board.js::renderCard` is a thin wrapper
      over `card-registry.js::renderCardFromRegistry`, proven **26/26 byte-identical** to the
      old hardcoded renderer across all card variants (incl. the messaging card), with a
      graceful fallback if the registry fetch fails.
- [x] **Agent-card horizontal-scroll regression fixed** at root cause: the modal `.dt-artifact`
      grid item lacked `min-width: 0` (CSS-grid `min-width:auto` defeated the existing ellipsis).
      Fixed in `index.html`. (The reported "Word box" was the modal, not the card action — the
      card action only ever renders a short label.)
- [x] **Pendo/Databricks integration facts → profile.** `profile_lib.pendo_config`/
      `databricks_config` + `--pendo-subid`/`--databricks-catalog` CLI flags +
      `integrations.yaml` `analytics` block. 17 skill files de-hardcoded to read from profile
      (dual-context: identical headless vs interactive; graceful degradation when provider is
      `none`). Guard test `tests/test_no_hardcoded_tenant.py` bans `4818486697721856` + `is_prod`.
- [x] **`msgraph_cli` (`mgc`) install remedy** is a real macOS route (`aka.ms/get/graphcli`
      binary download — no Homebrew formula exists, verified vs msgraph-cli issue #405). The
      internal confirm-note was moved to a code comment so it can't leak into user-facing Doctor
      output (test-guarded).

---

## Deferred (named, not in Phase-3 scope)

- **Asana publish impl** and **Granola sync impl** — both ship as documented, contract-conforming
  stubs. The seam is wired (select the provider in `integrations.yaml` and the loader finds the
  module); making them real = implement `publish()` / `sync()` against the respective API/MCP,
  mirroring the Jira/Otter modules.
- **`calendar` (m365/google)** and **`doc_sync`** adapters — named for later; the
  `adapters/<family>/` shape generalizes to them (noted in the contract docstrings). Their current
  scripts (`find_meeting_times.py`, `create_calendar_event.py`, `doc_sync.py`) are untouched.
- **`recommendation` / `receipt` / `graduation` card types are defined but INERT.** They exist in
  `registry.json` (required so the upcoming UI commission spec is complete — master design §11.5),
  but: `task.card_type` is read and never written anywhere; the three body renderers emit empty
  placeholder markup; and their actions (accept/reject/keep/undo/graduate) have **no handler branch**
  in `card-registry.js::_renderActions` (only `mark_done`/`open_output` are wired). Phase 4–6 ships
  their surfaces and handlers.
- **No JS test harness** (deliberate — a Python repo; adding Node test infra was rejected). The JS
  renderer refactor is verified by (a) the tested Python validator gating the registry data and
  (b) a throwaway Node render-equivalence harness (26/26 byte-identical, not committed). **A final
  on-screen human visual pass of the live board is still owed** (controller to arrange): confirm all
  card variants render and an agent card with a long output path no longer horizontally scrolls.

---

## Smaller hardening notes (non-blocking, surfaced in review)

- **`signal-ids.txt` is a hand-maintained mirror** of the `signalPredicates` map in
  `card-registry.js`. The validator checks only the catalog→predicate direction (a catalog signal
  lacking a predicate id fails); it does NOT verify the reverse, nor that the txt file actually
  matches the JS map. Accepted tradeoff (design "least-fragile mechanism"); a future improvement is
  to export the predicate keys from JS and diff against the txt.
- **`workflow-jira-home/SKILL.md` still hardcodes Vantaca Jira facts** (cloudId `vantaca.atlassian.net`,
  project `VNT`, board `1096`, an issue-type-ID table). This was NOT in Task 7's scope (which targeted
  the Pendo/Databricks analytics skills), and the engine (`jira_publish.py`) already reads Jira facts
  from the profile — so this is a skill-prose gap, not an engine leak, and the tenant guard test does
  not cover it. Deferred de-hardcoding target for a future skill-prose sweep.
- **Onboarding scaffold for the `analytics` block.** `profile.example/integrations.yaml` carries the
  empty `analytics` block, but onboarding does not yet populate a real `analytics` section
  (provider/subscription_id/app_ids/catalog/sources) into a live `profile/`. Confirm onboarding adds
  it so configured operators have values for the de-hardcoded skills to read.
- **`ensureCardRegistry()`** (`card-registry.js`) is a defined-but-unused public accessor, intentionally
  kept as the load-gate hook for a future caller that wants to await the registry before first paint.
- **`handle_publish_jira` failure-branch duplication** (None / NotConfigured / RuntimeError each repeat
  a ~6-line log+trace+respond block). Readable and consistent with the file's style; a
  `_fail_publish(handler, task_id, draft, msg, status)` helper would be a nice-to-have, not required.
- **`mgc` remedy URL** advertises `.zip` but `aka.ms/get/graphcli` actually serves a `.tar.gz`; the
  remedy says "extract" (arch-neutral) and the code comment flags confirming the asset name on a live
  Doctor run.
- **Git author identity:** all Phase-3 commits were authored as `Jay Jenkins
  <jayjenkins@Jays-MacBook-Pro.local>` (the machine default), not `jay.jenkins@vantaca.com`. Set
  `git config user.email` and consider rewriting the branch's author identity before opening the PR so
  commits link to the right GitHub account.

---

## Test inventory added this phase

`tests/test_adapters.py` (PM + transcript loader/contract/stubs), `tests/test_card_schema.py`
(validator, 6 cases), tenant guard `tests/test_no_hardcoded_tenant.py`, extended
`tests/test_profile_lib.py` (pendo/databricks accessors) and `tests/test_doctor.py` (mgc remedy).
