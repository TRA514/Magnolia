# meta-create-adapter + Tier-2 publish gate — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the third factory sibling (`meta-create-adapter`) plus a general Tier-2 "confirm before first external write" gate on the adapter publish path, presented as a one-time `confirm` card on the collab queue.

**Architecture:** A loader wrapper `adapters.publish(family, draft)` checks a provider-level `confirmed` flag (grandfather-by-config) and raises a typed `NeedsConfirmation` before any external call; `handle_publish_jira` catches it and emits a `confirm` collab card whose Confirm action flips the flag and re-drives the blocked publish via a shared core. `meta-create-adapter` scaffolds `scripts/adapters/<family>/<provider>.py` from the `asana.py` exemplar and *arms* the gate by writing `confirmed: false` into `integrations.yaml`. Gate = `validate_adapter` (Protocol conformance, import-only). Guard = `test_engine_no_jay.py` extended to `scripts/adapters/`.

**Tech Stack:** Python 3 (bare Homebrew, PEP-668 → `pip install --break-system-packages` if needed), `pytest`, `ruamel.yaml`, stdlib `http.server`, vanilla JS board served by `task_server.py`.

**Design doc:** `docs/plans/2026-06-07-phase-9-factory-pr3-adapter-design.md`

**Standing rules (every task):**
- Branch is `feat/phase-9-factory-pr3-adapter` (already created off `main`). Never commit to `main`.
- Git author is set locally already. End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Keep green throughout: `python3 -m pytest`, `python3 scripts/card_schema.py`, `python3 -m pytest tests/test_engine_no_jay.py`.
- Run tests from the repo root: `cd /Users/jayjenkins/dev/pm-os-team`.
- `tests/conftest.py` provides `profile_root` (temp PM-OS root with jira **configured**: `provider: jira`, `cloud_id`, `project_key: ACM`, etc. — and **no** `confirmed` key) and `tasks_root` (temp task tree + seeded counter).

---

## Task 1: `profile_lib.set_integration_confirmed`

Provider-level setter for the Tier-2 consent flag, modelled on `set_integration_conventions` (preserves siblings + comments, creates the provider sub-block if absent).

**Files:**
- Modify: `scripts/profile_lib.py` (add after `set_integration_conventions`, ~line 267)
- Test: `tests/test_profile_confirmed.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_profile_confirmed.py
import profile_lib


def test_set_confirmed_false_creates_flag_and_preserves_siblings(profile_root):
    profile_lib.set_integration_confirmed("project_management", False, provider="jira", root=profile_root)
    block = profile_lib.integration("project_management", root=profile_root)["jira"]
    assert block["confirmed"] is False
    assert block["project_key"] == "ACM"          # sibling preserved


def test_set_confirmed_true_roundtrips(profile_root):
    profile_lib.set_integration_confirmed("project_management", True, provider="jira", root=profile_root)
    block = profile_lib.integration("project_management", root=profile_root)["jira"]
    assert block["confirmed"] is True


def test_set_confirmed_creates_provider_block_when_absent(profile_root):
    # 'linear' has no sub-block in the fixture — setter must create it.
    profile_lib.set_integration_confirmed("project_management", False, provider="linear", root=profile_root)
    block = profile_lib.integration("project_management", root=profile_root)
    assert block["linear"]["confirmed"] is False
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_profile_confirmed.py -q`
Expected: FAIL with `AttributeError: module 'profile_lib' has no attribute 'set_integration_confirmed'`.

**Step 3: Write minimal implementation**

```python
# scripts/profile_lib.py — add after set_integration_conventions
def set_integration_confirmed(category, confirmed, provider=None, root=None):
    """Set the Tier-2 consent flag integrations.yaml[category][provider]['confirmed'].

    'confirmed' records that the operator okayed this integration to write to the
    OUTSIDE WORLD. With provider given, nests under <category>.<provider>.confirmed
    (creating the sub-block if absent); otherwise <category>.confirmed. Siblings +
    comments are preserved."""
    def mutate(doc):
        cat = doc.get(category)
        if not isinstance(cat, dict):
            cat = {}
            doc[category] = cat
        target = cat
        if provider:
            sub = cat.get(provider)
            if not isinstance(sub, dict):
                sub = {}
                cat[provider] = sub
            target = sub
        target["confirmed"] = bool(confirmed)
    _update_yaml("integrations.yaml", mutate, root)
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_profile_confirmed.py -q`
Expected: PASS (3 passed).

