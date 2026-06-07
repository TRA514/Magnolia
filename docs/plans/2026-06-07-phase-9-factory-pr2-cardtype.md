# Phase 9 Factory — PR2: meta-create-card-type Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A `meta-create-card-type` skill that scaffolds a new card type by adding one entry to the declarative `cardTypes` registry — **registry-composition-only** (a new type assembled from *existing* signals / actions / body-renderers), preserving the "zero new render code" promise. Gated by `scripts/card_schema.py` (the token-only design-system gate), committed + Keep/Undo'd through the PR1 factory spine.

**Architecture:** The card registry (`ui/task-board/cardtypes/registry.json`) already drives rendering: `js/card-registry.js` fetches it at runtime and `renderCardFromRegistry` walks `slotOrder`, rendering any registered `cardTypes` entry generically from existing slot builders, signal predicates, action handlers, and body renderers. So a new card type that *composes existing pieces* needs **no JS** — just a registry entry. The skill captures the spec, adds the entry, runs `card_schema.py` (which rejects unknown signals/actions/renderers and any hardcoded color/size — this is exactly what enforces composition-only), then commits via `factory_lib commit-and-receipt --kind card-type` and emits a receipt. Anything needing a *new* signal predicate, action handler, body renderer, or head-kind label is JS work → **out of scope**; the skill refuses and hands it to engineering.

**Tech Stack:** Python 3 (Homebrew, PEP-668), `pytest`. The artifact is a JSON registry edit (no new JS). Verify live on the dev board `:8743` via Chrome headless.

**Conventions:**
- Branch already created: `feat/phase-9-factory-pr2-cardtype`, based on merged main (PR1 present). Git author set locally.
- `python3 -m pytest`; keep `python3 scripts/card_schema.py` + `python3 -m pytest tests/test_engine_no_jay.py` green.
- End commits with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Do NOT touch `/Users/jayjenkins/pm-os`. Dev board only on `:8743`.

**Available composition pieces (from `registry.json`):**
- **signals**: `due, overdue, waiting_on, waiting_due, schedule, message, jira_draft, cron` (or `"auto"` for all-matching).
- **actions**: `mark_done, open_output, publish_jira, accept, reject, keep, undo, graduate`.
- **body**: `null`, or one of `diff`, `preview`, `agreement`.

---

## Task 1: `factory_lib.validate_card_type` + CLI + tests

A thin, testable gate for parity with `validate_worker`. Runs the full `card_schema` validation (token-only + every referenced signal/action/body-renderer must already exist — this is what enforces composition-only) and confirms the named type is present.

**Files:**
- Modify: `scripts/factory_lib.py` (add `validate_card_type` + a CLI subcommand)
- Test: `tests/test_factory_card_type.py` (create)

**Step 1: Write the failing test**

Create `tests/test_factory_card_type.py`:

```python
"""Phase 9 PR2 — factory_lib.validate_card_type: the registry-composition gate."""
import json
import pytest

# A registry that mirrors the real one's shape, with a known-good composed type.
_BASE = {
    "slotOrder": ["head", "title", "context", "signals", "body", "actions"],
    "signals": {"due": {"icon": "due", "variant": "due"},
                "cron": {"icon": "cron", "variant": "cron"}},
    "actions": {"mark_done": {"label": "Mark done", "handler": "quickDone", "primary": True},
                "keep": {"label": "Keep", "handler": "cardKeep", "primary": True},
                "undo": {"label": "Undo", "handler": "cardUndo"}},
    "cardTypes": {
        "task": {"signals": "auto", "actions": ["mark_done"], "body": None},
    },
}


def _write(tmp_path, reg):
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(reg))
    return str(p)


def test_validate_card_type_accepts_composed_entry(tmp_path):
    import factory_lib
    reg = json.loads(json.dumps(_BASE))
    reg["cardTypes"]["note"] = {"signals": [], "actions": ["mark_done"], "body": None}
    assert factory_lib.validate_card_type("note", registry_path=_write(tmp_path, reg)) == []


def test_validate_card_type_flags_unknown_signal(tmp_path):
    import factory_lib
    reg = json.loads(json.dumps(_BASE))
    reg["cardTypes"]["bad"] = {"signals": ["nonexistent"], "actions": ["mark_done"], "body": None}
    problems = factory_lib.validate_card_type("bad", registry_path=_write(tmp_path, reg))
    assert any("nonexistent" in p for p in problems)


def test_validate_card_type_flags_unknown_body_renderer(tmp_path):
    import factory_lib
    reg = json.loads(json.dumps(_BASE))
    reg["cardTypes"]["bad"] = {"signals": [], "actions": ["mark_done"], "body": "sparkly"}
    problems = factory_lib.validate_card_type("bad", registry_path=_write(tmp_path, reg))
    assert any("sparkly" in p for p in problems)


def test_validate_card_type_flags_missing_type(tmp_path):
    import factory_lib
    problems = factory_lib.validate_card_type("ghost", registry_path=_write(tmp_path, _BASE))
    assert any("ghost" in p and "not found" in p for p in problems)


def test_real_registry_passes_validate_card_type():
    """The live registry's existing 'task' type passes the gate unchanged."""
    import factory_lib
    assert factory_lib.validate_card_type("task") == []
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_factory_card_type.py -v`
Expected: FAIL — `AttributeError: module 'factory_lib' has no attribute 'validate_card_type'`.

