# Inline Markdown Editor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the "Open in Obsidian" hop on a task's `.md` output with an inline WYSIWYG Markdown editor that slides in over the left task pane, autosaving silently to the artifact file.

**Architecture:** A new front-end module (`markdown-editor.js`) builds a takeover overlay inside the existing `#split-modal .task-pane`, lazy-mounts a vendored Milkdown Crepe editor (styled-textarea fallback), and autosaves through two new backend endpoints (`GET`/`PUT /api/tasks/{id}/output`) that read/write the task's existing `agent_output` markdown file. The `.md` output tile in `tasks.js` becomes an inline-opening button; Obsidian is demoted to the editor's overflow menu. All styling is token-only so it tracks every Mood.

**Tech Stack:** Vanilla HTML/CSS/JS front end (no build step), Python `http.server` backend (`scripts/task_server.py`, `task_lib`), Milkdown Crepe 7.5.0 (vendored), pytest.

**Design doc:** `docs/plans/2026-06-10-inline-markdown-editor-design.md`

**Green gates (run before EVERY code commit — invariant #2):**
```bash
python3 -m pytest -q
python3 scripts/card_schema.py          # expect "registry.json OK"
python3 -m pytest tests/test_engine_no_jay.py -q
```

**Conventions:** branch is `feat/inline-markdown-editor` (already created off `main`). End every commit body with:
```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## Task 1: Backend — path-resolution helper with traversal guard

**Files:**
- Modify: `scripts/task_server.py` (add helper near the other module helpers, after `_read_request_body`, ~line 163)
- Test: `tests/test_output_route.py` (Create)

**Step 1: Write the failing test**

```python
"""GET/PUT /api/tasks/{id}/output — read & write a task's .md artifact for the
inline editor. Mirrors test_quick_add_route's _FakeHandler pattern. The output
file lives under a temp PM_OS_DIR (monkeypatched) so writes never touch the real tree."""
import io
import json
import os
import pytest


class _FakeHandler:
    def __init__(self, body=None):
        self._body = json.dumps(body).encode("utf-8") if body is not None else b""
        self.headers = {"Content-Length": str(len(self._body))}
        self.status = None
        self._chunks = []

    @property
    def rfile(self):
        return io.BytesIO(self._body)

    def send_response(self, s): self.status = s
    def send_header(self, *a): pass
    def end_headers(self): pass
    @property
    def wfile(self): return self
    def write(self, b): self._chunks.append(b)
    def json(self): return json.loads(b"".join(self._chunks).decode("utf-8"))


@pytest.fixture
def srv(tasks_root, monkeypatch):
    """task_server with task_lib + PM_OS_DIR pointed at the temp tree."""
    import task_server
    monkeypatch.setattr(task_server, "PM_OS_DIR", tasks_root)
    return task_server


def _seed_task_with_output(tasks_root, rel_path, content):
    """Create an agent task whose agent_output points at rel_path, and write that file."""
    import task_lib
    t = task_lib.create_task("Competitive landscape brief", queue="agent", domain="product")
    task_lib.update_task(t["id"], changes={"agent_output": rel_path})
    abspath = os.path.join(tasks_root, rel_path)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, "w", encoding="utf-8") as f:
        f.write(content)
    return t["id"]


def test_resolve_output_path_rejects_traversal(srv):
    # Escapes PM_OS_DIR → None
    assert srv._resolve_output_path("../../etc/passwd.md") is None
    # Not markdown → None
    assert srv._resolve_output_path("product/agent-output/note.txt") is None
    # Empty → None
    assert srv._resolve_output_path("") is None
    # Valid relative .md → absolute path inside PM_OS_DIR
    got = srv._resolve_output_path("product/agent-output/x.md")
    assert got is not None and got.endswith("product/agent-output/x.md")
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_output_route.py::test_resolve_output_path_rejects_traversal -v`
Expected: FAIL — `AttributeError: module 'task_server' has no attribute '_resolve_output_path'`

**Step 3: Write minimal implementation**

Add after `_read_request_body` (~line 163) in `scripts/task_server.py`:

```python
def _resolve_output_path(rel):
    """Resolve a task's agent_output to an absolute .md path inside PM_OS_DIR.

    Returns the absolute path, or None when there is no path, it is not a .md
    file, or it would escape PM_OS_DIR (path-traversal guard). Mirrors
    handle_open_file's PM_OS_DIR resolution, plus the containment check.
    """
    rel = (rel or "").strip()
    if not rel or not rel.endswith(".md"):
        return None
    base = os.path.realpath(PM_OS_DIR)
    candidate = os.path.realpath(rel if os.path.isabs(rel) else os.path.join(base, rel))
    if candidate != base and not candidate.startswith(base + os.sep):
        return None
    return candidate
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_output_route.py::test_resolve_output_path_rejects_traversal -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/task_server.py tests/test_output_route.py
git commit -m "feat(md-editor): output path resolver with traversal guard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Backend — `handle_get_output`

