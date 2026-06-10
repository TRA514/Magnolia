# Design: Inline native Markdown editor (Task Detail card)

**Date:** 2026-06-10
**Status:** Approved — proceeding to implementation plan
**Branch:** `feat/inline-markdown-editor`
**Merge authority:** merge to `main` when green + e2e-verified
**Source:** Claude Designer handoff (`Magnolia - native markdown editor.zip`) — `design_handoff_inline_markdown_editor/`

## Intent

Replace the "Open in Obsidian" hop on a task's `.md` output with an inline WYSIWYG
Markdown editor that slides in over the **left** task pane of the already-open split
workspace (the chat pane stays live on the right). Edits autosave silently; a quiet
"Saved" dot is the only confirmation. Obsidian survives as a low-prominence escape
hatch in an overflow menu — it is *demoted*, not removed everywhere.

The experience bar is high: faithful motion, token-driven theming across all six Moods,
and **no extraneous helper text or subtitles**. The chrome is back · filename · save-dot ·
overflow, and nothing else.

## Decisions locked in brainstorming

1. **Merge authority:** merge to `main` when green.
2. **Crepe delivery:** **vendor locally** under `ui/task-board/vendor/crepe/` (served as
   static files; works offline; no runtime CDN dependency). The import sits behind a
   one-line seam so swapping to CDN is trivial later. The styled-textarea fallback backstops
   either path.
3. **Activity tab stays read-only** — only the live task-detail tile becomes the inline
   editor. Activity rows (archived/done tasks) keep their current read-only "Open output"
   (Obsidian) behavior. `js/activity.js` is **not** modified.

## Alignment review (handoff vs. live code)

The prototype was checked out against older code. What lines up vs. what drifted:

**Lines up:** all helpers exist (`obsidianUri`, `escapeHtml`, `svgIcon` + the `doc`/`output`/
`obsidian`/`arrowRight` glyphs, `openTask`, `currentTaskId`, `closeModal`, `API`); `--spring`
is defined in `index.html`; the modal structure `#split-modal` → `.modal.task-pane` +
`.chat-pane` matches; `do_PUT` is already wired in the server router; all editor tokens
(`--surface(-hover)`, `--text(-muted/-dim)`, `--border(-soft)`, `--accent(-soft/-ink)`,
`--success`, `--danger`, `--font-serif/-sans`, `--mono`, `--r-btn`, `--ease`) resolve across
all six Moods (`--mono` is global in `magnolia.css`; `--accent-soft`/`--success-soft` are
derived in `index.html` `:root`).

**Drifted — must adapt, do NOT port verbatim:**
- The `.md` output tile is now rendered from an `artifacts[]` array as an
  `<a class="dt-artifact">` with live anatomy `dt-art-top` (icon + `dt-art-kind`),
  `dt-art-name`, `dt-art-path`, `dt-art-open`. The prototype's `.dt-review-cta` markup is
  stale. We special-case the `.md` artifact to render as a `<button class="dt-artifact
  dt-review">` calling `openOutputEditor(task.id)`, **keeping the live anatomy** and adding a
  `button.dt-artifact` reset (width/text-align/font/cursor). The Word `.docx` tile is untouched.
- `openTask` is `async function openTask(taskId, keepChat)` — `keepChat` is optional, so the
  handoff's `await openTask(taskId)` is compatible.
- No `/api/tasks/{id}/output` route exists yet — we add `GET` + `PUT`.
- `js/mock-api.js` is prototype-only and is never ported (live backend is real).

## Files

**New**
- `ui/task-board/js/markdown-editor.js` — overlay build/open/close, lazy editor load,
  formatting toolbar, debounced autosave, textarea fallback. IIFE; exposes
  `window.openOutputEditor`, `window.openTaskOutput`, `window.closeOutputEditor`.
- `ui/task-board/css/markdown-editor.css` — review tile (`.dt-review`), takeover overlay
  (`.dt-editor` + chrome), Crepe→Magnolia token bridge. **Token-only** (invariant #3).
- `ui/task-board/vendor/crepe/` — vendored Milkdown Crepe 7.5.0 self-contained ESM bundle +
  its two stylesheets.

**Modified**
- `index.html` — link `css/markdown-editor.css`; load `js/markdown-editor.js` after
  `js/tasks.js`. (No `position:relative` edit here — the overlay sets it on
  `#split-modal .task-pane` from the new CSS.)
- `js/tasks.js` — the `.md` artifact tile → inline-opening button (see drift note).
- `scripts/task_server.py` — add `GET` + `PUT /api/tasks/{id}/output` (+ handlers).

**Untouched:** `js/activity.js`, anything resembling `js/mock-api.js`.

## Backend contract

```
GET /api/tasks/{id}/output
    → 200 { path: string, format: "markdown", content: string }
    → 404 if the task has no agent_output, or it is not a .md path, or the file is missing
PUT /api/tasks/{id}/output
    body: { content: string }
    → 200 { ok: true, savedAt: <ISO> }
```

- Path comes from the task's existing `agent_output` frontmatter field (via
  `task_lib.read_task`).