**Step 3: Implement**

In `scripts/factory_lib.py`, add after `validate_worker`:

```python
def validate_card_type(name, registry_path=None):
    """Return a list of problems with a card type in the registry ([] = ok).

    Runs the full card-schema gate — token-only AND every referenced signal /
    action / body-renderer must already exist. That existence check is exactly
    what enforces 'registry-composition-only': a card type referencing a NEW
    signal/action/renderer (which would need JS) fails here. Also confirms the
    named type is present."""
    import json
    import card_schema
    path = registry_path or card_schema.REGISTRY
    with open(path, encoding="utf-8") as f:
        reg = json.load(f)
    errs = card_schema.validate_doc(
        reg, card_schema._declared_signal_ids(), card_schema._theme_tokens())
    if name not in reg.get("cardTypes", {}):
        errs.append(f"card type '{name}' not found in the registry")
    return errs
```

In the `__main__` CLI block, add a subcommand alongside `validate-worker`:

```python
    vc = sub.add_parser("validate-card-type")
    vc.add_argument("name")
```

and in the dispatch:

```python
    elif args.cmd == "validate-card-type":
        probs = validate_card_type(args.name)
        if probs:
            print("\n".join(probs)); sys.exit(1)
        print("ok")
```

**Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_factory_card_type.py -v`
Expected: PASS (5 tests). Also confirm the CLI: `python3 scripts/factory_lib.py validate-card-type task` → `ok`.

**Step 5: Commit**

```bash
git add scripts/factory_lib.py tests/test_factory_card_type.py
git commit -m "feat(factory): factory_lib.validate_card_type — the composition-only gate

Runs card_schema's token-only + reference-existence check (which rejects new
signals/actions/renderers) and confirms the named type exists. Parity with
validate_worker.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `meta-create-card-type` skill

**Files:**
- Create: `.claude/skills/meta-create-card-type/SKILL.md`
- Modify: `tests/test_factory_skills.py` (append tests)

**Step 1: Append the failing tests**

Append to `tests/test_factory_skills.py`:

```python
def test_meta_create_card_type_exists_and_frontmatter():
    body = _read(".claude/skills/meta-create-card-type/SKILL.md")
    assert body.startswith("---\n")
    fm = body.split("---\n", 2)[1]
    assert "name: meta-create-card-type" in fm
    assert "Use when" in fm
    assert "meta-factory-core" in body
    assert "factory_lib" in body
    assert "card_schema" in body
    assert "registry.json" in body
    # composition-only is explicit + the out-of-scope refusal is stated
    assert "composition" in body.lower()
    assert "zero new render code" in body or "no JS" in body or "no new JS" in body


def test_meta_create_card_type_lists_only_existing_pieces():
    """The skill must enumerate the real signals/actions/body-renderers so the
    agent composes from them and doesn't invent new ones."""
    body = _read(".claude/skills/meta-create-card-type/SKILL.md")
    for renderer in ("diff", "preview", "agreement"):
        assert renderer in body
    for action in ("mark_done", "accept", "keep", "undo", "graduate"):
        assert action in body
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_factory_skills.py -v`
Expected: FAIL — file not found.

**Step 3: Write the skill**

Create `.claude/skills/meta-create-card-type/SKILL.md` with EXACTLY this content:

```markdown
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
```

**Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_factory_skills.py -v` → PASS.
Run: `python3 -m pytest tests/test_engine_no_jay.py -v` → PASS (denylist-clean).

**Step 5: Commit**

```bash
git add .claude/skills/meta-create-card-type/SKILL.md tests/test_factory_skills.py
git commit -m "feat(factory): meta-create-card-type skill — compose a card type from existing pieces

Registry-composition-only (zero new render code); gates on validate-card-type +
card_schema.py; commits via factory_lib with a Keep/Undo receipt. New
signals/actions/renderers are explicitly out of scope (JS, hand to engineering).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Register `meta-create-card-type` in the `core` pack