**Files:**
- Modify: `scripts/task_server.py` (add handler after `handle_get_task`, ~line 702)
- Test: `tests/test_output_route.py`

**Step 1: Write the failing test** (append to the file)

```python
def test_get_output_returns_content(srv, tasks_root):
    tid = _seed_task_with_output(tasks_root, "product/agent-output/comp.md",
                                 "# Competitive Landscape\n\nFour vendors dominate.\n")
    h = _FakeHandler()
    srv.handle_get_output(h, tid)
    assert h.status == 200
    resp = h.json()
    assert resp["format"] == "markdown"
    assert resp["path"] == "product/agent-output/comp.md"
    assert "Four vendors dominate." in resp["content"]


def test_get_output_404_when_no_agent_output(srv, tasks_root):
    import task_lib
    t = task_lib.create_task("No output yet", queue="agent")
    h = _FakeHandler()
    srv.handle_get_output(h, t["id"])
    assert h.status == 404


def test_get_output_404_when_not_markdown(srv, tasks_root):
    import task_lib
    t = task_lib.create_task("Link output", queue="agent")
    task_lib.update_task(t["id"], changes={"agent_output": "https://example.com/x"})
    h = _FakeHandler()
    srv.handle_get_output(h, t["id"])
    assert h.status == 404
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_output_route.py -k get_output -v`
Expected: FAIL — `handle_get_output` not defined.

**Step 3: Write minimal implementation**

Add after `handle_get_task` (~line 702) in `scripts/task_server.py`:

```python
def handle_get_output(handler, task_id):
    """GET /api/tasks/{id}/output — return the task's .md artifact for inline editing."""
    try:
        task_data = task_lib.read_task(task_id)
    except FileNotFoundError:
        _error_response(handler, f"Task {task_id} not found", status=404)
        return
    except Exception as e:
        _error_response(handler, f"Failed to read task: {e}", status=500)
        return

    rel = str(task_data["frontmatter"].get("agent_output") or "")
    filepath = _resolve_output_path(rel)
    if filepath is None:
        _error_response(handler, "Task has no editable markdown output", status=404)
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        _error_response(handler, f"Output file not found: {rel.strip()}", status=404)
        return
    except Exception as e:
        _error_response(handler, f"Failed to read output: {e}", status=500)
        return
    _json_response(handler, {"path": rel.strip(), "format": "markdown", "content": content})
```

**Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_output_route.py -k get_output -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add scripts/task_server.py tests/test_output_route.py
git commit -m "feat(md-editor): GET /api/tasks/{id}/output handler

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Backend — `handle_save_output`

**Files:**
- Modify: `scripts/task_server.py` (add handler after `handle_get_output`)
- Test: `tests/test_output_route.py`

**Step 1: Write the failing test** (append)

```python
def test_put_output_roundtrips_to_disk(srv, tasks_root):
    tid = _seed_task_with_output(tasks_root, "product/agent-output/comp.md", "# Old\n")
    h = _FakeHandler({"content": "# New title\n\nEdited body.\n"})
    srv.handle_save_output(h, tid)
    assert h.status == 200
    resp = h.json()
    assert resp["ok"] is True
    assert "savedAt" in resp
    import os
    with open(os.path.join(tasks_root, "product/agent-output/comp.md"), encoding="utf-8") as f:
        assert f.read() == "# New title\n\nEdited body.\n"


def test_put_output_400_when_content_missing(srv, tasks_root):
    tid = _seed_task_with_output(tasks_root, "product/agent-output/comp.md", "# Old\n")
    h = _FakeHandler({})
    srv.handle_save_output(h, tid)
    assert h.status == 400


def test_put_output_404_when_not_markdown(srv, tasks_root):
    import task_lib
    t = task_lib.create_task("Link output", queue="agent")
    task_lib.update_task(t["id"], changes={"agent_output": "https://example.com/x"})
    h = _FakeHandler({"content": "nope"})
    srv.handle_save_output(h, t["id"])
    assert h.status == 404
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_output_route.py -k put_output -v`
Expected: FAIL — `handle_save_output` not defined.

