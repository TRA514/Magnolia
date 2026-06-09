# Trust-ladder ENFORCING — autonomous auto-ship, judge-in-the-loop, kill switch — design

**Date:** 2026-06-09
**Status:** Approved, ready for implementation
**Branch:** `feat/trust-ladder-enforcement`
**Scope (new):** `scripts/enforce_lib.py`, `scripts/shipper.py`
**Scope (edit):** `scripts/judge.py`, `scripts/task_cli.py`, `scripts/ladder_lib.py`, `scripts/profile_lib.py`, `profile/config.yaml`, `scripts/task_server.py`, `ui/task-board/` (top bar + `quality.js` + `card-registry.js` + `index.html`), `docs/reference/architecture.md`
**Follows:** `docs/plans/2026-06-09-trust-ladder-passive-signal-design.md` (commit 95c7e5a) — that work left the ladder advisory on purpose; this is the deferred enforcement half.

## Problem

The trust ladder is **advisory only**. `ladder_lib.tier_of(task_type)` returns
`shadow → supervised → autonomous`, but `tier_of` is consumed in just two places —
a Quality-tab display label (`build_quality`) and the graduate-card handler
(`graduate_card`). **Nothing in dispatch/completion/review reads the tier to change
behavior.** Graduating a task-type changes a label and unlocks no autonomy.

This epic makes the tier *do* something: an autonomous action-type ships its terminal
action automatically; a supervised type gets a judge-driven quality gate; and a manual
kill switch can instantly pull a type out of autonomous.

## The two design tensions (resolved)

### Tension 1 — autonomy vs invariant #5 (Tier-2)

These are **different gates that compose**, not competitors:

- **Tier-2 (invariant #5)** is a *per-integration* gate: "has the operator given one
  plain-language confirm before this provider's first external write?" Enforced by
  `adapters.publish()` raising `NeedsConfirmation`.
- **The trust ladder** is a *per-task-type* gate: "must a human approve each individual
  instance, or has this type earned auto-ship?"

Composition: auto-ship calls the **same** `adapters.publish()`. So if the integration
isn't confirmed yet, auto-ship **still** raises `NeedsConfirmation` → the existing
one-time confirm card is emitted and the task parks. **Autonomy never bypasses the
first-write confirm.** An autonomous type whose integration is already confirmed ships
without per-instance approval; an autonomous type whose integration is unconfirmed
triggers the confirm exactly once, then ships thereafter.

### Tension 2 — action vs artifact split

Only **ACTION** types can reach autonomous and auto-ship: `ACTION_TYPES =
{"send-message", "publish-ticket"}`. **ARTIFACT** types (PRDs, research, memos) cap at
supervised forever — autonomy can't transfer the accountability of signing a document.
This is enforced **in code**, not by convention: `enforce_lib` hard-stops any non-action
type from auto-shipping even if its tier store somehow reads `autonomous`.

## Beta posture (resolved)

Autonomous **auto-ship** ships **default-OFF** behind a global posture flag
`autonomy_enforcement` in `profile/config.yaml` (default `false`). The ladder still
graduates types to `autonomous` (advisory) but nothing auto-ships until the operator
flips the flag on. The flag is surfaced as an **"Autonomous Mode" toggle** in a
theme-compliant **settings cog** in the top-right of the top bar. The kill switch +
never-deleted Keep/Undo receipts (invariant #6) are the safety net.

The **supervised judge-revision loop is NOT behind this flag** — it performs no external
write and keeps the human approving externals, and it is opt-in by virtue of graduation
to supervised. The flag guards only the externally-risky auto-ship.

## Architecture — the judge is the enforcement seam

The judge already fires (detached) right after `agent:complete`, and it is the only
component holding the quality score. So the tier policy runs **after the judge scores**:
`judge.write_back()` → `enforce_lib.apply_post_judge(task_id, verdict)`.

### The tier × score policy

| Tier | Judge `< bar` (revisions remaining) | Judge `>= bar` |
|---|---|---|
| **shadow** | park (advisory — current behavior) | park (advisory — current behavior) |
| **supervised** | **revise** (reset + re-dispatch `--rerun`, carry `judge_why`) | **park** for human approval (judge comment advisory) |
| **autonomous** (action type + flag ON) | **revise** (same loop) | **auto-ship** via Tier-2 shipper + receipt |

Notes:
- **bar** = `JUDGE_GOOD_THRESHOLD` (7), configurable via `ladder.json` thresholds.
- **Auto-ship is judge-gated**: a type auto-ships only on a *passing* score. No score
  (judge skipped — `detect_kind` None — or judge unavailable) → park. Fail-safe: autonomy
  can never ship unscored or below-bar work.
- **Artifacts get the revision loop too** at supervised (auto-revised to quality, then
  parked — they never ship). This is the main value of supervised for artifacts.
- **autonomous-but-flag-OFF** behaves like supervised (revise/park), never ships.

### The revision loop

Reuses the existing rerun path (`handle_rerun_task` mechanics): reset agent fields +
`status="open"`, append a comment carrying the judge's `why` as revision guidance, then
spawn `task_dispatch.py --task <id> --rerun` (detached, Claude env stripped — mirrors the
Rerun button). The rerun agent reads the activity log for guidance (the rerun prompt
block, broadened to recognize a `judge` revision comment alongside human comments).

- Bounded by **`MAX_REVISIONS`** (persisted as `revision_count` in frontmatter; default
  **1**, configurable). Each rerun re-fires the judge → re-evaluates → self-terminates.
- After revisions are exhausted (below bar, no revisions left) → **park** for human.
  Never auto-ship below-bar work.

### Where ship happens (and the Tier-2 boundary)

Auto-ship runs in a **trusted backend process** (the judge / `enforce_lib`), **never the
headless LLM agent session** — which still has zero send tools (`chat_runner`
`CHAT_ALLOWED_TOOLS` boundary unchanged). The shipper calls the same Tier-2-gated
`adapters.publish()` cores. So "the board (and now the judge/enforce backend) publishes;
the agent never does" holds.

## Components

### `scripts/enforce_lib.py` (new)

```
ACTION_TYPES = {"send-message", "publish-ticket"}

def action_type_of(fm) -> str | None        # the canonical action type, else None (artifact)
def revision_bar(path=None) -> int           # JUDGE_GOOD_THRESHOLD, threshold-overridable
def max_revisions(path=None) -> int          # default 1, config-overridable
def autonomy_enabled(root=None) -> bool      # the global posture flag

def apply_post_judge(task_id, verdict, *, root=None, ladder_path=None) -> str
    # Returns one of: "park" | "revise" | "shipped" | "needs_confirm" | "error".
    # Reads tier_of(action_type_of or grouping key), the score, the flag, revision_count.
    # Pure decision + thin effect calls (reset+rerun, or shipper.ship). Never raises into
    # the judge — judge.py stays additive and exits 0; any failure → "park".
```

The grouping key for `tier_of` mirrors `graduation_assess`/`build_quality`
(`task_type or domain or "uncategorized"`); for action types it is the clean
`action_type` (`send-message`, `publish-ticket`).

### `scripts/shipper.py` (new)

Extract the existing terminal-action cores from `task_server.py`:
`_attempt_send_message`, `_attempt_publish`, `_message_draft_from_task`, and the
receipt/`_note` helpers they need. Keep behavior identical (same `(status, payload)`
contract). `task_server.py` handlers (`handle_send_message`, `handle_publish_jira`,
`handle_confirm`) become thin wrappers over `shipper`. Existing tests
(`test_send_message_route`, `test_publish_core`, `test_messaging_tier2`,
`test_send_message_graph`) must stay green unchanged.

`shipper` also exposes the function `enforce_lib` calls to auto-ship by family,
returning the same `(status, payload)` shape, and the receipt-card emitter.

### `scripts/judge.py` (edit — add the `ticket` kind + the enforcement call)

- `detect_kind`: `task_type == "publish-ticket"` → `"ticket"` (checked before the
  document fallback). Keys off the stamped task_type — no body sniffing needed.
- `RUBRICS["ticket"] = ("judge-rubric-ticket", DEFAULT_RUBRIC_TICKET)`.
- `DIMENSIONS_BY_KIND["ticket"] = ["completeness", "clarity", "actionability", "format"]`
  (final keys TBD in plan; quality.js already renders arbitrary dimension keys).
- `gather_evidence`: `kind == "ticket"` → `parse_jira_draft(body)`, formatted as a field
  block (type, summary, description, fields). `KIND_EVIDENCE_LABEL["ticket"] =
  "DRAFTED TICKET (score this)"`.
- After `write_back`, call `enforce_lib.apply_post_judge(task_id, verdict)` (swallow all
  errors — strictly additive, exit 0).

### `scripts/task_cli.py` (edit — stamp `publish-ticket`)

In `cmd_agent_complete`, after the agent finishes: if the task body contains
`<!-- JIRA_DRAFT -->` and `task_type` is unset/empty, set
`task_type = "publish-ticket"`. Local frontmatter write; gives clean, consistent keying
across the ladder, judge, Quality tab, and enforcement going forward.

### `scripts/ladder_lib.py` (edit — kill-switch helper)

`kill_to_supervised(task_type, path=None)`: `set_tier(task_type, "supervised")` and
`note_demotion_signal(task_type, False)` (reset the streak). Idempotent. (Generalize to
a `demote_to(tier)` if cheap; the UI only needs → supervised.)

### `scripts/profile_lib.py` + `profile/config.yaml` (edit — the flag)

- `config.yaml`: add `autonomy_enforcement: false`.
- `profile_lib`: `autonomy_enforcement(root=None) -> bool` getter and
  `set_autonomy_enforcement(bool, root=None)` setter (writes `config.yaml`, ruamel
  round-trip preserving comments, mirroring existing setters).

### `scripts/task_server.py` (edit — routes + wrappers)

- `GET /api/config/autonomy` → `{enabled: bool}`.
- `POST /api/config/autonomy` `{enabled: bool}` → flips the flag.
- `POST /api/tasks/{id}/demote` → `ladder_lib.kill_to_supervised(grad/grouping key)`;
  used by the Quality-tab kill switch. (Keyed by `task_type` passed from the frontend
  row.) Returns the new tier.
- Send/publish handlers delegate to `shipper`.
- The receipt-card emission lives in `shipper`/`enforce_lib`; the server only needs the
  new card type registered in the card registry (see frontend).

### Frontend (`ui/task-board/`)

- **Settings cog** (top bar, top-right, right of the Mood control): a theme-compliant
  gear icon (added to `icons.js`, token-only styling — invariant #3) opening a small
  popover. The popover holds the **Autonomous Mode** toggle wired to
  `GET/POST /api/config/autonomy`. Toggle is a calm switch; no interaction/UX change to
  Moods. New JS module (e.g. `js/settings.js`) + a mount point in `index.html`.
- **Quality-tab kill switch** (`quality.js`): on each group card whose `phase` is
  `autonomous`, render an obvious "Stop auto-shipping" control → `POST
  /api/tasks/.../demote` with the group's `task_type` → toast + re-render. Only renders
  for `autonomous` types. Token-only styling.
- **Receipt card face**: register the auto-ship receipt as a card type in
  `card-registry.js` (and `cardtypes/registry.json` via `card_schema.py`), theme-token
  only. Keep dismisses; Undo demotes the type to supervised + flags (see below).

## Receipt + Undo semantics

An auto-shipped action writes a **receipt card** to the collab queue recording exactly
what shipped (sender, channel/issue, recipient/board, timestamp). Never deleted
(invariant #6).

- **Keep** — acknowledge + dismiss (archive) the receipt.
- **Undo** — honest about irreversibility: it does **not** unsend an email or unpost a
  ticket (it can't). It **demotes that type to supervised** (so it stops auto-shipping)
  and flags the receipt. The receipt copy states plainly that the external action already
  happened. (Reuses the kill-switch demote path.)

## Safety / reversibility

- Tier-2 first-write confirm still fires on auto-ship (composes with the per-type gate).
- Auto-ship is judge-gated → never ships unscored or below-bar work.
- Global flag default-OFF; auto-ship is opt-in per install.
- Kill switch is instant (no waiting for the twice-weekly assessor); Undo + the assessor's
  auto-demote remain as additional brakes.
- Receipts are never deleted (invariant #6).
- Revision loop is bounded by `MAX_REVISIONS`.
- Engine stays de-personalized (invariant #1) — no identity literals; the flag and tiers
  are per-install config/runtime, not artifact content.
- Agent session still has zero send tools — the headless LLM can never ship.

## Testing (TDD; green gates before every commit)

Gates: `python3 -m pytest` · `python3 scripts/card_schema.py` (→ `registry.json OK`) ·
`python3 -m pytest tests/test_engine_no_jay.py`.

- **`enforce_lib`**:
  - `action_type_of` truth table: `send-message` → action; body/`publish-ticket` →
    action; document/PRD/research → None (artifact).
  - `apply_post_judge` matrix: shadow → park (any score); supervised below-bar+revisions
    → revise; supervised below-bar+exhausted → park; supervised ≥bar → park; autonomous
    ≥bar + action + flag ON → shipped; autonomous ≥bar + **artifact** → park (hard-stop);
    autonomous ≥bar + action + flag OFF → park; autonomous below-bar → revise; no score →
    park; `NeedsConfirmation` from shipper → needs_confirm (parks, confirm card emitted).
  - `max_revisions` / `revision_bar` honor `ladder.json` overrides.
- **`shipper` extraction**: existing send/publish/Tier-2 tests stay green unchanged.
- **`judge`**: `detect_kind` → ticket for `publish-ticket`; `gather_evidence` ticket
  branch parses the draft; `apply_post_judge` is called after write-back; judge stays
  exit-0 / additive on enforce errors.
- **`task_cli`**: `cmd_agent_complete` stamps `publish-ticket` when body has the marker
  and leaves an existing `task_type` untouched.
- **`ladder_lib`**: `kill_to_supervised` sets supervised + resets streak; idempotent.
- **`profile_lib`**: autonomy flag getter/setter round-trips `config.yaml` preserving
  comments; default False when absent.
- **routes** (`task_server`): autonomy GET/POST; demote endpoint demotes + returns tier.
- **`card_schema`**: the receipt card type validates token-only.
- **`test_engine_no_jay`**: denylist-clean.

## Out of scope (explicit)

- `schedule-meeting` auto-ship (needs an auto-slot-pick policy and isn't behind the
  Tier-2 `adapters.publish` gate) — deferred.
- The human-queue audit cron and the promotion Q&A / cluster→factory bridge (tracked
  separately).