**Files:**
- Modify: `.claude/packs.yaml` (add to `core.skills`)
- Modify: `tests/test_factory_skills.py` (extend the pack test)

**Step 1: Update the failing test**

Edit the existing `test_factory_skills_in_core_pack` in `tests/test_factory_skills.py` to also assert the new skill:

```python
def test_factory_skills_in_core_pack():
    from ruamel.yaml import YAML
    packs = YAML(typ="safe").load((REPO / ".claude/packs.yaml").read_text())
    core = packs["core"]["skills"]
    assert "meta-factory-core" in core
    assert "meta-create-worker" in core
    assert "meta-create-card-type" in core
```

(Note: the existing test already uses `ruamel.yaml` — PyYAML is not installed in this env. Keep the ruamel parser.)

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_factory_skills.py::test_factory_skills_in_core_pack -v`
Expected: FAIL.

**Step 3: Edit `.claude/packs.yaml`**

In the `core:` pack's `skills:` list, add after `- meta-create-worker`:

```yaml
    - meta-create-card-type
```

**Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_factory_skills.py tests/test_packs_lib.py -v` → all PASS.

**Step 5: Commit**

```bash
git add .claude/packs.yaml tests/test_factory_skills.py
git commit -m "feat(factory): register meta-create-card-type in core pack

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Full-suite green

**Step 1: Run the suite + both gates**

```bash
python3 -m pytest -q
python3 scripts/card_schema.py
python3 -m pytest tests/test_engine_no_jay.py -q
```
Expected: all green; pytest count = 237 + new tests (5 card_type + 2 skill structural).

**Step 2: Documentation-sync** — same finding as PR1: this repo has no hand-maintained skill index (auto-discovery), so it's a no-op. Confirm by checking the new skill auto-appears (it's a `.claude/skills/*/SKILL.md`). No doc edits expected.

**Step 3: Commit** any incidental changes (skip if none).

---

## Task 5: Live verification (Chrome — the design-system claim)

Prove the "zero new render code" claim: a composed card type renders on the real board with working actions, with no JS change. Then Undo to clean up.

**Step 1: No backend change in PR2 → no server restart needed.** `card-registry.js` fetches `/cardtypes/registry.json` at runtime, so a registry edit shows after a page reload. Confirm the dev board is up and is THIS repo:
```bash
PID=$(lsof -ti :8743 -sTCP:LISTEN); lsof -a -p $PID -d cwd -Fn | grep '^n'   # must be /Users/jayjenkins/dev/pm-os-team
```

**Step 2: Drive the factory.** Use the `meta-create-card-type` skill (or do it by hand following the skill) to add a throwaway composed type, e.g.:
```json
"note": { "signals": [], "actions": ["mark_done"], "body": null }
```
Run the gate (`validate-card-type note` + `card_schema.py`), then `factory_lib commit-and-receipt --kind card-type ui/task-board/cardtypes/registry.json`.

**Step 3: Verify the registry served + the gate.**
```bash
curl -s localhost:8743/cardtypes/registry.json | python3 -c "import sys,json; print('note' in json.load(sys.stdin)['cardTypes'])"   # True
python3 scripts/card_schema.py   # registry.json OK
```

**Step 4: Render proof (Chrome headless).** Seed a throwaway task with `card_type: note` in the human queue (a gitignored task file), reload the board, and screenshot/`--dump-dom` the human column. Confirm a card renders for that task with the `Mark done` button — i.e. `data-task-id` present and a `card-action` Mark done button, produced entirely by `renderCardFromRegistry` with no JS edit. (See `docs/plans` PR #12 lesson: verify the INTERACTION — confirm the rendered card exists in the DOM, not just that the file changed.)

**Step 5: Undo + clean up.** Hit the receipt's Undo (`POST /api/tasks/<receipt_id>/undo`) to git-revert the registry edit; confirm `note` is gone from the served registry. Remove the throwaway seeded task file. Drop the verification commits (`git reset --hard <pre-verification sha>`), leaving only the reviewed PR2 commits. `git status` clean.

---

## Done criteria for PR2

- [ ] `factory_lib.validate_card_type` + CLI + 5 tests green (Task 1).
- [ ] `meta-create-card-type` skill (composition-only, lists existing pieces, refuses new JS) + structural tests green, denylist-clean (Task 2).
- [ ] Skill in `core` pack (Task 3).
- [ ] Full suite + `card_schema.py` + `test_engine_no_jay.py` green (Task 4).
- [ ] Live proof: a composed card type renders on the board with working actions (zero JS), then Undo reverts the registry edit clean (Task 5).
- [ ] Open PR `feat/phase-9-factory-pr2-cardtype` → main with the two-stage review.
```