**Step 3: Write minimal implementation**

Confirm `from datetime import datetime, timezone` is importable in the module (it imports `datetime` already — verify near the top imports; if only `import datetime`, use `datetime.datetime.now(datetime.timezone.utc)` instead). Add after `handle_get_output`:

```python
def handle_save_output(handler, task_id):
    """PUT /api/tasks/{id}/output — persist edited markdown back to the artifact file."""
    try:
        task_data = task_lib.read_task(task_id)
    except FileNotFoundError:
        _error_response(handler, f"Task {task_id} not found", status=404)
        return
    except Exception as e:
        _error_response(handler, f"Failed to read task: {e}", status=500)
        return

    rel = str(task_data["frontmatter"].get("agent_output") or "")
    filepath = _resolve_output_path(rel)
    if filepath is None:
        _error_response(handler, "Task has no editable markdown output", status=404)
        return
    try:
        body = _read_request_body(handler)
    except (json.JSONDecodeError, ValueError) as e:
        _error_response(handler, f"Invalid JSON body: {e}", status=400)
        return
    content = body.get("content")
    if content is None:
        _error_response(handler, "Missing 'content' field", status=400)
        return
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        _error_response(handler, f"Failed to write output: {e}", status=500)
        return
    _json_response(handler, {"ok": True, "savedAt": _utc_now_iso()})
```

If a UTC-ISO helper does not already exist, add a tiny one near the other helpers (check first with `grep -n "def _utc_now_iso\|utcnow\|now(timezone" scripts/task_server.py`; reuse whatever timestamp idiom the file already uses for activity entries):

```python
def _utc_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
```

**Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_output_route.py -k put_output -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add scripts/task_server.py tests/test_output_route.py
git commit -m "feat(md-editor): PUT /api/tasks/{id}/output handler

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Backend — wire the routes into the router

**Files:**
- Modify: `scripts/task_server.py` (`_route_request`, insert BEFORE the generic `^/api/tasks/([^/]+)$` GET match at ~line 2302)
- Test: `tests/test_output_route.py`

**Step 1: Write the failing test** (append — an integration check through the router via a live server thread mirrors test patterns elsewhere, but the lighter check is asserting the route table matches; here, verify the match-ordering by unit-calling `_route_request` is overkill. Instead, assert the regex placement indirectly with a routing smoke test using a real server.)

Keep it simple — add a routing smoke test that boots the handler's `_route_request` with a fake handler is awkward (it needs a real socket). Instead, assert the two regexes are present and ordered before the generic GET by reading the source:

```python
def test_output_routes_registered_before_generic_get():
    import re
    src = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "task_server.py"),
               encoding="utf-8").read()
    out_idx = src.index('/api/tasks/([^/]+)/output$')
    generic_idx = src.index('^/api/tasks/([^/]+)$')
    assert out_idx < generic_idx, "output route must be matched before the generic task GET"
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_output_route.py -k routes_registered -v`
Expected: FAIL — substring `/api/tasks/([^/]+)/output$` not found.

**Step 3: Write minimal implementation**

In `_route_request`, immediately before the `# Match /api/tasks/{id}` generic GET block (~line 2302), add:

```python
        # Match /api/tasks/{id}/output — GET reads, PUT writes the .md artifact.
        match = re.match(r"^/api/tasks/([^/]+)/output$", path)
        if match and method in ("GET", "PUT"):
            task_id = _parse_task_id(match.group(1))
            if task_id is None:
                _error_response(self, "Invalid task ID format", status=400)
            elif method == "GET":
                handle_get_output(self, task_id)
            else:
                handle_save_output(self, task_id)
            return True
```

Also add `PUT` to the `do_OPTIONS` allow-methods header (find `Access-Control-Allow-Methods` in `do_OPTIONS`, ~line 2367) so the value reads `"GET, POST, PUT, OPTIONS"`.

**Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_output_route.py -v` (all output tests)
Expected: PASS (all)

**Step 5: Run the full gates, then commit**

```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
git add scripts/task_server.py tests/test_output_route.py
git commit -m "feat(md-editor): route GET/PUT /api/tasks/{id}/output

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Vendor Milkdown Crepe 7.5.0 (verification-driven, no test)

**Files:**
- Create: `ui/task-board/vendor/crepe/crepe.bundle.js`
- Create: `ui/task-board/vendor/crepe/common.css`
- Create: `ui/task-board/vendor/crepe/frame.css`
- Create: `ui/task-board/vendor/crepe/README.md` (provenance: version, source URLs, date, regeneration command)

**Step 1: Fetch a self-contained ESM bundle + its stylesheets**

The board has no bundler, so produce ONE self-contained ESM file. Try, in order:
1. `curl -L 'https://esm.sh/@milkdown/crepe@7.5.0?bundle&target=es2020' -o ui/task-board/vendor/crepe/crepe.bundle.js`
   then inspect the head: `head -5 ui/task-board/vendor/crepe/crepe.bundle.js`. If it contains bare
   `import ... from "https://esm.sh/..."` lines (i.e. not fully inlined), it is NOT self-contained.
2. If not self-contained, build it locally with esbuild (one-time dev tool, not a runtime build):
   ```bash
   cd /tmp && npm i @milkdown/crepe@7.5.0 && \
   npx esbuild --bundle --format=esm --target=es2020 \
     --outfile=crepe.bundle.js <(echo "export { Crepe } from '@milkdown/crepe';")
   ```
   Copy the result to `ui/task-board/vendor/crepe/crepe.bundle.js`.
3. Fetch the two stylesheets:
   ```bash
   curl -L 'https://esm.sh/@milkdown/crepe@7.5.0/theme/common/style.css' -o ui/task-board/vendor/crepe/common.css
   curl -L 'https://esm.sh/@milkdown/crepe@7.5.0/theme/frame.css' -o ui/task-board/vendor/crepe/frame.css
   ```

**Step 2: Verify the bundle loads + what API it exposes**

Write a throwaway probe `ui/task-board/vendor/crepe/_probe.html` that imports the bundle and a tiny doc, mounts it, and logs the keys of the Crepe instance + whether `crepe.editor`/`crepe.action`/command helpers exist. Serve via the running dev board (`http://localhost:8743/vendor/crepe/_probe.html`) and open with Chrome headless (see `visual-pass-technique` memory). Record findings in the vendor README:
- Does `new Crepe({root, defaultValue})` + `await crepe.create()` work?
- Does `crepe.getMarkdown()` work?
- Is there a real command/action API (e.g. `crepe.editor.action(...)`) and a change/update listener? — this decides Task 7's toolbar + autosave strategy.

Delete `_probe.html` before committing.

**Step 3: Commit the vendored library**

```bash
git add ui/task-board/vendor/crepe/
git commit -m "chore(md-editor): vendor Milkdown Crepe 7.5.0 (no-build, offline)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> If a self-contained bundle proves infeasible without heavy tooling, fall back to the CDN
> lazy-import (the prototype's approach) and note it in the vendor README + the design doc's
> decisions. The editor module (Task 6) keeps the import behind a one-line `CREPE_ESM` seam
> either way, and the textarea fallback backstops both.

---

## Task 6: Front end — `markdown-editor.js` (the editor module)

**Files:**
- Create: `ui/task-board/js/markdown-editor.js`
- Reference (do not copy verbatim): handoff `design_handoff_inline_markdown_editor/markdown-editor.js`

This is a port-and-adapt of the handoff module. No JS unit harness exists, so correctness is proven by the e2e visual pass in Task 9. Build it faithfully with these REQUIRED adaptations:

**Step 1: Author the module**

Start from the handoff `markdown-editor.js` and change exactly these things:
1. **Import seam — vendored, not CDN.** Replace the `CREPE_ESM`/`CREPE_CSS` constants:
   ```js
   const CREPE_ESM = '/vendor/crepe/crepe.bundle.js';
   const CREPE_CSS = ['/vendor/crepe/common.css', '/vendor/crepe/frame.css'];
   ```
   (If Task 5 fell back to CDN, use the esm.sh URLs instead — this is the one-line seam.)
2. **Toolbar + autosave per Task 5's findings.** If Crepe exposes a real command/action API and
   a change listener, use them (call commands directly; subscribe for autosave and DROP the 2s
   poll). Otherwise keep the handoff's synthetic-keystroke `runToolCommand` + `input` listener +
   2s reconciliation poll exactly as written, with the explanatory comments retained.
3. Keep everything else faithful: `buildOverlay`, the four-state `setSaveState`, `scheduleSave`/
   `flushSave` (750ms debounce, no-op skip), `openOutputEditor`/`openTaskOutput`/
   `closeOutputEditor`, the `closeModal` wrap, Esc handling, the textarea `mountFallback`, and the
   `editorTaskId` race guard.
4. The overlay markup uses `svgIcon('doc')`, `svgIcon('obsidian')`, `svgIcon('output')` — all
   exist in the live `icons.js`. Leave them.

**Step 2: Lint-check (syntax only)**

Run: `node --check ui/task-board/js/markdown-editor.js`
Expected: no output (valid syntax).

**Step 3: Commit**

```bash
git add ui/task-board/js/markdown-editor.js
git commit -m "feat(md-editor): inline editor module (overlay, autosave, fallback)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Front end — `markdown-editor.css` (token-only)

