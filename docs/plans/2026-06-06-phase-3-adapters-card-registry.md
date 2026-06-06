# Phase 3 — Adapters + Declarative Card Registry — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make project-management (Jira) and transcript (Otter) integrations pluggable behind a single module-per-provider interface, replace hardcoded card rendering with a declarative JSON card registry guarded by a tested Python validator, and migrate Pendo/Databricks facts into the profile — closing the matching Phase-2 residuals.

**Architecture:** A tiny loader maps `profile_lib.provider(family)` → an adapter module under `scripts/adapters/<family>/<provider>.py`; `jira_publish.py` and `transcript_sync.py` become thin shims over it. The card design system becomes data in `ui/task-board/cardtypes/registry.json` (served statically, read by both the JS renderer and a Python validator). Signal trigger conditions stay as one-line JS predicates keyed by id — no DSL.

**Tech Stack:** Bare Homebrew `python3` (PEP-668: `pip install --break-system-packages`), `pytest`, `ruamel.yaml`, vanilla browser JS (no build, no JS test harness), `typing.Protocol` for adapter contracts.

**Conventions:**
- Tests run `python3 -m pytest` from repo root. Reuse `tests/conftest.py::profile_root`.
- Every commit message ends with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Branch: `feat/phase-3-adapters-card-registry` (already created off `main`).
- NEVER touch `/Users/jayjenkins/pm-os` (separate production system).
- Skills must stay **dual-context** (work under task-board dispatch AND a bare interactive terminal session) and **degrade gracefully** when a provider is `none`.

---

## Task 1: Project-management adapter — contract + loader + Jira port

**Files:**
- Create: `scripts/adapters/__init__.py`
- Create: `scripts/adapters/project_management/__init__.py`
- Create: `scripts/adapters/project_management/_contract.py`
- Create: `scripts/adapters/project_management/jira.py`
- Modify: `scripts/jira_publish.py` (delegate publish to the adapter)
- Test: `tests/test_adapters.py`

**Step 1: Write the failing test**

```python
# tests/test_adapters.py
import pytest
import adapters
from adapters.project_management import jira as jira_adapter


def test_loader_returns_jira_module_for_jira_provider(profile_root):
    mod = adapters.get("project_management", root=profile_root)
    assert mod is jira_adapter


def test_loader_returns_none_when_provider_none(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text(
        "project_management:\n  provider: none\n")
    assert adapters.get("project_management", root=str(tmp_path)) is None


def test_jira_is_configured_true_for_populated_profile(profile_root):
    assert jira_adapter.is_configured(root=profile_root) is True


def test_jira_publish_delegates_to_publish_to_jira(profile_root, monkeypatch):
    captured = {}
    def fake_publish(draft):
        captured["draft"] = draft
        return ("ACM-1", "https://acme.atlassian.net/browse/ACM-1")
    import jira_publish
    monkeypatch.setattr(jira_publish, "publish_to_jira", fake_publish)
    key, url = jira_adapter.publish({"summary": "x", "type": "Bug"}, root=profile_root)
    assert key == "ACM-1"
    assert captured["draft"]["summary"] == "x"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_adapters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters'`

**Step 3: Write minimal implementation**

```python
# scripts/adapters/__init__.py
"""Adapter loader: maps a profile integration family to its provider module.

Each family lives under scripts/adapters/<family>/ with one module per provider
(<provider>.py) conforming to that family's _contract.py Protocol. The loader is
the ONLY place that knows provider-name -> module; adding a provider = drop a
module in and select it in the profile. Calendar/doc_sync generalize to the same
shape when their turn comes.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402


def get(family, root=None):
    """Return the adapter module for the family's active provider, or None."""
    provider = profile_lib.provider(family, root)
    if provider == "none":
        return None
    try:
        return importlib.import_module(f"adapters.{family}.{provider}")
    except ModuleNotFoundError:
        return None
```