**Step 5: Commit**

```bash
git add scripts/profile_lib.py tests/test_profile_confirmed.py
git commit -m "feat(profile): set_integration_confirmed — provider-level Tier-2 consent flag

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `adapters.publish` gate + `NeedsConfirmation` + `_is_confirmed`

The general Tier-2 gate. Lives in the loader so every adapter inherits it for free.

**Files:**
- Modify: `scripts/adapters/__init__.py`
- Test: `tests/test_adapter_gate.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_adapter_gate.py
import pytest
import adapters
from adapters.project_management import jira as jira_adapter


def _no_provider_root(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text(
        "project_management:\n  provider: none\n")
    return str(tmp_path)


def test_publish_returns_none_when_no_provider(tmp_path):
    assert adapters.publish("project_management", {"summary": "x"},
                            root=_no_provider_root(tmp_path)) is None


def test_publish_raises_needs_confirmation_when_explicitly_unconfirmed(profile_root):
    import profile_lib
    profile_lib.set_integration_confirmed("project_management", False, provider="jira", root=profile_root)
    with pytest.raises(adapters.NeedsConfirmation):
        adapters.publish("project_management", {"summary": "x", "type": "Bug"}, root=profile_root)


def test_publish_passes_when_confirmed(profile_root, monkeypatch):
    import profile_lib, jira_publish
    profile_lib.set_integration_confirmed("project_management", True, provider="jira", root=profile_root)
    monkeypatch.setattr(jira_publish, "publish_to_jira", lambda d: ("ACM-2", "u"))
    assert adapters.publish("project_management", {"summary": "x"}, root=profile_root) == ("ACM-2", "u")


def test_publish_grandfathers_configured_without_flag(profile_root, monkeypatch):
    # profile_root has jira creds but NO confirmed key -> grandfathered (creds = consent).
    import jira_publish
    monkeypatch.setattr(jira_publish, "publish_to_jira", lambda d: ("ACM-3", "u"))
    assert adapters.publish("project_management", {"summary": "x"}, root=profile_root) == ("ACM-3", "u")


def test_is_confirmed_explicit_false_blocks_even_if_configured(profile_root):
    import profile_lib
    profile_lib.set_integration_confirmed("project_management", False, provider="jira", root=profile_root)
    assert adapters._is_confirmed("project_management", jira_adapter, root=profile_root) is False
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_adapter_gate.py -q`
Expected: FAIL with `AttributeError: module 'adapters' has no attribute 'publish'` (and `NeedsConfirmation`).

**Step 3: Write minimal implementation**

```python
# scripts/adapters/__init__.py — add below get()
class NeedsConfirmation(RuntimeError):
    """Raised when publish() is attempted but the integration has not been
    confirmed for external writes (Tier-2). Stops BEFORE any external call so a
    one-time plain-language confirm can be surfaced. Carries the family so the
    caller can build the confirm card."""

    def __init__(self, family):
        self.family = family
        super().__init__(
            f"{family} integration needs a one-time confirm before its first external write")


def _is_confirmed(family, mod, root=None):
    """Tier-2 consent check for the family's active provider.

    An explicit `confirmed` flag in integrations.yaml wins (False blocks). When the
    flag is ABSENT, an integration the operator configured creds for is treated as
    self-confirmed (grandfather-by-config) so a live install is never retroactively
    blocked; the factory arms the gate by writing an explicit confirmed: false."""
    provider = profile_lib.provider(family, root)
    block = profile_lib.integration(family, root).get(provider) or {}
    if "confirmed" in block:
        return bool(block["confirmed"])
    return bool(mod.is_configured(root))


def publish(family, draft, root=None):
    """Tier-2 gated publish. Returns None when no provider is configured (caller
    degrades gracefully); raises NeedsConfirmation when configured-but-unconfirmed
    (no external call is made); otherwise delegates to the provider adapter."""
    mod = get(family, root)
    if mod is None:
        return None
    if not _is_confirmed(family, mod, root):
        raise NeedsConfirmation(family)
    return mod.publish(draft, root)
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_adapter_gate.py tests/test_adapters.py -q`
Expected: PASS (all green — existing adapter tests still pass).

**Step 5: Commit**

```bash
git add scripts/adapters/__init__.py tests/test_adapter_gate.py
git commit -m "feat(adapters): Tier-2 publish gate — NeedsConfirmation + grandfather-by-config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `factory_lib.validate_adapter` (Protocol conformance) + CLI

The adapter's gate (the GREEN before commit). Import-only; never calls `publish()`, so no creds. Split a pure `_conformance_problems(mod, proto)` so failure modes test cleanly without import gymnastics.

**Files:**
- Modify: `scripts/factory_lib.py` (add `validate_adapter`, `_conformance_problems`, `_protocol_in`; add `validate-adapter` subparser)
- Test: `tests/test_validate_adapter.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_validate_adapter.py
import types
import factory_lib
from adapters.project_management._contract import ProjectManagementAdapter


def test_real_asana_conforms():
    assert factory_lib.validate_adapter("project_management", "asana") == []


def test_missing_publish_is_flagged():
    fake = types.SimpleNamespace(is_configured=lambda root=None: True)
    probs = factory_lib._conformance_problems(fake, ProjectManagementAdapter)
    assert any("publish" in p for p in probs)


def test_wrong_signature_is_flagged():
    fake = types.SimpleNamespace(
        is_configured=lambda root=None: True,
        publish=lambda x: ("K", "U"),          # missing draft/root param names
    )
    probs = factory_lib._conformance_problems(fake, ProjectManagementAdapter)
    assert any("draft" in p or "root" in p for p in probs)


def test_import_error_is_flagged():
    probs = factory_lib.validate_adapter("project_management", "does_not_exist")
    assert any("import failed" in p for p in probs)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_validate_adapter.py -q`
Expected: FAIL with `AttributeError: module 'factory_lib' has no attribute 'validate_adapter'`.

**Step 3: Write minimal implementation**

```python
# scripts/factory_lib.py — add near validate_card_type
def _protocol_in(contract_module):
    """Return the typing.Protocol subclass defined in a family's _contract module."""
    import inspect
    for _, obj in inspect.getmembers(contract_module, inspect.isclass):
        if getattr(obj, "_is_protocol", False) and obj.__module__ == contract_module.__name__:
            return obj
    return None


def _conformance_problems(mod, proto):
    """Return a list of ways `mod` fails to satisfy Protocol `proto` ([] = ok).

    Pure interface check: every public Protocol method must be present, callable,
    and expose the Protocol's parameter names. Never invokes the methods."""
    import inspect
    problems = []
    for name, _ in inspect.getmembers(proto, callable):
        if name.startswith("_"):
            continue
        fn = getattr(mod, name, None)
        if not callable(fn):
            problems.append(f"missing or non-callable method: {name}")
            continue
        want = [p for p in inspect.signature(getattr(proto, name)).parameters if p != "self"]
        have = list(inspect.signature(fn).parameters)
        for p in want:
            if p not in have:
                problems.append(f"{name}() missing expected parameter '{p}'")
    return problems


def validate_adapter(family, provider, root=None):
    """Return a list of conformance problems for a scaffolded adapter ([] = ok).

    Imports the family's _contract Protocol and the scaffolded module and checks
    interface conformance. Import-only — does NOT call publish()/sync(), so no
    external creds are needed. The import itself is part of the gate (syntax +
    resolvable imports)."""
    import importlib
    scripts_dir = os.path.join(root, "scripts") if root else SCRIPT_DIR
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        contract = importlib.import_module(f"adapters.{family}._contract")
    except Exception as e:
        return [f"could not import contract for family '{family}': {e}"]
    proto = _protocol_in(contract)
    if proto is None:
        return [f"no Protocol found in adapters.{family}._contract"]
    try:
        mod = importlib.import_module(f"adapters.{family}.{provider}")
    except Exception as e:
        return [f"adapter import failed: {e}"]
    return _conformance_problems(mod, proto)
```

Add the CLI subcommand inside `if __name__ == "__main__":` (next to `validate-card-type`):

```python
    va = sub.add_parser("validate-adapter")
    va.add_argument("family")
    va.add_argument("provider")
```

and in the dispatch chain:

```python
    elif args.cmd == "validate-adapter":
        probs = validate_adapter(args.family, args.provider)
        if probs:
            print("\n".join(probs)); sys.exit(1)
        print("ok")
```

**Step 4: Run tests + CLI to verify**

Run: `python3 -m pytest tests/test_validate_adapter.py -q`
Expected: PASS (4 passed).

Run: `python3 scripts/factory_lib.py validate-adapter project_management asana`
Expected: prints `ok`, exit 0.

**Step 5: Commit**

```bash
git add scripts/factory_lib.py tests/test_validate_adapter.py
git commit -m "feat(factory): validate_adapter — Protocol-conformance gate (import-only, cred-free)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Tier-2 confirm card — backend (`_attempt_publish`, `_emit_confirm_card`, `handle_confirm`), route, registry, JS

This task wires the publish path through the gate and the confirm round-trip. Unit-test the testable cores (`_attempt_publish`, `_emit_confirm_card`); the full HTTP route is exercised by the live e2e in Task 6.

**Files:**
- Modify: `scripts/task_server.py` (refactor `handle_publish_jira`; add `_attempt_publish`, `_emit_confirm_card`, `handle_confirm`; add `confirm` to `_card_handlers` + its route regex; ensure `from adapters import NeedsConfirmation` and `NotConfigured` are importable)
- Modify: `ui/task-board/cardtypes/registry.json` (add `confirm` action + `confirm` card type)
- Modify: `ui/task-board/js/card-registry.js` (`_renderActions`: add a `confirm` branch)
- Test: `tests/test_publish_core.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_publish_core.py
import importlib
import pytest


@pytest.fixture
def srv(tasks_root, profile_root, monkeypatch):
    """task_server with task_lib pointed at the temp task tree and profile at profile_root."""
    import task_server, adapters, profile_lib
    # Pin profile reads to profile_root for the duration of the test.
    for fn in ("provider", "integration"):
        orig = getattr(profile_lib, fn)
        monkeypatch.setattr(profile_lib, fn, lambda *a, _o=orig, **k: _o(*a, **{**k, "root": profile_root}))
    return task_server


def test_attempt_publish_needs_confirm_when_unconfirmed(srv, profile_root, monkeypatch):
    import profile_lib, adapters
    profile_lib.set_integration_confirmed("project_management", False, provider="jira", root=profile_root)
    monkeypatch.setattr(adapters, "publish",
                        lambda *a, **k: (_ for _ in ()).throw(adapters.NeedsConfirmation("project_management")))
    status, payload = srv._attempt_publish("TASK-0001", {"summary": "x"})
    assert status == "needs_confirm"


def test_attempt_publish_ok_records_and_returns_keypair(srv, monkeypatch):
    import adapters
    monkeypatch.setattr(adapters, "publish", lambda *a, **k: ("ACM-9", "https://x/ACM-9"))
    # create a real task to record onto
    import task_lib
    tid, _ = task_lib.create_task("draft", queue="human", domain="ops", creator="agent")
    status, payload = srv._attempt_publish(tid, {"summary": "x"})
    assert status == "ok" and payload == ("ACM-9", "https://x/ACM-9")


def test_emit_confirm_card_lands_on_collab_with_links(srv):
    import task_lib
    cid = srv._emit_confirm_card("project_management", "TASK-0042")
    card = task_lib.read_task(cid)
    assert card["card_type"] == "confirm"
    assert card["queue"] == "collab"
    assert card["confirm_family"] == "project_management"
    assert card["confirm_source_task"] == "TASK-0042"
```

> Note: if `create_task` raises `FileNotFoundError` on `_counter`, bootstrap it — see Task 6's gotcha. The `tasks_root` fixture seeds the counter, so this should not occur in tests.

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_publish_core.py -q`
Expected: FAIL (`_attempt_publish` / `_emit_confirm_card` not defined).

**Step 3: Write minimal implementation**

In `scripts/task_server.py`, ensure the imports expose the gate types (near the existing `import adapters` / `from adapters... import NotConfigured`):

```python
import adapters
from adapters import NeedsConfirmation
from adapters.project_management._contract import NotConfigured
```

Add the shared core + helpers (place them just above `handle_publish_jira`):

```python
def _note(task_id, msg):
    try:
        task_lib.update_task(task_id, changes={}, comment=msg, actor="system")
    except Exception:
        pass


def _attempt_publish(task_id, draft):
    """Shared publish core for the publish-jira and confirm handlers.

    Returns (status, payload):
      ("needs_confirm", None)             — Tier-2 gate fired; no external call made
      ("unconfigured", (400, msg))        — no provider configured
      ("error",       (code, msg))        — NotConfigured -> 400, RuntimeError -> 500
      ("ok",          (issue_key, url))   — published; task marked done + traced
    Records the outcome (task comment + LangFuse trace) for every terminal status."""
    if draft is None:
        return ("error", (400, "No JIRA_DRAFT block found in task body"))
    try:
        result = adapters.publish("project_management", draft)
    except NeedsConfirmation:
        return ("needs_confirm", None)
    except NotConfigured as e:
        _note(task_id, f"Jira publish failed: {e}")
        jira_publish._trace_publish(task_id, draft, error=str(e))
        return ("error", (400, str(e)))
    except RuntimeError as e:
        _note(task_id, f"Jira publish failed: {e}")
        jira_publish._trace_publish(task_id, draft, error=str(e))
        return ("error", (500, f"Jira publish failed: {e}"))
    if result is None:
        msg = "No project-management tool is configured for this install"
        _note(task_id, f"Jira publish failed: {msg}")
        jira_publish._trace_publish(task_id, draft, error=msg)
        return ("unconfigured", (400, msg))
    issue_key, issue_url = result
    output_str = f"Created {issue_key}: {issue_url}"
    try:
        task_lib.update_task(task_id, changes={"agent_output": output_str},
                             comment=f"Published to Jira: {output_str}", actor="system")
        task_lib.complete_task(task_id, actor="system")
    except Exception:
        pass
    jira_publish._trace_publish(task_id, draft, issue_key=issue_key, issue_url=issue_url)
    return ("ok", (issue_key, issue_url))


def _emit_confirm_card(family, source_task):
    """Write a Tier-2 confirm card to the collab queue. Confirm flips consent and
    re-drives source_task; Reject holds off. Carries the link fields handle_confirm reads."""
    provider = (profile_lib.provider(family) or "").title() or "your tool"
    summary = f"Okay to let this assistant post to your {provider}?"
    cid, _ = task_lib.create_task(
        summary, queue="collab", domain="ops", creator="agent",
        description=(f"This is the first time it will write to your {provider}. "
                     "Confirm to allow it from now on, or Reject to hold off."),
        card_type="confirm")
    task_lib.update_task(cid, changes={
        "confirm_family": family,
        "confirm_source_task": source_task,
        "receipt_summary": summary,   # the `preview` body renderer reads this
    })
    return cid
```

Rewrite `handle_publish_jira` to use the core:

```python
def handle_publish_jira(handler, task_id):
    """POST /api/tasks/{id}/publish-jira — publish a Jira draft (Tier-2 gated)."""
    try:
        task_data = task_lib.read_task(task_id)
    except FileNotFoundError:
        _error_response(handler, f"Task {task_id} not found", status=404)
        return
    draft = jira_publish.parse_jira_draft(task_data.get("body", ""))
    status, payload = _attempt_publish(task_id, draft)
    if status == "needs_confirm":
        cid = _emit_confirm_card("project_management", task_id)
        _json_response(handler, {
            "status": "needs_confirmation",
            "confirm_task": cid,
            "message": "First external write needs a one-time confirm — see the collab queue.",
        })
        return
    if status == "ok":
        issue_key, issue_url = payload
        _json_response(handler, {
            "status": "ok",
            "message": f"Published to Jira: {issue_key}",
            "issue_key": issue_key, "issue_url": issue_url,
        })
        return
    code, msg = payload
    _error_response(handler, msg, status=code)
```

Add `handle_confirm`:

```python
def handle_confirm(handler, task_id):
    """POST /api/tasks/{id}/confirm — Tier-2: record consent for an integration's
    first external write, then re-drive the blocked publish."""
    try:
        card = task_lib.read_task(task_id)
    except FileNotFoundError:
        _error_response(handler, f"Task {task_id} not found", status=404)
        return
    family = card.get("confirm_family")
    source_task = card.get("confirm_source_task")
    if not family or not source_task:
        _error_response(handler, "Confirm card missing confirm_family/confirm_source_task", status=400)
        return
    provider = profile_lib.provider(family)
    try:
        profile_lib.set_integration_confirmed(family, True, provider=provider)
    except Exception as e:
        _error_response(handler, f"Could not record confirmation: {e}", status=500)
        return
    try:
        src = task_lib.read_task(source_task)
    except FileNotFoundError:
        task_lib.complete_task(task_id, actor="human")
        _json_response(handler, {"ok": True, "note": "confirmed; source draft no longer exists"})
        return
    draft = jira_publish.parse_jira_draft(src.get("body", ""))
    status, payload = _attempt_publish(source_task, draft)
    if status != "ok":
        # Consent is recorded; surface the publish problem but leave the confirm card.
        code, msg = payload if isinstance(payload, tuple) else (500, "publish failed")
        _error_response(handler, msg, status=code)
        return
    task_lib.complete_task(task_id, actor="human")
    issue_key, issue_url = payload
    _json_response(handler, {"ok": True, "issue_key": issue_key, "issue_url": issue_url})
```

Wire the route — add `confirm` to the card-action map + regex (~line 1834):

```python
        _card_handlers = {
            "accept": handle_accept, "reject": handle_reject,
            "graduate": handle_graduate, "keep": handle_keep, "undo": handle_undo,
            "confirm": handle_confirm,
        }
        match = re.match(r"^/api/tasks/([^/]+)/(accept|reject|graduate|keep|undo|confirm)$", path)
```

Registry — `ui/task-board/cardtypes/registry.json`: add to `actions`:

```json
    "confirm": { "label": "Confirm", "handler": "cardConfirm", "primary": true }
```

and to `cardTypes`:

```json
    "confirm": { "signals": [], "actions": ["confirm", "reject"], "body": "preview" }
```

JS — `ui/task-board/js/card-registry.js`, in `_renderActions`, add a branch (after the `undo` branch, before the closing `}`):

```javascript
    } else if (id === 'confirm') {
      parts.push(`<button class="card-action primary" onclick="cardAction('${task.id}','confirm',event)">${svgIcon('done')}Confirm</button>`);
    }
```

(`cardAction(id, verb, event)` is the generic POST-to-`/api/tasks/{id}/{verb}` helper; `reject` already renders. No bespoke JS function needed.)

**Step 4: Run tests + gates**

Run: `python3 -m pytest tests/test_publish_core.py -q`
Expected: PASS (3 passed).

Run: `python3 scripts/card_schema.py`
Expected: prints ok / exit 0 (the `confirm` action + card type reference only existing `preview` body + `reject`).

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import factory_lib; print(factory_lib.validate_card_type('confirm'))"`
Expected: `[]`.

Run: `python3 -m pytest -q`
Expected: full suite green.

**Step 5: Commit**

```bash
git add scripts/task_server.py ui/task-board/cardtypes/registry.json ui/task-board/js/card-registry.js tests/test_publish_core.py
git commit -m "feat(tier2): confirm card + gated publish path with shared re-drive core

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `meta-create-adapter` skill + pack registration

The third factory sibling. Mirror `meta-create-worker`'s structure. The embedded skeleton is the `asana.py`-shaped contract-conformant stub (profile-driven, denylist-clean). The skill *arms the gate*: writes `confirmed: false` into `integrations.yaml` via `set_integration_confirmed`, and the receipt covers both files.

**Files:**
- Create: `.claude/skills/meta-create-adapter/SKILL.md`
- Modify: `.claude/packs.yaml` (add `meta-create-adapter` to the `core` pack's `skills:`)
- Test: none new (guarded by Task 6's extended `test_engine_no_jay`; structurally validated by reading)

**Step 1: Write the skill**

```markdown
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
```

**Step 2: Register in the core pack**

In `.claude/packs.yaml`, add `meta-create-adapter` to the `core` pack's `skills:` list, alongside `meta-create-worker` and `meta-create-card-type`. (Read the file first; match the existing list style/indentation exactly.)

**Step 3: Verify the skill is discoverable + denylist-clean**

Run: `python3 -m pytest tests/test_engine_no_jay.py -q`
Expected: PASS (the skeleton uses placeholders + "the operator" + profile-read prose).

Run: `python3 -c "import yaml; d=yaml.safe_load(open('.claude/packs.yaml')); assert 'meta-create-adapter' in d['packs']['core']['skills'], d['packs']['core']['skills']; print('registered')"`
Expected: prints `registered`. (Adjust the key path to match the actual `packs.yaml` shape verified in Step 2.)

**Step 4: Commit**

```bash
git add .claude/skills/meta-create-adapter/SKILL.md .claude/packs.yaml
git commit -m "feat(factory): meta-create-adapter skill — scaffold an adapter, arm the Tier-2 confirm

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Extend the denylist guard + full-suite green + live e2e

**Files:**
- Modify: `tests/test_engine_no_jay.py` (extend `TARGETS` with `scripts/adapters/**/*.py`)

**Step 1: Verify existing adapter code already passes the denylist (before extending)**

Run:
```bash
grep -rniE "\bjay\b|jay-voice|712020:aeec48b7-3829-433b-9125-c8c2a4c84e6f|board 1096|~/pm-os|/Users/" scripts/adapters --include=*.py || echo "CLEAN"
```
Expected: `CLEAN`. If anything matches, STOP — it is either a real leak to fix in that adapter file or a scoping decision to raise with the operator before extending the guard.

**Step 2: Write the failing test (extend the glob)**

Edit `tests/test_engine_no_jay.py`:

```python
TARGETS = (
    glob.glob(os.path.join(ROOT, "scripts", "workers", "*.md")) +
    glob.glob(os.path.join(ROOT, ".claude", "skills", "**", "*.md"), recursive=True) +
    glob.glob(os.path.join(ROOT, ".claude", "commands", "*.md")) +
    glob.glob(os.path.join(ROOT, "scripts", "adapters", "**", "*.py"), recursive=True)
)
```

**Step 3: Run the guard**

Run: `python3 -m pytest tests/test_engine_no_jay.py -q`
Expected: PASS (both `test_no_per_person...` and `test_vantaca_still_allowed` — Vantaca still appears in skills text).

**Step 4: Full suite + all gates green**

Run:
```bash
python3 -m pytest -q
python3 scripts/card_schema.py
```
Expected: all green; the prior baseline (245 passing) plus the new tests.

**Step 5: Live e2e — the confirm round-trip through the real HTTP handlers**

This is mandatory (units miss the interaction). Stub the actual Jira call so **no real ticket is created**.

1. **Restart the dev board on :8743** (PR3 changed `task_server`/`adapters`):
   ```bash
   lsof -ti :8743 -sTCP:LISTEN   # find the listener
   # Confirm its cwd is THIS repo (/Users/jayjenkins/dev/pm-os-team) before killing:
   #   lsof -p <pid> | grep cwd
   kill <pid>
   cd /Users/jayjenkins/dev/pm-os-team
   nohup python3 scripts/task_server.py > logs/devserver.log 2>&1 &
   ```
   > Do NOT touch :8742 — that is the separate PRODUCTION board.

2. **Seed a configured-but-unconfirmed integration + a throwaway draft.** Set the dev profile's `project_management` to `provider: jira` with a `cloud_id`/`project_key` and `jira.confirmed: false` (use `profile_lib.set_integration_confirmed('project_management', False, provider='jira')`). Stub the external call for the test by monkeypatching/temporarily editing `jira_publish.publish_to_jira` to return a fake `("DEV-1","https://example/DEV-1")` — OR point the adapter at a provider whose `publish` returns a fake. Seed a gitignored throwaway task on the human queue with a `JIRA_DRAFT` block in its body. If `create_task` raises `FileNotFoundError` on `datasets/tasks/_counter`, bootstrap it: `echo <N> > datasets/tasks/_counter` where N is above the current global max task id.

3. **Trigger the blocked publish:**
   ```bash
   curl -s -X POST http://localhost:8743/api/tasks/<DRAFT_ID>/publish-jira
   ```
   Expected JSON: `{"status":"needs_confirmation","confirm_task":"<CID>", ...}`. Assert **no ticket was created** (the stub was not called, or the trace shows no success). A `confirm` card now exists on the collab queue.

4. **Verify the card renders** (Chrome headless):
   ```bash
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
     --headless=new --virtual-time-budget=4500 --dump-dom http://localhost:8743/ \
     | grep -i "Confirm\|post to your"
   ```
   Expected: the confirm card markup with a Confirm action is present.

5. **Confirm → flag flips + publish re-drives:**
   ```bash
   curl -s -X POST http://localhost:8743/api/tasks/<CID>/confirm
   ```
   Expected JSON: `{"ok":true,"issue_key":"DEV-1","issue_url":"https://example/DEV-1"}`. Assert `integrations.yaml` now has `jira.confirmed: true`, the source draft task is marked published with the link, and the confirm card is completed.

6. **Second publish flows straight through** (now confirmed) — seed another draft, POST publish-jira, expect `status: ok` with no confirm card.

7. **Clean up** the throwaway tasks and revert any temporary stub edit to `jira_publish.py`. Restore the dev profile's `confirmed`/provider to its pre-test state if you changed real profile files (or do the whole e2e against a temp profile root if cleaner).

Record the actual curl outputs in your completion notes (evidence before assertions).

**Step 6: Commit**

```bash
git add tests/test_engine_no_jay.py
git commit -m "test(guard): extend denylist guard to scripts/adapters/**

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Done criteria

- `python3 -m pytest` green (baseline + new tests for the setter, the gate, `validate_adapter`, the publish core).
- `python3 scripts/card_schema.py` green; `factory_lib.validate_card_type('confirm') == []`.
- `python3 -m pytest tests/test_engine_no_jay.py` green with adapters now scanned.
- `python3 scripts/factory_lib.py validate-adapter project_management asana` → `ok`.
- Live e2e confirm round-trip verified through :8743 with no real external write.
- `meta-create-adapter` registered in the `core` pack and discoverable.

## Finishing

After all tasks pass and the e2e is verified, use **superpowers:finishing-a-development-branch**: open the PR with `gh pr create --base main` (title `feat(factory): meta-create-adapter + Tier-2 publish gate`, body summarizing the six locked decisions and linking the design doc). After this merges, Phase 9 — and the whole build sequence — is complete.