**Files:**
- Create: `ui/task-board/css/markdown-editor.css`
- Reference: handoff `design_handoff_inline_markdown_editor/markdown-editor.css`

**Step 1: Author the stylesheet**

Port the handoff CSS verbatim with these checks:
1. It is **token-only** — no literal colors/radii/transitions except the editor-local literals the
   handoff documents (28px toolbar buttons, 7px save dot, menu radius/shadow, backdrop blur,
   editor body padding, base font 14px/1.7). Every color/surface uses a `var(--…)` confirmed to
   exist in all six Moods.
2. Keep `#split-modal .task-pane { position: relative; }` — this is how the overlay positions
   (no `index.html` edit needed for it).
3. Section 1's tile rules must compose onto the LIVE `.dt-artifact` (styled in `index.html`):
   keep `button.dt-artifact { width:100%; text-align:left; font-family:inherit; cursor:pointer; }`
   (the reset that lets a `<button>` wear the tile that was built for an `<a>`), plus the
   `.dt-review` accent treatment. Drop any prototype rule that references markup the live tile
   doesn't have.

**Step 2: Sanity-check token-only**

Run (expect NO hits other than the documented editor-local literals):
```bash
grep -nE '#[0-9a-fA-F]{3,8}|rgb\(|hsl\(' ui/task-board/css/markdown-editor.css
```
The only allowed matches are inside `rgba(0,0,0,…)` shadow/backdrop literals the design calls out.
Any themed color must be a `var(--…)`.

**Step 3: Commit**

```bash
git add ui/task-board/css/markdown-editor.css
git commit -m "feat(md-editor): token-only styles + Crepe theme bridge

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Front end — wire assets + convert the `.md` tile

**Files:**
- Modify: `ui/task-board/index.html` (CSS link ~line 1261; script load ~line 1395)
- Modify: `ui/task-board/js/tasks.js` (the artifact array + render loop, lines 89–114)

**Step 1: Link the stylesheet and load the module**

In `index.html`, after `<link rel="stylesheet" href="/css/magnolia.css">` (~line 1261) add:
```html
<link rel="stylesheet" href="/css/markdown-editor.css">
```
After `<script src="/js/tasks.js"></script>` (~line 1395) add:
```html
<script src="/js/markdown-editor.js"></script>
```

**Step 2: Convert the `.md` output tile to an inline-opening button**

In `js/tasks.js`, the `.md` branch (line 92) currently pushes an Obsidian `<a>` artifact. Change
that pushed object so the markdown artifact opens the editor inline, and make the render loop emit
a `<button>` for it while leaving the Word `<a>` untouched.

Change line 92's pushed object to mark it inline and carry the open call + a "Review & edit" label:
```js
        artifacts.push({ icon: 'doc', cls: 'dt-review', kind: 'Markdown', name: v.split('/').pop(), path: shortArtifactPath(v), inline: true, taskId: task.id, label: 'Review & edit', external: false });