```python
# scripts/adapters/project_management/__init__.py
"""project-management adapters: push work OUT to the team's system of record."""
```

```python
# scripts/adapters/project_management/_contract.py
"""Contract every project-management adapter must satisfy (legibility only)."""
from typing import Protocol


class NotConfigured(RuntimeError):
    """Raised when publish() is called but the provider/profile isn't set up."""


class ProjectManagementAdapter(Protocol):
    def is_configured(self, root=None) -> bool: ...
    def publish(self, draft: dict, root=None) -> tuple: ...  # -> (issue_key, issue_url)
```

```python
# scripts/adapters/project_management/jira.py
"""Jira project-management adapter. Wraps the existing jira_publish helpers."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import profile_lib  # noqa: E402
import jira_publish  # noqa: E402
from adapters.project_management._contract import NotConfigured  # noqa: E402


def is_configured(root=None) -> bool:
    cfg = profile_lib.jira_config(root)
    return bool(cfg.get("cloud_id") and cfg.get("project_key"))


def publish(draft, root=None):
    if not is_configured(root):
        raise NotConfigured("Jira is not configured in this profile")
    return jira_publish.publish_to_jira(draft)
```

Then make `jira_publish.publish_to_jira` the implementation the adapter calls (it already exists — no change needed beyond confirming the import path). Leave `jira_publish.py`'s CLI and parsing intact.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_adapters.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add scripts/adapters/__init__.py scripts/adapters/project_management/ tests/test_adapters.py
git commit -m "feat(adapters): project-management loader + Jira adapter over jira_publish"
```

---

## Task 2: Asana drop-in stub

**Files:**
- Create: `scripts/adapters/project_management/asana.py`
- Test: `tests/test_adapters.py` (append)

**Step 1: Write the failing test**

```python
def test_asana_stub_is_not_configured(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text(
        "project_management:\n  provider: asana\n")
    from adapters.project_management import asana
    assert asana.is_configured(root=str(tmp_path)) is False


def test_asana_publish_raises_not_configured(tmp_path):
    from adapters.project_management import asana
    from adapters.project_management._contract import NotConfigured
    with pytest.raises(NotConfigured):
        asana.publish({"summary": "x"}, root=str(tmp_path))
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_adapters.py -k asana -v`
Expected: FAIL — `ImportError: cannot import name 'asana'`

**Step 3: Write minimal implementation**

```python
# scripts/adapters/project_management/asana.py
"""Asana adapter — documented drop-in stub.

The seam is wired: select provider "asana" in integrations.yaml and the loader
finds this module. To make it real, implement publish() against the Asana MCP
(mirror jira.py: read profile_lib config, push a draft, return (id, url)) and
flip is_configured() to check the profile. Until then it degrades gracefully.
"""
from adapters.project_management._contract import NotConfigured


def is_configured(root=None) -> bool:
    return False


def publish(draft, root=None):
    raise NotConfigured(
        "Asana adapter is a stub — implement publish() against the Asana MCP")
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_adapters.py -k asana -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/adapters/project_management/asana.py tests/test_adapters.py
git commit -m "feat(adapters): Asana drop-in stub conforming to the contract"
```

---

## Task 3: Transcript adapter — contract + loader + Otter/Granola behind the loader

**Files:**
- Create: `scripts/adapters/transcript/__init__.py`
- Create: `scripts/adapters/transcript/_contract.py`
- Create: `scripts/adapters/transcript/otter.py`
- Create: `scripts/adapters/transcript/granola.py`
- Modify: `scripts/transcript_sync.py` (dispatch via loader; keep `sync(root)` public + the otter single-install note)
- Test: `tests/test_adapters.py` (append) — and existing `tests/test_transcript_sync.py` must still pass unchanged

**Step 1: Write the failing test**

```python
def test_transcript_loader_dispatches_otter(profile_root, monkeypatch):
    # profile_root uses transcript provider "granola"; override to otter here
    import profile_lib
    monkeypatch.setattr(profile_lib, "provider", lambda fam, root=None: "otter")
    mod = adapters.get("transcript", root=profile_root)
    from adapters.transcript import otter
    assert mod is otter


def test_granola_sync_reports_unsupported(tmp_path):
    from adapters.transcript import granola
    result = granola.sync(root=str(tmp_path))
    assert result["status"] == "unsupported"
    assert result["provider"] == "granola"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_adapters.py -k transcript -v`
Expected: FAIL — module/import errors

**Step 3: Write minimal implementation**

```python
# scripts/adapters/transcript/__init__.py
"""transcript adapters: how meeting transcripts arrive + trigger extraction."""
```

```python
# scripts/adapters/transcript/_contract.py
"""Contract every transcript adapter must satisfy (legibility only)."""
from typing import Protocol


class TranscriptAdapter(Protocol):
    # status in {ok, skipped, error, unsupported}
    def sync(self, root=None) -> dict: ...
```

```python
# scripts/adapters/transcript/otter.py
"""Otter transcript adapter.

NOTE (single-install): the ported otter_sync resolves STATE_DIR/MEETINGS_DIR from
the LIVE profile at import time and does not thread `root`. `root` is accepted for
signature symmetry / test injection only. Re-plumbing otter_sync is out of scope.
"""


def sync(root=None) -> dict:
    import otter_sync  # heavy deps (otterai) — import only when dispatching
    try:
        otter_sync.main()
    except Exception as e:  # narrow: Exception, not BaseException
        return {"status": "error", "provider": "otter", "error": str(e)}
    return {"status": "ok", "provider": "otter"}
```

```python
# scripts/adapters/transcript/granola.py
"""Granola transcript adapter — documented drop-in stub.

The seam is wired (select provider "granola" in integrations.yaml). To make it
real, implement sync() to pull Granola transcripts into the profile's transcript
target dir, mirroring otter.py's contract (return {"status": "ok", ...}).
"""


def sync(root=None) -> dict:
    return {"status": "unsupported", "provider": "granola",
            "note": "Granola adapter is a wired stub — implement sync()"}
```

```python
# scripts/transcript_sync.py  — replace the provider if-ladder in sync() with:
def sync(root=None):
    provider = profile_lib.transcript_config(root)["provider"]
    if provider == "none":
        return {"status": "skipped", "provider": "none"}
    import adapters
    mod = adapters.get("transcript", root)
    if mod is None:
        return {"status": "unsupported", "provider": provider}
    return mod.sync(root)
```

Keep `_run_otter` only if `test_transcript_sync.py` patches it. **It does** (`monkeypatch.setattr(transcript_sync, "_run_otter", ...)`). To keep that test green without rewriting it, route the otter adapter's body through `transcript_sync._run_otter` OR update the test. Decision: keep `transcript_sync._run_otter` and have `otter.py` call it, so the existing test contract holds. Adjust `otter.sync` to `from transcript_sync import _run_otter` and wrap it.

> **Implementer note:** verify `tests/test_transcript_sync.py` stays green. If the loader indirection breaks its monkeypatch of `_run_otter`, prefer adjusting `otter.py` to call `transcript_sync._run_otter` over editing the existing test.

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_adapters.py tests/test_transcript_sync.py -v`
Expected: PASS (all, including the 4 pre-existing transcript_sync tests)

**Step 5: Commit**

```bash
git add scripts/adapters/transcript/ scripts/transcript_sync.py tests/test_adapters.py
git commit -m "feat(adapters): transcript loader; Otter/Granola behind the seam"
```

---

## Task 4: Card registry data + tested Python validator

**Files:**
- Create: `ui/task-board/cardtypes/registry.json`
- Create: `ui/task-board/cardtypes/signal-ids.txt` (newline-listed signal ids the JS `signalPredicates` map defines — the validator cross-checks against this)
- Create: `scripts/card_schema.py`
- Test: `tests/test_card_schema.py`

**Step 1: Write the failing test**

```python
# tests/test_card_schema.py
import json
import pytest
import card_schema

REG = "ui/task-board/cardtypes/registry.json"


def test_real_registry_validates():
    errors = card_schema.validate()  # validates the repo's real registry.json
    assert errors == [], f"registry.json invalid: {errors}"


def test_dangling_signal_reference_is_caught(tmp_path):
    reg = {"slotOrder": ["head", "title", "context", "signals", "body", "actions"],
           "signals": {}, "actions": {},
           "cardTypes": {"task": {"signals": ["ghost"], "actions": [], "body": None}}}
    errors = card_schema.validate_doc(reg, signal_ids={"ghost"}, tokens=set())
    assert any("ghost" in e for e in errors)


def test_hardcoded_color_is_rejected(tmp_path):
    reg = {"slotOrder": ["head", "title", "context", "signals", "body", "actions"],
           "signals": {"x": {"icon": "due", "tokens": ["#ff0000"]}},
           "actions": {}, "cardTypes": {"task": {"signals": ["x"], "actions": [], "body": None}}}
    errors = card_schema.validate_doc(reg, signal_ids={"x"}, tokens={"--accent"})
    assert any("token" in e.lower() or "color" in e.lower() for e in errors)


def test_unknown_body_renderer_is_caught():
    reg = {"slotOrder": ["head", "title", "context", "signals", "body", "actions"],
           "signals": {}, "actions": {},
           "cardTypes": {"task": {"signals": [], "actions": [], "body": "nope"}}}
    errors = card_schema.validate_doc(reg, signal_ids=set(), tokens=set(),
                                      body_renderers={"diff", "preview", "agreement"})
    assert any("nope" in e for e in errors)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_card_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'card_schema'` (and the real registry doesn't exist yet)

**Step 3: Write minimal implementation**

Create `ui/task-board/cardtypes/registry.json` (tokens must be REAL `--vars` present in `ui/task-board/themes/_TEMPLATE.css` — implementer confirms each):

```json
{
  "slotOrder": ["head", "title", "context", "signals", "body", "actions"],
  "signals": {
    "due":        { "icon": "due",      "variant": "due" },
    "overdue":    { "icon": "overdue",  "variant": "overdue" },
    "waiting_on": { "icon": "hourglass","variant": "waiting" },
    "waiting_due":{ "icon": "due",      "variant": "due" },
    "schedule":   { "icon": "meeting",  "variant": "meeting" },
    "message":    { "icon": "chat",     "variant": "message" },
    "jira_draft": { "icon": "jira",     "variant": "accent" },
    "cron":       { "icon": "cron",     "variant": "cron" }
  },
  "actions": {
    "mark_done":   { "label": "Mark done",       "handler": "quickDone",   "primary": true },
    "open_output": { "label": "Open output",     "handler": "outputLink",  "truncatePath": true },
    "publish_jira":{ "label": "Publish to Jira", "handler": "publishJira" },
    "accept":      { "label": "Accept",          "handler": "cardAccept",  "primary": true },
    "reject":      { "label": "Reject",          "handler": "cardReject" },
    "keep":        { "label": "Keep",            "handler": "cardKeep",    "primary": true },
    "undo":        { "label": "Undo",            "handler": "cardUndo" },
    "graduate":    { "label": "Graduate",        "handler": "cardGraduate","primary": true }
  },
  "cardTypes": {
    "task":           { "signals": "auto", "actions": ["mark_done", "open_output"], "body": null },
    "recommendation": { "signals": [],     "actions": ["accept", "reject"],        "body": "diff" },
    "receipt":        { "signals": [],     "actions": ["keep", "undo"],            "body": "preview" },
    "graduation":     { "signals": [],     "actions": ["graduate"],                "body": "agreement" }
  }
}
```

Create `ui/task-board/cardtypes/signal-ids.txt`:

```
due
overdue
waiting_on
waiting_due
schedule
message
jira_draft
cron
```

Create `scripts/card_schema.py`:

```python
"""Validator for the declarative card registry (the design-system gate).

Enforces §9: card definitions reference theme tokens ONLY (no hardcoded colors),
every referenced signal/action exists, every signal id has a JS predicate
(cross-checked vs signal-ids.txt), and bodies name a known renderer or null.
This is the gate the future factory runs before writing a new card type.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "ui", "task-board", "cardtypes", "registry.json")
SIGNAL_IDS = os.path.join(ROOT, "ui", "task-board", "cardtypes", "signal-ids.txt")
TEMPLATE_CSS = os.path.join(ROOT, "ui", "task-board", "themes", "_TEMPLATE.css")
BODY_RENDERERS = {"diff", "preview", "agreement"}
SLOTS = {"head", "title", "context", "signals", "body", "actions"}

_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgb\(|\bhsl\(|\b\d+px\b")


def _theme_tokens():
    if not os.path.isfile(TEMPLATE_CSS):
        return set()
    with open(TEMPLATE_CSS, encoding="utf-8") as f:
        return set(re.findall(r"(--[a-zA-Z0-9-]+)\s*:", f.read()))


def _declared_signal_ids():
    if not os.path.isfile(SIGNAL_IDS):
        return set()
    with open(SIGNAL_IDS, encoding="utf-8") as f:
        return {ln.strip() for ln in f if ln.strip()}


def validate_doc(reg, signal_ids, tokens, body_renderers=BODY_RENDERERS):
    errors = []
    if set(reg.get("slotOrder", [])) != SLOTS:
        errors.append(f"slotOrder must be exactly {sorted(SLOTS)}")
    cat_sig = reg.get("signals", {})
    cat_act = reg.get("actions", {})

    # token-only rule across every string in signals + actions
    for group_name, group in (("signals", cat_sig), ("actions", cat_act)):
        for name, spec in group.items():
            for tok in spec.get("tokens", []):
                if not tok.startswith("--"):
                    errors.append(f"{group_name}.{name}: '{tok}' is not a theme token")
                elif tok not in tokens:
                    errors.append(f"{group_name}.{name}: token '{tok}' not in theme")
            for k, v in spec.items():
                if isinstance(v, str) and _COLOR_RE.search(v):
                    errors.append(f"{group_name}.{name}.{k}: hardcoded color/size '{v}'")
            if group is cat_sig and name not in signal_ids:
                errors.append(f"signal '{name}' has no predicate in signal-ids.txt")

    for ct, spec in reg.get("cardTypes", {}).items():
        sigs = spec.get("signals", [])
        if sigs != "auto":
            for s in sigs:
                if s not in cat_sig:
                    errors.append(f"cardType '{ct}': unknown signal '{s}'")
        for a in spec.get("actions", []):
            if a not in cat_act:
                errors.append(f"cardType '{ct}': unknown action '{a}'")
        body = spec.get("body")
        if body is not None and body not in body_renderers:
            errors.append(f"cardType '{ct}': unknown body renderer '{body}'")
    return errors


def validate():
    with open(REGISTRY, encoding="utf-8") as f:
        reg = json.load(f)
    return validate_doc(reg, _declared_signal_ids(), _theme_tokens())


if __name__ == "__main__":
    import sys
    errs = validate()
    if errs:
        print("\n".join(errs)); sys.exit(1)
    print("registry.json OK")
```

> **Implementer note:** the real `registry.json` ships with **no `tokens` arrays** initially (rendering metadata only — icon/variant). That keeps `test_real_registry_validates` green without coupling to specific theme vars yet; tokens are added per signal only when a card needs a token the variant class doesn't already supply. The token-checking code path is exercised by the unit fixtures.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_card_schema.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add ui/task-board/cardtypes/ scripts/card_schema.py tests/test_card_schema.py
git commit -m "feat(cards): declarative card registry + tested Python validator"
```

---

## Task 5: JS renderer refactor + Word-box truncation fix (manual-verified)

**Files:**
- Create: `ui/task-board/js/card-registry.js`
- Modify: `ui/task-board/index.html` (add `<script src="/js/card-registry.js">` BEFORE `board.js`)
- Modify: `ui/task-board/js/board.js` (`renderCard` delegates; keep signature `renderCard(task, queue)`)
- Modify: theme CSS or `index.html` `<style>` — add `.card-action .path { max-width: …; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }` using existing tokens

> **No JS test harness** (deliberate — see design §6). Verification = the Python validator (Task 4) gates the data + a manual visual pass below.

**Step 1: Build `card-registry.js`**

Holds: a `cardRegistry` loaded once from `/cardtypes/registry.json`; the `signalPredicates` map (move today's conditions out of `renderCard`); a `bodyRenderers` map (`diff`/`preview`/`agreement` → minimal placeholder markup for now); and `renderCardFromRegistry(task, queue)` that walks `slotOrder`, reuses the existing head/title/context builders, renders signals whose predicate matches (when `signals:"auto"`) or the pinned list, the named body, then actions.

`signalPredicates` mirrors today's `board.js` exactly, e.g.:
```js
const signalPredicates = {
  due:        t => t.queue !== 'waiting' && t.due && String(t.due) >= today(),
  overdue:    t => t.queue !== 'waiting' && t.due && String(t.due) <  today(),
  waiting_on: t => t.queue === 'waiting' && !!t.waiting_on,
  waiting_due:t => t.queue === 'waiting' && !!t.waiting_expected,
  schedule:   t => t.task_type === 'schedule-meeting',
  message:    t => t.task_type === 'send-message',
  jira_draft: t => t.body && t.body.includes('<!-- JIRA_DRAFT -->'),
  cron:       t => isCronTask(t),
};
```

Load registry before first render; `app.js` already calls `fetchTasks()` on boot — gate the first render on the registry promise (or fetch it synchronously at startup in `card-registry.js` and cache).

**Step 2: Refactor `board.js::renderCard`**

`renderCard(task, queue)` becomes a thin wrapper: `return renderCardFromRegistry(task, queue);`. Move the signal/action HTML builders into `card-registry.js` (or keep helpers in `board.js` and call them from the registry renderer — implementer picks the smaller diff). The `open_output` action renderer wraps the path label in `<span class="path">…</span>` so the new CSS truncates it.

**Step 3: Manual verification (record results in the commit body)**

Start the board and visually confirm — seed/curate tasks covering every variant:
```bash
cd ~/dev/pm-os-team && python3 scripts/task_server.py   # then open the served localhost URL
```
Checklist (each must look identical to pre-refactor, except the Word-box fix):
- [ ] human/collab/agent/waiting queue chips render
- [ ] judge score badge + status mark in head
- [ ] source-meeting + domain context line
- [ ] due / overdue chips; waiting_on + waiting_expected chips
- [ ] **schedule-meeting** chip; **send-message (messaging)** chip
- [ ] **jira draft** chip; cron chip
- [ ] Mark done + Open output actions; quickDone still works
- [ ] **Agent card with a long Word/output path no longer forces horizontal scroll** (truncates with ellipsis)
- [ ] Now view + Board view both render via the same cards

**Step 4: Re-run the validator + full suite**

Run: `python3 -m pytest -q` and `python3 scripts/card_schema.py`
Expected: all pass; `registry.json OK`

**Step 5: Commit**

```bash
git add ui/task-board/js/card-registry.js ui/task-board/js/board.js ui/task-board/index.html
git commit -m "refactor(cards): renderCard reads the registry; fix agent-card path overflow

Manual visual pass: <paste checklist results>."
```

---

## Task 6: Pendo/Databricks integration facts → profile

**Files:**
- Modify: `profile.example/integrations.yaml` (add `analytics` block)
- Modify: `scripts/profile_lib.py` (`pendo_config`, `databricks_config`, CLI flags)
- Test: `tests/test_profile_lib.py` (append)

**Step 1: Write the failing test**

```python
def test_pendo_config_reads_from_profile(profile_root):
    import profile_lib
    # extend the fixture's integrations.yaml inline for this test
    p = os.path.join(profile_root, "profile", "integrations.yaml")
    with open(p, "a") as f:
        f.write("analytics:\n  pendo:\n    provider: pendo\n"
                "    subscription_id: '123'\n    app_ids: {web: 'a1'}\n")
    cfg = profile_lib.pendo_config(root=profile_root)
    assert cfg["subscription_id"] == "123"
    assert cfg["app_ids"]["web"] == "a1"


def test_databricks_config_defaults_empty(profile_root):
    import profile_lib
    cfg = profile_lib.databricks_config(root=profile_root)
    assert cfg["catalog"] == ""
    assert cfg["sources"] == {}
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_profile_lib.py -k "pendo or databricks" -v`
Expected: FAIL — `AttributeError: module 'profile_lib' has no attribute 'pendo_config'`

**Step 3: Write minimal implementation**

`profile.example/integrations.yaml` — append:
```yaml
analytics:
  pendo:
    provider: "none"      # pendo | none
    subscription_id: ""
    app_ids: {}
  databricks:
    provider: "none"      # databricks | none
    catalog: ""
    sources: {}
```

`profile_lib.py` — add:
```python
def _analytics(name, root=None):
    return (integrations(root).get("analytics") or {}).get(name) or {}


def pendo_config(root=None):
    p = _analytics("pendo", root)
    return {"provider": p.get("provider") or "none",
            "subscription_id": p.get("subscription_id", ""),
            "app_ids": p.get("app_ids") or {}}


def databricks_config(root=None):
    d = _analytics("databricks", root)
    return {"provider": d.get("provider") or "none",
            "catalog": d.get("catalog", ""),
            "sources": d.get("sources") or {}}
```

`profile_lib.py` `__main__` — add CLI flags (so headless AND interactive Claude can read live values):
```python
    if "--pendo-subid" in sys.argv:
        print(pendo_config().get("subscription_id", ""))
    if "--databricks-catalog" in sys.argv:
        print(databricks_config().get("catalog", ""))
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_profile_lib.py -k "pendo or databricks" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add profile.example/integrations.yaml scripts/profile_lib.py tests/test_profile_lib.py
git commit -m "feat(profile): pendo/databricks analytics config + CLI accessors"
```

---

## Task 7: De-hardcode the analytics skills/workers (dual-context + guard test)

**Files:**
- Modify: `.claude/skills/context-pendo-analytics/SKILL.md`
- Modify: `.claude/skills/context-databricks-analytics/SKILL.md`
- Modify: `.claude/skills/metric-quarterly-rocks/SKILL.md`
- Modify: affected `scripts/workers/*.md` (researcher, product-analyst — wherever subId/catalog appear)
- Test: `tests/test_no_hardcoded_tenant.py` (new guard)

**Step 1: Write the failing test**

```python
# tests/test_no_hardcoded_tenant.py — template must ship free of Vantaca tenant facts
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANNED = ["4818486697721856"]  # Pendo subId; add other tenant literals as found


def test_no_hardcoded_tenant_ids_in_skills_or_workers():
    hits = []
    paths = glob.glob(os.path.join(ROOT, ".claude/skills/**/*.md"), recursive=True)
    paths += glob.glob(os.path.join(ROOT, "scripts/workers/*.md"))
    for path in paths:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for token in BANNED:
            if token in text:
                hits.append(f"{os.path.relpath(path, ROOT)}: '{token}'")
    assert hits == [], f"hardcoded tenant facts: {hits}"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_no_hardcoded_tenant.py -v`
Expected: FAIL — lists the files still carrying `4818486697721856` (and `is_prod` if added to BANNED).

> First run `grep -rn "4818486697721856\|is_prod" .claude/skills scripts/workers` to enumerate every hit, so the edits are complete.

**Step 3: Edit the skills/workers (prose)**

Replace each literal with a dual-context instruction + graceful degradation, e.g. in `context-pendo-analytics`:
> The Pendo subscription ID is **not hardcoded** — read it from the active profile:
> `python3 scripts/profile_lib.py --pendo-subid` (or read `profile/integrations.yaml`
> → `analytics.pendo.subscription_id`). If `analytics.pendo.provider` is `none`, tell the
> user Pendo is not configured for this install and stop — do not guess an ID.

Mirror for Databricks (`--databricks-catalog`, `analytics.databricks.sources`). For `metric-quarterly-rocks`, generalize Jay's specific Rocks to read targets/metrics from the profile (or mark them operator-supplied) rather than baking Vantaca specifics. Keep instructions identical whether run headless or interactively (no app-only assumptions).

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_no_hardcoded_tenant.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add .claude/skills tests/test_no_hardcoded_tenant.py scripts/workers
git commit -m "refactor(skills): read Pendo/Databricks facts from profile (dual-context); guard test"
```

---

## Task 8: `msgraph_cli` (`mgc`) install route in the Doctor

**Files:**
- Modify: `scripts/doctor.py` (replace the `msgraph_cli` placeholder remedy)
- Test: `tests/test_doctor.py` (append)

**Step 1: Confirm the real install command**

`mgc` (Microsoft Graph CLI) macOS install — confirm the current route (`brew install microsoftgraph/tap/msgraph-cli`, or the documented binary). Capture the exact command; if unconfirmable in this environment, record the most-authoritative documented command and mark it `# confirm on live Doctor run` per the Phase-2 residual.

**Step 2: Write the failing test**

```python
def test_msgraph_remedy_is_a_real_install_command():
    import doctor
    remedy = doctor.remedy_for("msgraph_cli")  # adjust to the actual accessor
    assert "claude.ai/code install" not in remedy   # placeholder gone
    assert "mgc" in remedy or "msgraph" in remedy
```

**Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_doctor.py -k msgraph -v`
Expected: FAIL (placeholder still present)

> **Implementer note:** read `doctor.py` first to find how remedies are stored/looked up; adapt the test's accessor to the real structure.

**Step 4: Implement + run**

Replace the placeholder with the confirmed command. Run: `python3 -m pytest tests/test_doctor.py -v` → PASS.

**Step 5: Commit**

```bash
git add scripts/doctor.py tests/test_doctor.py
git commit -m "fix(doctor): real msgraph_cli (mgc) install route, replacing placeholder"
```

---

## Final: full-suite gate + finish the branch

**Step 1:** `python3 -m pytest -q` — expect all prior 86 + new tests green.
**Step 2:** `python3 scripts/card_schema.py` — `registry.json OK`.
**Step 3:** Re-do the Task-5 manual board checklist once more on the final state.
**Step 4:** Update `docs/plans/2026-06-06-phase-3-residual.md` (mirror the Phase-2 residual format): Definition of Done, deferred items (Asana/Granola impls, calendar/doc_sync adapters, JS test harness, `recommendation/receipt/graduation` body markup, `mgc` live-confirm), and anything surfaced in review.
**Step 5:** REQUIRED SUB-SKILL: superpowers:finishing-a-development-branch — decide merge/PR.

---

## Task dependency / ordering

- **1 → 2 → 3** (adapters; 2 and 3 depend on 1's loader + `tests/test_adapters.py`).
- **4 → 5** (registry data + validator before the JS refactor that consumes it).
- **6 → 7** (profile accessors before the skills that reference them).
- **8** independent.
- Groups (1-3), (4-5), (6-7), (8) are mutually independent — safe to parallelize across implementer subagents if desired, but the two-stage review per task still applies.
