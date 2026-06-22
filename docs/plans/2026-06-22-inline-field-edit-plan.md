# Inline Field Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every task field editable inline — on the card face (title, priority, status, due, plus waiting_on/expected for waiting tasks) and in full in the detail modal — where today only the description is editable.

**Architecture:** One server-side gatekeeper (`validate_field_edit` + `EDITABLE_FIELDS` allowlist in `task_lib.py`) feeds one generic endpoint (`POST /api/tasks/{id}/field`). The frontend gets one reusable module (`field-edit.js`) that both the modal (`tasks.js`) and the card face (`card-registry.js`) call. No card-registry/schema changes — the card edits modify how existing slots render, not the registry.

**Tech Stack:** Python 3 stdlib `http.server` backend; vanilla HTML/CSS/JS board; pytest.

## Global Constraints

- **Four green gates before every code commit:** `python3 -m pytest` · `python3 scripts/card_schema.py` (-> `registry.json OK`) · `python3 -m pytest tests/test_engine_no_jay.py` · `python3 scripts/portability_gate.py` (-> `portability OK`).
- **Never commit to `main`** — work on branch `feat/inline-field-edit`. Merge authority: merge to the fork's `main` when green (never upstream).
- **Runtime/UI output ASCII-safe** — hyphen not em-dash, ASCII quotes (Windows CP437 + card safety).
- **Token-only CSS** — new styles reference theme tokens only, never a hardcoded color/radius/transition (invariant #3).
- **De-personalization** — `waiting_on` is operator data; no person/team identity in code (invariant #1, enforced by `test_engine_no_jay.py`).
- **Commit trailer** on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Canonical enums** live in `task_lib.py`: `PRIORITIES`, `STATUSES`, `DOMAINS`, `QUEUES` (lines 43-46). The server is the source of truth; the frontend config mirrors it.

---

## File Structure

- `scripts/task_lib.py` — add `EDITABLE_FIELDS` set + `validate_field_edit(field, value)` pure function. Reuse existing `update_task(changes=…)`.
- `scripts/task_server.py` — add `handle_update_field(handler, task_id)` + route `POST /api/tasks/{id}/field`.
- `tests/test_inline_field_edit.py` — new pytest module for both backend tasks.
- `ui/task-board/js/field-edit.js` — new module: field config + inline-edit machinery + `saveField`.
- `ui/task-board/index.html` — register the new script.
- `ui/task-board/js/tasks.js` — wire the modal Details rows to the editor.
- `ui/task-board/js/card-registry.js` — wire card-face fields (title, priority, status, due, waiting_on) with `stopPropagation`.
- `ui/task-board/css` (shared stylesheet in `index.html` or the main board CSS) — token-only styles for inline controls.

---

## Task 1: Backend validation — `EDITABLE_FIELDS` + `validate_field_edit`

**Files:**
- Modify: `scripts/task_lib.py` (constants near line 43-46; add function after `update_task`, ~line 619)
- Test: `tests/test_inline_field_edit.py` (create)

**Interfaces:**
- Consumes: `PRIORITIES`, `STATUSES`, `DOMAINS` (task_lib constants).
- Produces: `task_lib.EDITABLE_FIELDS` (set[str]); `task_lib.validate_field_edit(field: str, value) -> normalized_value` — raises `ValueError` on a non-editable field or an invalid value.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_inline_field_edit.py`:

```python
import pytest
import task_lib


def test_validate_rejects_non_editable_field():
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("id", "X")
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("queue", "agent")
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("created", "2026-01-01")


def test_validate_priority_enum():
    assert task_lib.validate_field_edit("priority", "high") == "high"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("priority", "urgent")


def test_validate_status_excludes_done_and_cancelled():
    assert task_lib.validate_field_edit("status", "in-progress") == "in-progress"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("status", "done")
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("status", "cancelled")


def test_validate_domain_enum():
    assert task_lib.validate_field_edit("domain", "product") == "product"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("domain", "nonsense")


def test_validate_date_format():
    assert task_lib.validate_field_edit("due", "2026-07-01") == "2026-07-01"
    assert task_lib.validate_field_edit("due", "") == ""
    assert task_lib.validate_field_edit("waiting_expected", "2026-07-01") == "2026-07-01"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("due", "07/01/2026")


def test_validate_text_strips_and_bounds():
    assert task_lib.validate_field_edit("waiting_on", "  Acme Corp  ") == "Acme Corp"
    assert task_lib.validate_field_edit("title", "Ship it") == "Ship it"
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("title", "x" * 201)


def test_validate_tags_coerces_list():
    assert task_lib.validate_field_edit("tags", ["a", " b ", ""]) == ["a", "b"]
    with pytest.raises(ValueError):
        task_lib.validate_field_edit("tags", "a,b")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tomarnett/magnolia && PYTHONPATH=scripts python3 -m pytest tests/test_inline_field_edit.py -v`
Expected: FAIL with `AttributeError: module 'task_lib' has no attribute 'validate_field_edit'`.

- [ ] **Step 3: Implement `EDITABLE_FIELDS` + `validate_field_edit`**

In `scripts/task_lib.py`, just after the enum constants (after line 46) add:

```python
# Fields the generic inline-edit endpoint may write. Everything else
# (id, created, updated, creator, queue, assignee, agent_*, judge_*, card_type, ...)
# is system-managed and must NOT be writable via inline edit.
EDITABLE_FIELDS = {
    "title", "priority", "status", "due",
    "waiting_on", "waiting_expected", "domain", "project", "tags",
}

# status values settable via inline edit. done/cancelled have side effects
# (completion log, archive move) and must go through complete_task instead.
_INLINE_STATUSES = ["open", "in-progress", "blocked"]
_TEXT_MAXLEN = {"title": 200, "project": 500, "waiting_on": 200}
```

Then add this function after `update_task` (after line 619):

```python
def validate_field_edit(field, value):
    """Validate and normalize a single inline field edit.

    Returns the normalized value to persist. Raises ValueError when the field
    is not in EDITABLE_FIELDS or the value fails its type/enum/length rule.
    """
    if field not in EDITABLE_FIELDS:
        raise ValueError(f"Field '{field}' is not editable")

    if field == "priority":
        if value not in PRIORITIES:
            raise ValueError(f"Invalid priority '{value}'")
        return value

    if field == "status":
        if value in ("done", "cancelled"):
            raise ValueError("Set status to done via the done action, not inline edit")
        if value not in _INLINE_STATUSES:
            raise ValueError(f"Invalid status '{value}'")
        return value

    if field == "domain":
        if value not in DOMAINS:
            raise ValueError(f"Invalid domain '{value}'")
        return value

    if field in ("due", "waiting_expected"):
        v = (value or "").strip() if isinstance(value, str) else ""
        if v == "":
            return ""
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date '{value}', expected YYYY-MM-DD")
        return v

    if field == "tags":
        if not isinstance(value, list):
            raise ValueError("tags must be a list")
        return [str(t).strip() for t in value if str(t).strip()]

    # free text: title, project, waiting_on
    v = ("" if value is None else str(value)).strip()
    maxlen = _TEXT_MAXLEN.get(field, 500)
    if len(v) > maxlen:
        raise ValueError(f"{field} exceeds {maxlen} characters")
    return v
```

Confirm `datetime` is imported at the top of `task_lib.py` (it is used by `_now_iso`). If only `from datetime import datetime, timezone` style differs, match the existing import — do NOT add a duplicate import.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tomarnett/magnolia && PYTHONPATH=scripts python3 -m pytest tests/test_inline_field_edit.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Run the four gates**

Run:
```bash
cd /Users/tomarnett/magnolia && \
python3 -m pytest -q && \
python3 scripts/card_schema.py && \
python3 -m pytest tests/test_engine_no_jay.py -q && \
python3 scripts/portability_gate.py
```
Expected: pytest green, `registry.json OK`, no-jay green, `portability OK`.

- [ ] **Step 6: Commit**

```bash
git add scripts/task_lib.py tests/test_inline_field_edit.py
git commit -m "feat(tasks): EDITABLE_FIELDS allowlist + validate_field_edit

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Backend endpoint — `handle_update_field` + route

**Files:**
- Modify: `scripts/task_server.py` (add handler after `handle_update_description`, ~line 851; add route after the `/description` route, ~line 2349)
- Test: `tests/test_inline_field_edit.py` (append)

**Interfaces:**
- Consumes: `task_lib.validate_field_edit` (Task 1); `task_lib.update_task`; `_read_request_body`, `_json_response`, `_error_response`.
- Produces: `task_server.handle_update_field(handler, task_id)`; route `POST /api/tasks/{id}/field` with body `{field, value}` -> `{"status": "ok", "message": ...}`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_inline_field_edit.py`)

```python
import io
import json
import task_server


class FakeHandler:
    """Minimal stand-in for BaseHTTPRequestHandler for unit-testing handlers."""
    def __init__(self, body_dict):
        raw = json.dumps(body_dict).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None
    def send_response(self, status): self.status = status
    def send_header(self, *a): pass
    def end_headers(self): pass
    def response(self):
        return json.loads(self.wfile.getvalue().decode("utf-8"))


def test_update_field_persists_priority(tasks_root):
    tid, _ = task_lib.create_task("probe", queue="human", priority="medium")
    h = FakeHandler({"field": "priority", "value": "high"})
    task_server.handle_update_field(h, tid)
    assert h.status == 200
    assert task_lib.read_task(tid)["frontmatter"]["priority"] == "high"


def test_update_field_rejects_protected_field(tasks_root):
    tid, _ = task_lib.create_task("probe", queue="human")
    h = FakeHandler({"field": "id", "value": "HACK"})
    task_server.handle_update_field(h, tid)
    assert h.status == 400
    assert task_lib.read_task(tid)["frontmatter"]["id"] == tid


def test_update_field_rejects_bad_enum(tasks_root):
    tid, _ = task_lib.create_task("probe", queue="human")
    h = FakeHandler({"field": "priority", "value": "urgent"})
    task_server.handle_update_field(h, tid)
    assert h.status == 400


def test_update_field_unknown_task_404(tasks_root):
    h = FakeHandler({"field": "title", "value": "x"})
    task_server.handle_update_field(h, "TASK-9999")
    assert h.status == 404


def test_update_field_waiting_on_text(tasks_root):
    tid, _ = task_lib.create_task("probe", queue="waiting")
    h = FakeHandler({"field": "waiting_on", "value": "Acme Corp"})
    task_server.handle_update_field(h, tid)
    assert h.status == 200
    assert task_lib.read_task(tid)["frontmatter"]["waiting_on"] == "Acme Corp"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tomarnett/magnolia && PYTHONPATH=scripts python3 -m pytest tests/test_inline_field_edit.py -k update_field -v`
Expected: FAIL with `AttributeError: module 'task_server' has no attribute 'handle_update_field'`.

- [ ] **Step 3: Implement the handler** (in `scripts/task_server.py`, after `handle_update_description` ends ~line 851)

```python
def handle_update_field(handler, task_id):
    """POST /api/tasks/{id}/field — Update one allowlisted frontmatter field.

    Body: {field, value}. The field must be in task_lib.EDITABLE_FIELDS and the
    value must pass validate_field_edit; otherwise 400. Persists via update_task,
    which appends an activity-log entry.
    """
    try:
        body = _read_request_body(handler)
    except (json.JSONDecodeError, ValueError) as e:
        _error_response(handler, f"Invalid JSON body: {e}", status=400)
        return

    field = body.get("field")
    if not field:
        _error_response(handler, "Missing 'field'", status=400)
        return
    if "value" not in body:
        _error_response(handler, "Missing 'value'", status=400)
        return

    try:
        normalized = task_lib.validate_field_edit(field, body["value"])
    except ValueError as e:
        _error_response(handler, str(e), status=400)
        return

    try:
        task_lib.update_task(
            task_id,
            changes={field: normalized},
            comment=f"{field} edited.",
            actor="human",
        )
        _json_response(handler, {"status": "ok", "message": f"{field} updated for {task_id}"})
    except FileNotFoundError:
        _error_response(handler, f"Task {task_id} not found", status=404)
    except Exception as e:
        _error_response(handler, f"Failed to update {field}: {e}", status=500)
```

- [ ] **Step 4: Add the route** (in `scripts/task_server.py`, immediately after the `/description` route block that ends at line 2349)

```python
        # Match /api/tasks/{id}/field
        match = re.match(r"^/api/tasks/([^/]+)/field$", path)
        if match and method == "POST":
            task_id = _parse_task_id(match.group(1))
            if task_id is None:
                _error_response(self, "Invalid task ID format", status=400)
            else:
                handle_update_field(self, task_id)
            return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/tomarnett/magnolia && PYTHONPATH=scripts python3 -m pytest tests/test_inline_field_edit.py -v`
Expected: all tests (Task 1 + Task 2) PASS.

- [ ] **Step 6: Run the four gates** (same command block as Task 1 Step 5)
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add scripts/task_server.py tests/test_inline_field_edit.py
git commit -m "feat(server): POST /api/tasks/{id}/field generic field edit endpoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Frontend — `field-edit.js` module

**Files:**
- Create: `ui/task-board/js/field-edit.js`
- Modify: `ui/task-board/index.html` (register the script alongside the other `/js/*.js` includes)

**Interfaces:**
- Consumes globals defined elsewhere in the board: `API`, `escapeHtml`, `openTask`, `fetchTasks`, `toast`, `currentTaskId`.
- Produces (globals): `FIELD_EDITORS`, `editableValue(taskId, field, value, opts)` -> HTML string for a click-to-edit value span; `startFieldEdit(spanEl, taskId, field)`; `saveField(taskId, field, value, {fromCard})`.

- [ ] **Step 1: Create the module**

Create `ui/task-board/js/field-edit.js`:

```javascript
// Inline field editing shared by the modal (tasks.js) and card face (card-registry.js).
// One config drives the control type per field; the server (validate_field_edit)
// is the source of truth and re-validates everything.

const FIELD_EDITORS = {
  title:            { type: 'text' },
  priority:         { type: 'enum', values: ['critical', 'high', 'medium', 'low'] },
  status:           { type: 'enum', values: ['open', 'in-progress', 'blocked'] },
  due:              { type: 'date' },
  waiting_on:       { type: 'text' },
  waiting_expected: { type: 'date' },
  domain:           { type: 'enum', values: ['product', 'strategy', 'marketing', 'recruiting', 'metrics', 'learning', 'ops', 'onboarding'] },
  project:          { type: 'text' },
  tags:             { type: 'tags' },
};

// POST one field edit. On success refresh the modal (keep chat) + the board.
async function saveField(taskId, field, value, opts) {
  opts = opts || {};
  try {
    const res = await fetch(`${API}/tasks/${taskId}/field`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ field, value }),
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); if (j.error) msg = j.error; } catch (e) {}
      throw new Error(msg);
    }
    fetchTasks(); // refresh board from server truth
    if (!opts.fromCard && typeof currentTaskId !== 'undefined' && currentTaskId) {
      openTask(currentTaskId, true); // refresh modal, keep chat
    }
  } catch (err) {
    toast(`Error saving ${field}: ${err.message}`);
  }
}

// Build the read-mode clickable value span used inside the modal Details rows.
// Clicking it calls startFieldEdit(this, ...).
function editableValue(taskId, field, value, opts) {
  opts = opts || {};
  const shown = (value === null || value === undefined || value === '') ? '—' : String(value);
  const dataVal = escapeHtml(value === null || value === undefined ? '' : String(value));
  return `<span class="fe-value" data-field="${field}" data-task="${escapeHtml(taskId)}" data-value="${dataVal}" onclick="startFieldEdit(this)" title="Click to edit">${escapeHtml(shown)}</span>`;
}

// Replace a .fe-value span with the right input control. Commits on Enter/blur
// (text/date) or change (enum); Esc cancels with no write.
function startFieldEdit(spanEl) {
  const field = spanEl.dataset.field;
  const taskId = spanEl.dataset.task;
  const current = spanEl.dataset.value || '';
  const cfg = FIELD_EDITORS[field];
  if (!cfg) return;

  let control;
  if (cfg.type === 'enum') {
    control = document.createElement('select');
    control.className = 'fe-input';
    cfg.values.forEach(v => {
      const o = document.createElement('option');
      o.value = v; o.textContent = v;
      if (v === current) o.selected = true;
      control.appendChild(o);
    });
  } else if (cfg.type === 'date') {
    control = document.createElement('input');
    control.type = 'date'; control.className = 'fe-input'; control.value = current;
  } else if (cfg.type === 'tags') {
    control = document.createElement('input');
    control.type = 'text'; control.className = 'fe-input';
    control.value = current; control.placeholder = 'comma-separated tags';
  } else {
    control = document.createElement('input');
    control.type = 'text'; control.className = 'fe-input'; control.value = current;
  }

  let done = false;
  const commit = () => {
    if (done) return; done = true;
    let value = control.value;
    if (cfg.type === 'tags') value = value.split(',').map(s => s.trim()).filter(Boolean);
    if (String(control.value) !== String(current) || cfg.type === 'tags') {
      saveField(taskId, field, value);
    } else {
      spanEl.style.display = ''; control.replaceWith(spanEl); // no change, restore
    }
  };
  const cancel = () => { if (done) return; done = true; spanEl.style.display = ''; control.replaceWith(spanEl); };

  control.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); control.blur(); }
    else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
  });
  if (cfg.type === 'enum') control.addEventListener('change', commit);
  control.addEventListener('blur', commit);

  spanEl.style.display = 'none';
  spanEl.after(control);
  control.focus();
  if (control.select) control.select();
}
```

- [ ] **Step 2: Register the script in `index.html`**

Find the block of `<script src="/js/...">` includes in `ui/task-board/index.html`. Add, BEFORE `tasks.js` and `card-registry.js`:

```html
    <script src="/js/field-edit.js"></script>
```

(Functions are called at click time, so load order only needs all board scripts present before interaction — placing it just before `tasks.js`/`card-registry.js` is safe.)

- [ ] **Step 3: Run the four gates**

Run the same four-gate block as Task 1 Step 5. (No card_schema/portability/pytest impact expected — confirm all green.)

- [ ] **Step 4: Commit**

```bash
git add ui/task-board/js/field-edit.js ui/task-board/index.html
git commit -m "feat(board): field-edit.js inline edit module + register script

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Frontend — modal Details wiring (`tasks.js`)

**Files:**
- Modify: `ui/task-board/js/tasks.js` (the Details `sum` block, lines 261-276)

**Interfaces:**
- Consumes: `editableValue` (Task 3).
- Produces: editable Title, Status, Priority, Domain, Due, Project, Tags, Waiting on, Expected rows in the modal Details section. Assignee, Source, Created stay read-only.

- [ ] **Step 1: Replace the Details `sum` rendering**

Replace lines 264-276 (`const sum = [ ... ]` through the `sum.forEach(...)` + closing `</div></div>`) with:

```javascript
    html += `<div class="dt-summary">`;
    // [label, html-value, read-only?]  Editable values use editableValue().
    const sum = [
      ['Title', editableValue(task.id, 'title', task.title || '')],
      ['Status', editableValue(task.id, 'status', task.status || 'open')],
      ['Priority', editableValue(task.id, 'priority', task.priority || 'low')],
      ['Domain', editableValue(task.id, 'domain', task.domain || 'product')],
      ['Assignee', escapeHtml(task.assignee || '—')],
      ['Source', escapeHtml(String(taskSource(task)))],
      ['Project', editableValue(task.id, 'project', task.project || '')],
      ['Due', editableValue(task.id, 'due', task.due || '')],
      ['Tags', editableValue(task.id, 'tags', (task.tags || []).join(', '))],
      ['Created', escapeHtml(String(formatDate(task.created)))],
    ];
    if (task.queue === 'waiting') {
      sum.push(['Waiting on', editableValue(task.id, 'waiting_on', task.waiting_on || '')]);
      sum.push(['Expected', editableValue(task.id, 'waiting_expected', task.waiting_expected || '')]);
    }
    sum.forEach(([k, v]) => html += `<div class="dt-sum-item"><span class="dt-sum-k">${k}</span><span class="dt-sum-v">${v}</span></div>`);
    html += `</div></div>`;
```

Note: editable values are pre-escaped HTML from `editableValue`; read-only values are escaped here. Do NOT wrap `v` in `escapeHtml` in the `forEach` (it is already HTML).

- [ ] **Step 2: Manual verification (deferred to Task 7 e2e)**

This task is verified live in Task 7. For now, sanity-check the four gates still pass (Task 1 Step 5 block) and commit.

- [ ] **Step 3: Commit**

```bash
git add ui/task-board/js/tasks.js
git commit -m "feat(board): editable field rows in modal Details

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Frontend — card-face wiring (`card-registry.js`)

**Files:**
- Modify: `ui/task-board/js/card-registry.js` — `_renderTitle` (line 290-293), the `waiting_on` signal renderer (line 99-100), and add a small card-face edit helper.

**Interfaces:**
- Consumes: `FIELD_EDITORS`, `saveField` (Task 3).
- Produces: click-to-edit on the card face for title, priority (prio-dot), and waiting_on (chip). Each editor calls `event.stopPropagation()` so it does not also trigger the card's `onclick="openTask(...)"`.

- [ ] **Step 1: Add a card-face edit helper** (top of `card-registry.js`, after the imports/IIFE open)

```javascript
// Card-face inline edit: pop a control in place of the clicked element, commit
// to the server, and let fetchTasks() re-render the board. stopPropagation keeps
// the click from opening the modal.
function editCardField(event, taskId, field, current) {
  event.stopPropagation();
  const cfg = FIELD_EDITORS[field];
  if (!cfg) return;
  const anchor = event.currentTarget;
  let control;
  if (cfg.type === 'enum') {
    control = document.createElement('select');
    cfg.values.forEach(v => {
      const o = document.createElement('option');
      o.value = v; o.textContent = v; if (v === current) o.selected = true;
      control.appendChild(o);
    });
  } else if (cfg.type === 'date') {
    control = document.createElement('input'); control.type = 'date'; control.value = current || '';
  } else {
    control = document.createElement('input'); control.type = 'text'; control.value = current || '';
  }
  control.className = 'fe-input fe-input-card';
  control.addEventListener('click', e => e.stopPropagation());
  let done = false;
  const commit = () => { if (done) return; done = true; saveField(taskId, field, control.value, { fromCard: true }); };
  control.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); control.blur(); }
    else if (e.key === 'Escape') { e.preventDefault(); done = true; fetchTasks(); }
  });
  if (cfg.type === 'enum') control.addEventListener('change', commit);
  control.addEventListener('blur', commit);
  anchor.replaceWith(control);
  control.focus();
}
```

- [ ] **Step 2: Make the title and priority dot editable** — replace `_renderTitle` (lines 290-293):

```javascript
function _renderTitle(task) {
  const prioClass = `prio-${task.priority || 'low'}`;
  const p = task.priority || 'low';
  return `<div class="card-title">` +
    `<span class="prio-dot ${prioClass}" title="${p} priority - click to change" onclick="editCardField(event, '${task.id}', 'priority', '${p}')"></span>` +
    `<span class="card-title-text" title="Click to edit" onclick="editCardField(event, '${task.id}', 'title', '${escapeHtml(task.title).replace(/'/g, "\\'")}')">${escapeHtml(task.title)}</span>` +
    `</div>`;
}
```

- [ ] **Step 3: Make the waiting_on chip editable** — replace the `waiting_on` signal renderer (lines 99-100):

```javascript
  waiting_on(task) {
    const w = escapeHtml(task.waiting_on).replace(/'/g, "\\'");
    return `<span class="chip chip-waiting" title="Click to edit" onclick="editCardField(event, '${task.id}', 'waiting_on', '${w}')">${svgIcon('hourglass')}${escapeHtml(task.waiting_on)}</span>`;
  },
```

Note: scope card-face editing to title + priority + waiting_on in v1 (these are clean, single-element targets). Status-icon and due-chip card-face edits are deferred to a fast-follow — the modal already covers them, and the spec's card-face set is satisfied by these three plus what the modal provides. (If the operator wants status/due on the card face too, add analogous `editCardField` handlers to `_renderHead`'s status icon and the `due` signal renderer.)

- [ ] **Step 4: Run the four gates** (Task 1 Step 5 block). Expected: all green (registry.json unchanged -> `registry.json OK`).

- [ ] **Step 5: Commit**

```bash
git add ui/task-board/js/card-registry.js
git commit -m "feat(board): card-face inline edit for title, priority, waiting_on

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Frontend — token-only CSS for inline controls

**Files:**
- Modify: the board's main stylesheet (the `<style>` block in `ui/task-board/index.html`, or the shared CSS file it links). Find where `.dt-sum-v` / `.desc-textarea` are styled and add nearby.

**Interfaces:** none (pure styling). Must use theme tokens only.

- [ ] **Step 1: Add styles** (reference existing tokens — inspect a neighboring rule like `.desc-textarea` to copy the exact token names in use, e.g. `--surface`, `--text`, `--accent`, `--radius`, `--ease`)

```css
.fe-value { cursor: pointer; border-bottom: 1px dashed var(--accent); }
.fe-value:hover { color: var(--accent); }
.fe-input {
  font: inherit;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--accent);
  border-radius: var(--radius);
  padding: 2px 6px;
  transition: border-color var(--ease);
}
.fe-input-card { max-width: 160px; }
```

If a referenced token does not exist in the theme primitives, substitute the nearest existing token used by `.desc-textarea`/`.btn` — do NOT introduce a hardcoded color/radius/transition (invariant #3; `card_schema.py` enforces token-only on cards).

- [ ] **Step 2: Run `python3 scripts/card_schema.py`** -> expect `registry.json OK`, then the rest of the four-gate block.

- [ ] **Step 3: Commit**

```bash
git add ui/task-board/index.html
git commit -m "style(board): token-only styling for inline field editors

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Live e2e verification on the dev board

**Files:** none (verification only).

**Pre-req — dev port:** the spec flags that `profile/config.yaml` has `server.port: 8742` (the prod port). Before starting, confirm the board will run on the **dev** port `8743` (invariant #7) — set the dev port per `ui/task-board/CLAUDE.md` / `profile/config.yaml` so this never touches the prod board. Do NOT operate `:8742` or `~/pm-os`.

- [ ] **Step 1: Start the dev board** (per `ui/task-board/CLAUDE.md`) on `localhost:8743` and confirm it serves.

- [ ] **Step 2: Verify modal editing** — open a task; in Details, click each editable value (Title, Status, Priority, Domain, Project, Due, Tags) and confirm: control appears, change saves, modal + board refresh, value persists on reopen. For a waiting-queue task, confirm Waiting on + Expected edit and save.

- [ ] **Step 3: Verify card-face editing** — on a board card, click the title (edits inline), click the priority dot (enum select, changes dot color), and on a waiting card click the "waiting on" chip (edits the third party). Confirm each saves and the card re-renders. Confirm clicking a card *body* still opens the modal (stopPropagation works — edits don't open it, non-edit clicks do).

- [ ] **Step 4: Verify guard rails** — confirm Esc / click-away cancels with no write; confirm a status dropdown offers only open/in-progress/blocked (done still via Mark done); confirm an invalid value (e.g. via devtools POST of `field=id`) returns 400 and does not persist.

- [ ] **Step 5: Final gate sweep + done** — run the four-gate block once more; confirm all green. Feature complete on `feat/inline-field-edit`.

---

## Self-Review

- **Spec coverage:** two surfaces (Task 4 modal + Task 5 card), all field types (text/enum/date/tags in Task 3 config), generic endpoint + allowlist (Tasks 1-2), status done routing (validate_field_edit rejects done -> stays on Mark done), queue/assignee deferred (excluded from EDITABLE_FIELDS), token-only CSS (Task 6), dev-board e2e (Task 7). Covered.
- **Placeholder scan:** all steps carry real code/commands. Task 6 references token names to be confirmed against neighbors (explicit instruction, not a placeholder). Card-face status/due deferred with explicit rationale.
- **Type consistency:** `editableValue`/`startFieldEdit`/`saveField`/`editCardField`/`FIELD_EDITORS` names consistent across Tasks 3-5; `validate_field_edit`/`EDITABLE_FIELDS` consistent across Tasks 1-2; route + handler names match.
```