```
Then in the render loop (lines 105–113), branch on `a.inline`:
```js
      artifacts.forEach(a => {
        const ext = a.external ? ' target="_blank" rel="noopener"' : '';
        const href = a.href ? ` href="${escapeHtml(a.href)}"` : '';
        const tag = a.inline ? 'button' : 'a';
        const attrs = a.inline
          ? ` type="button" onclick="event.stopPropagation(); openOutputEditor('${a.taskId}')"`
          : `${href}${ext} onclick="event.stopPropagation()"`;
        html += `<${tag} class="dt-artifact ${a.cls}"${attrs}>`;
        html += `<span class="dt-art-top"><span class="dt-art-icon">${svgIcon(a.icon)}</span><span class="dt-art-kind">${escapeHtml(a.kind)}</span></span>`;
        html += `<span class="dt-art-name">${escapeHtml(a.name)}</span>`;
        html += `<span class="dt-art-path">${escapeHtml(a.path)}</span>`;
        if (a.label) html += `<span class="dt-art-open">${escapeHtml(a.label)}${svgIcon(a.inline ? 'arrowRight' : 'output')}</span>`;
        html += `</${tag}>`;
      });
```
(Obsidian is no longer the tile's destination — it moves to the editor's overflow menu, built in
`markdown-editor.js`. The Word `.docx` tile, pushed elsewhere, is unchanged.)

**Step 3: Syntax check + verify no stray Obsidian tile remains**

```bash
node --check ui/task-board/js/tasks.js
grep -n "Open in Obsidian" ui/task-board/js/tasks.js   # expect: no matches (moved to the editor menu)
```

**Step 4: Commit**

```bash
git add ui/task-board/index.html ui/task-board/js/tasks.js
git commit -m "feat(md-editor): open .md output inline; load editor assets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: End-to-end verification across all six Moods

**Files:** none (verification only). Uses the running dev board on `localhost:8743` and Chrome headless (`visual-pass-technique` memory).

**Step 1: Restart the dev board so it picks up new static files + server routes**

The server caches Python modules; restart it (kill the process bound to 8743, relaunch
`python3 scripts/task_server.py`). Confirm `curl -s localhost:8743/vendor/crepe/crepe.bundle.js -o /dev/null -w '%{http_code}'` returns `200`.

**Step 2: Find (or seed) a task with a `.md` `agent_output`**

`curl -s localhost:8743/api/tasks | python3 -c "import sys,json; [print(t['id']) for t in json.load(sys.stdin) if str(t.get('agent_output','')).endswith('.md')]"`.
If none exist, seed one via `task_lib` against the real tree pointing at a small fixture `.md`
under `datasets/product/agent-output/` (create the file too).

**Step 3: Visually verify the full flow in Chrome headless, in EACH Mood**

For each of `organic, modafinil, breathe, vantaca, karesansui, sugarmagnolia`:
- Open the task → the output tile reads "Review & edit" and looks like the primary action.
- Click it → the editor takes over the LEFT pane with the scale+blur spring; chat stays on the right.
- Top bar shows back · filename · "Saved" dot · overflow. No subtitles, no helper text.
- Type → dot goes "Editing…" → "Saving…" → "Saved"; confirm the file on disk changed (`PUT` landed).
- Toolbar: bold, a heading, a list, a checklist, a link all work.
- Overflow menu: "Open in Obsidian" (href set) + "Copy markdown".
- Esc and Back close only the editor (chat + task remain); closing the whole modal tears it down.
- Editor body palette/typography matches the active Mood (token bridge working).
Capture a screenshot per Mood of the open editor; eyeball contrast/spacing.

**Step 4: Verify the textarea fallback**

Temporarily point `CREPE_ESM` at a bad path (or block the vendor file), reload, open a doc →
the monospace textarea mounts, toolbar still wraps/prefixes markdown, autosave still works. Revert.

**Step 5: Final gate sweep + commit any fixes found**

```bash
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
```
Commit any fixes surfaced by the visual pass with a `fix(md-editor): …` message and the trailer.

---

## Done criteria
- All gates green; `tests/test_output_route.py` passes.
- Editor opens inline over the left pane, autosaves to the artifact file, falls back to a textarea,
  and wears every Mood — verified visually across all six.
- Obsidian is demoted to the editor's overflow menu; the task-detail `.md` tile opens inline.
  Activity tab unchanged.
- No new helper text/subtitles; chrome is back · filename · save-dot · overflow only.
- Ready to merge to `main` per the kickoff merge authority.