- Resolve relative paths against `PM_OS_DIR` and `os.path.normpath`, **exactly like
  `handle_open_file`**, then assert the resolved path stays inside `PM_OS_DIR`
  (path-traversal guard) and ends with `.md`.
- `PUT` writes the file in place (UTF-8). This is a **local file write**, equivalent to how
  description/message edits already persist — *not* an external write, so **no Tier-2
  confirm** (invariant #5 does not apply). In-place edit of the user's own document is not
  artifact deletion, so invariant #6 is not triggered; git history remains the audit trail.
- Routes inserted **before** the generic `^/api/tasks/([^/]+)$` GET match so they win.

## Editor surface & toolbar

Body is Milkdown Crepe (ProseMirror WYSIWYG), lazy-loaded on first open with a centered
spinner ("Opening the document…"); on load failure a styled monospace `<textarea>` fallback
mounts and toolbar commands fall back to raw-markdown wrapping/prefixing.

**Toolbar strategy — to verify during build:** the handoff drives Crepe via *synthetic
keystrokes* because its CDN build exposed no command API. Since we vendor the same build, the
build's first editor task **verifies Crepe's actual public API**:
- If Crepe exposes a usable command/action API → the toolbar calls it directly (handoff's
  stated preference) and autosave uses the editor's real change subscription (drop the poll).
- If not → keep the documented synthetic-keystroke approach + the 2s reconciliation poll.

Toolbar groups (slim icon buttons, 28×28, thin separators): Bold/Italic/Strike/Code · H1/H2/H3 ·
Bullet/Ordered/Checklist/Quote · Link.

## Motion, autosave, theming

- **Open:** `opacity 0→1`, `scale .97→1`, `blur 10px→0` on `--spring` (mirrors the
  `.task-pane` materialize). **Close:** faster ease to `scale .985 / blur 2px / opacity 0`,
  node removed on `transitionend` with a 520ms safety timeout.
  `prefers-reduced-motion` collapses to a 120ms opacity fade.
- **Autosave:** any edit → `editing`, 750ms debounce; flush skips no-op (unchanged vs
  `lastSaved`), else `saving` → `PUT` → `saved`/`error`. Four token-colored states
  (`--text-dim`/`--accent` pulsing/`--success`/`--danger`).
- **Layering:** editor is its own layer above the modal. Esc and the Back button close
  *only* the editor (flushing any pending save). `window.closeModal` is wrapped to tear the
  editor down first so it never lingers.
- **Theme bridge:** map Crepe's `--crepe-*` tokens onto Magnolia tokens; pull Crepe's
  oversized type down to the app scale; headings take the serif display face; code blocks /
  inline code / blockquotes / tables ride the app surface tokens. **Token-only** — tracks
  every Mood automatically.

## State (single editor instance)

`editorTaskId` (also the race guard when switching tasks mid-load), `crepe` (or null on
fallback), `fallbackEl`, `docPath`, `lastSaved`, `saveTimer` (debounce), `savePoll` (reconcile).

## Testing & gates

- **Backend (pytest, `_FakeHandler` pattern from `test_quick_add_route.py`):** GET returns
  `{path, content}` for a `.md` task; PUT round-trips to disk and updates content; 404 on a
  task with no `agent_output` and on a non-`.md` output; path-traversal attempt rejected.
- **Frontend:** no JS test harness — verify via Chrome headless across all six Moods (visual
  pass): the review tile, takeover open/close motion, toolbar commands, the four save states,
  and the textarea fallback.
- **Green gates before every code commit (invariant #2):** `python3 -m pytest` ·
  `python3 scripts/card_schema.py` · `python3 -m pytest tests/test_engine_no_jay.py`.

## Non-goals (YAGNI)

- No build system / bundler added to the board.
- No read-only editor mode (Activity stays as-is).
- No new card type, worker, or adapter — this is a UI + two-endpoint feature.
- No collaborative editing, version history UI, or conflict resolution beyond in-place save.
