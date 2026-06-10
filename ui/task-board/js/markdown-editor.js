// markdown-editor.js — inline native Markdown review & edit.
//
// Replaces the old "Open in Obsidian" hop. When you open the output document
// from a task's detail pane, the document slides in over the LEFT pane of the
// split workspace (the chat stays on the right) as a writing-first WYSIWYG
// surface — Milkdown Crepe, lazy-loaded the moment a note is opened. Edits
// autosave (debounced) back through PUT /api/tasks/:id/output; a quiet "Saved"
// indicator is the only confirmation. Power users keep an Obsidian path tucked
// in the overflow menu.
//
// Depends on globals: API, escapeHtml, svgIcon, obsidianUri, openTask,
// toast (all from core.js / icons.js / tasks.js).

(function () {
  // Crepe is vendored locally (no CDN at runtime) so the board works offline
  // and is reproducible. The bundle is a single self-contained ESM module so
  // Crepe's internal @milkdown/* packages share ONE instance (otherwise the
  // shared "SchemaReady" timer registry mismatches and create() throws).
  //
  // SEAM: to swap back to a CDN, change this one line to e.g.
  //   `https://esm.sh/@milkdown/crepe@7.5.0?bundle`
  const CREPE_ESM = '/vendor/crepe/crepe.bundle.js';
  const CREPE_CSS = ['/vendor/crepe/common.css', '/vendor/crepe/frame.css'];

  let crepe = null;          // live Crepe instance (or null when using fallback)
  let fallbackEl = null;     // <textarea> if Crepe couldn't load
  let editorTaskId = null;   // task whose output is open
  let docPath = '';          // artifact path (for the Obsidian link + filename)
  let saveTimer = null;
  let savePoll = null;       // safety poll for edits that don't emit DOM input
  let lastSaved = '';        // last persisted markdown, to skip no-op saves
  let crepeImportPromise = null;
  let menuClickHandler = null; // the one document click handler that dismisses the overflow menu
  let saving = false;        // true while a PUT is in flight, to serialize saves

  // ── CSS injection (once) ─────────────────────────────────────────────
  function ensureCrepeCss() {
    if (document.getElementById('crepe-css-0')) return;
    CREPE_CSS.forEach((href, i) => {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = href;
      link.id = `crepe-css-${i}`;
      document.head.appendChild(link);
    });
  }

  function loadCrepe() {
    if (!crepeImportPromise) {
      ensureCrepeCss();
      crepeImportPromise = import(CREPE_ESM);
    }
    return crepeImportPromise;
  }

  // ── Build the takeover overlay inside the left task pane ─────────────
  function buildOverlay(taskPane) {
    let ov = taskPane.querySelector('.dt-editor');
    if (ov) return ov;
    ov = document.createElement('div');
    ov.className = 'dt-editor';
    ov.innerHTML = `
      <div class="dte-bar">
        <button class="dte-back" type="button" aria-label="Back to task">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 3.5 5.5 8l4.5 4.5"/></svg>
          <span>Task</span>
        </button>
        <div class="dte-doc">
          <span class="dte-doc-icon">${svgIcon('doc')}</span>
          <span class="dte-doc-name"></span>
        </div>
        <div class="dte-spacer"></div>
        <span class="dte-save" data-state="saved">
          <span class="dte-save-dot"></span>
          <span class="dte-save-text">Saved</span>
        </span>
        <div class="dte-overflow">
          <button class="dte-of-btn" type="button" aria-label="More actions" aria-haspopup="true" aria-expanded="false">
            <svg viewBox="0 0 16 16" fill="currentColor" stroke="none"><circle cx="3.4" cy="8" r="1.25"/><circle cx="8" cy="8" r="1.25"/><circle cx="12.6" cy="8" r="1.25"/></svg>
          </button>
          <div class="dte-menu" role="menu">
            <a class="dte-menu-item dte-obsidian" role="menuitem" target="_blank" rel="noopener">${svgIcon('obsidian')}<span>Open in Obsidian</span></a>
            <button class="dte-menu-item dte-copy" type="button" role="menuitem">${svgIcon('output')}<span>Copy markdown</span></button>
          </div>
        </div>
      </div>
      <div class="dte-toolbar" role="toolbar" aria-label="Formatting">
        <button class="dte-tool" type="button" data-cmd="bold" title="Bold (⌘B)" aria-label="Bold"><span class="dte-ico-t" style="font-weight:800">B</span></button>
        <button class="dte-tool" type="button" data-cmd="italic" title="Italic (⌘I)" aria-label="Italic"><span class="dte-ico-t" style="font-style:italic;font-family:var(--font-serif)">I</span></button>
        <button class="dte-tool" type="button" data-cmd="strike" title="Strikethrough" aria-label="Strikethrough"><span class="dte-ico-t" style="text-decoration:line-through">S</span></button>
        <button class="dte-tool" type="button" data-cmd="code" title="Inline code" aria-label="Inline code"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5.5 5 2.5 8l3 3M10.5 5l3 3-3 3"/></svg></button>
        <span class="dte-tsep"></span>
        <button class="dte-tool" type="button" data-cmd="h1" title="Heading 1" aria-label="Heading 1"><span class="dte-ico-t">H1</span></button>
        <button class="dte-tool" type="button" data-cmd="h2" title="Heading 2" aria-label="Heading 2"><span class="dte-ico-t">H2</span></button>
        <button class="dte-tool" type="button" data-cmd="h3" title="Heading 3" aria-label="Heading 3"><span class="dte-ico-t">H3</span></button>
        <span class="dte-tsep"></span>
        <button class="dte-tool" type="button" data-cmd="bullet" title="Bulleted list" aria-label="Bulleted list"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="3" cy="4.4" r="1" fill="currentColor" stroke="none"/><circle cx="3" cy="8" r="1" fill="currentColor" stroke="none"/><circle cx="3" cy="11.6" r="1" fill="currentColor" stroke="none"/><path d="M6.5 4.4h7M6.5 8h7M6.5 11.6h7"/></svg></button>
        <button class="dte-tool" type="button" data-cmd="ordered" title="Numbered list" aria-label="Numbered list"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6.5 4.4h7M6.5 8h7M6.5 11.6h7"/><text x="0.6" y="5.8" font-size="4.6" fill="currentColor" stroke="none" style="font-family:var(--mono,monospace)">1</text><text x="0.6" y="9.6" font-size="4.6" fill="currentColor" stroke="none" style="font-family:var(--mono,monospace)">2</text><text x="0.6" y="13.4" font-size="4.6" fill="currentColor" stroke="none" style="font-family:var(--mono,monospace)">3</text></svg></button>
        <button class="dte-tool" type="button" data-cmd="quote" title="Quote" aria-label="Quote"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3.4 4.4v7.2"/><path d="M6.6 5.4h7M6.6 8h7M6.6 10.6h4.4"/></svg></button>
        <span class="dte-tsep"></span>
        <button class="dte-tool" type="button" data-cmd="link" title="Link" aria-label="Link"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6.8 9.2a2.4 2.4 0 0 0 3.4 0l2-2a2.4 2.4 0 1 0-3.4-3.4l-1 1"/><path d="M9.2 6.8a2.4 2.4 0 0 0-3.4 0l-2 2a2.4 2.4 0 1 0 3.4 3.4l1-1"/></svg></button>
      </div>
      <div class="dte-scroll">
        <div class="dte-surface"></div>
        <div class="dte-loading"><span class="dte-spin"></span><span>Opening the document…</span></div>
      </div>`;
    taskPane.appendChild(ov);

    ov.querySelector('.dte-back').addEventListener('click', closeOutputEditor);

    // Overflow menu
    const ofBtn = ov.querySelector('.dte-of-btn');
    const menu = ov.querySelector('.dte-menu');
    ofBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = menu.classList.toggle('open');
      ofBtn.setAttribute('aria-expanded', String(open));
    });
    // One document listener to dismiss the menu; stored module-level so
    // destroyEditor() can remove it on close (no per-open accumulation).
    menuClickHandler = () => { menu.classList.remove('open'); ofBtn.setAttribute('aria-expanded', 'false'); };
    document.addEventListener('click', menuClickHandler);
    ov.querySelector('.dte-copy').addEventListener('click', () => {
      const md = getMarkdown();
      if (navigator.clipboard) navigator.clipboard.writeText(md).catch(() => {});
      menu.classList.remove('open');
    });

    // Formatting toolbar. mousedown→preventDefault keeps the editor's selection
    // intact when a button is pressed; click runs the command.
    const toolbar = ov.querySelector('.dte-toolbar');
    toolbar.addEventListener('mousedown', (e) => { if (e.target.closest('.dte-tool')) e.preventDefault(); });
    toolbar.addEventListener('click', (e) => { const b = e.target.closest('.dte-tool'); if (b) runToolCommand(b.dataset.cmd); });
    return ov;
  }

  // ── Formatting commands ──────────────────────────────────────────────
  // Crepe is a sealed prebuilt bundle — its Milkdown command API can't be reached
  // from outside (separately-imported commands are different instances). So the
  // toolbar drives the editor the way a person does: dispatching the exact
  // keyboard shortcuts Crepe's keymap binds (verified against the bundle). This
  // is reliable; inserting raw markdown and hoping an input rule fires is not.
  // Crepe's bindings: Mod-b bold · Mod-i italic · Mod-Alt-x strike · Mod-e inline
  // code · Mod-Alt-1..3 H1-3 · Mod-Alt-8 bullet · Mod-Alt-7 ordered ·
  // Mod-Shift-b quote · Mod-k link (opens Crepe's own in-app link tooltip).
  const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '');
  function fireKey(pm, key, opt) {
    const mod = IS_MAC ? { metaKey: true } : { ctrlKey: true };
    const code = (/^[0-9]$/.test(key) ? 'Digit' : 'Key') + key.toUpperCase();
    pm.dispatchEvent(new KeyboardEvent('keydown', {
      key, code, keyCode: key.toUpperCase().charCodeAt(0), which: key.toUpperCase().charCodeAt(0),
      bubbles: true, cancelable: true, ...mod, ...(opt || {}),
    }));
  }

  function runToolCommand(cmd) {
    // Fallback textarea path (Crepe unavailable).
    if (fallbackEl && !crepe) { runFallbackCommand(cmd); scheduleSave(); return; }
    const pm = document.querySelector('.dt-editor .ProseMirror');
    if (!pm) return;
    pm.focus();
    switch (cmd) {
      case 'bold':    fireKey(pm, 'b'); break;
      case 'italic':  fireKey(pm, 'i'); break;
      case 'strike':  fireKey(pm, 'x', { altKey: true }); break;
      case 'code':    fireKey(pm, 'e'); break;
      case 'h1':      fireKey(pm, '1', { altKey: true }); break;
      case 'h2':      fireKey(pm, '2', { altKey: true }); break;
      case 'h3':      fireKey(pm, '3', { altKey: true }); break;
      case 'bullet':  fireKey(pm, '8', { altKey: true }); break;
      case 'ordered': fireKey(pm, '7', { altKey: true }); break;
      case 'quote':   fireKey(pm, 'b', { shiftKey: true }); break;
      // Mod-k opens Crepe's own link tooltip — an in-app, themed input. No native
      // prompt(); the user types the URL right there. (Returns early: the tooltip
      // owns the rest of the flow and the autosave poll catches the edit.)
      case 'link':    fireKey(pm, 'k'); return;
    }
    scheduleSave();
  }

  // Fallback (plain textarea) equivalents — wrap or prefix the raw markdown.
  function runFallbackCommand(cmd) {
    const ta = fallbackEl; if (!ta) return;
    const s = ta.selectionStart, e = ta.selectionEnd, v = ta.value, sel = v.slice(s, e);
    const wrap = (b, a) => { ta.value = v.slice(0, s) + b + sel + a + v.slice(e); ta.selectionStart = s + b.length; ta.selectionEnd = e + b.length; };
    const prefix = (p) => { const ls = v.lastIndexOf('\n', s - 1) + 1; ta.value = v.slice(0, ls) + p + v.slice(ls); };
    const map = { bold: () => wrap('**', '**'), italic: () => wrap('_', '_'), strike: () => wrap('~~', '~~'),
      code: () => wrap('`', '`'), h1: () => prefix('# '), h2: () => prefix('## '), h3: () => prefix('### '),
      bullet: () => prefix('- '), ordered: () => prefix('1. '), quote: () => prefix('> '), check: () => prefix('- [ ] '),
      link: () => { const url = window.prompt('Link URL', 'https://'); if (url) wrap('[', `](${url})`); } };
    (map[cmd] || (() => {}))();
    ta.focus();
  }

  function setSaveState(state) {
    const el = document.querySelector('.dt-editor .dte-save');
    if (!el) return;
    el.dataset.state = state;
    const text = { saved: 'Saved', saving: 'Saving…', editing: 'Editing…', error: 'Save failed' }[state] || 'Saved';
    el.querySelector('.dte-save-text').textContent = text;
  }

  function getMarkdown() {
    if (crepe) { try { return crepe.getMarkdown(); } catch (_) { return lastSaved; } }
    if (fallbackEl) return fallbackEl.value;
    return lastSaved;
  }

  function scheduleSave() {
    setSaveState('editing');
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(flushSave, 750);
  }

  async function flushSave() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    if (!editorTaskId) return;
    // Serialize: if a PUT is already in flight, bail — the debounce/poll re-attempts.
    if (saving) return;
    const md = getMarkdown();
    if (md === lastSaved) { setSaveState('saved'); return; }
    setSaveState('saving');
    saving = true;
    try {
      const res = await fetch(`${API}/tasks/${editorTaskId}/output`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: md }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      lastSaved = md;
      setSaveState('saved');
    } catch (e) {
      setSaveState('error');
      // The editor may already be torn down (final save on close), so the
      // inline indicator can no-op — surface the failure via the global toast.
      if (typeof toast === 'function') toast('Couldn’t save your latest edit - please try again.');
    } finally {
      saving = false;
    }
  }

  // ── Open / close ─────────────────────────────────────────────────────
  async function openOutputEditor(taskId) {
    const taskPane = document.querySelector('#split-modal .task-pane');
    if (!taskPane) return;
    // Re-entrant-safe: tear down any stale editor/instance before building anew.
    if (editorTaskId) destroyEditor();
    editorTaskId = taskId;

    const ov = buildOverlay(taskPane);
    const surface = ov.querySelector('.dte-surface');
    const loading = ov.querySelector('.dte-loading');
    surface.innerHTML = '';
    loading.style.display = '';
    ov.querySelector('.dte-save').dataset.state = 'saved';
    ov.querySelector('.dte-save .dte-save-text').textContent = 'Saved';

    // Animate the takeover in (mirror the workspace blur+spring vocabulary).
    taskPane.classList.add('has-editor');
    void ov.offsetWidth; // commit hidden baseline
    requestAnimationFrame(() => ov.classList.add('is-open'));

    // Fetch the document. `exists` distinguishes a real (possibly empty) file
    // from one the task points at but that was never written.
    let content = '', path = '', exists = true;
    try {
      const res = await fetch(`${API}/tasks/${taskId}/output`);
      if (res.ok) { const data = await res.json(); content = data.content || ''; path = data.path || ''; exists = data.exists !== false; }
    } catch (_) {}
    docPath = path;
    lastSaved = content;

    // Filename + Obsidian link.
    const fname = path ? path.split('/').pop() : 'output.md';
    ov.querySelector('.dte-doc-name').textContent = fname;
    const obsLink = ov.querySelector('.dte-obsidian');
    if (obsLink && typeof obsidianUri === 'function' && path) obsLink.href = obsidianUri(path);

    // No file behind this task's output path — show an honest state instead of a
    // blank editable canvas (which would silently create a phantom file on edit).
    if (!exists) {
      loading.style.display = 'none';
      ov.querySelector('.dte-save').style.display = 'none';   // nothing to save
      surface.innerHTML = '<div class="dte-empty">This document couldn’t be found.</div>';
      return;
    }

    // Mount Crepe (lazy). Fall back to a styled textarea on any failure.
    try {
      const mod = await loadCrepe();
      // If the user closed/switched while Crepe was loading, bail. (Gate on the
      // task id only — NOT the is-open class: a warm/cached import can resolve
      // before the open-transition rAF runs, which would race us out.)
      if (editorTaskId !== taskId) return;
      const Crepe = mod.Crepe || (mod.default && mod.default.Crepe);
      if (!Crepe) throw new Error('Crepe export missing');
      crepe = new Crepe({ root: surface, defaultValue: content });
      await crepe.create();
      // Autosave. Crepe (v7) exposes no change event, so we watch the editor's
      // contenteditable for `input` (covers typing) and add a light poll to
      // catch toolbar / slash-menu edits that mutate via transactions only.
      surface.addEventListener('input', scheduleSave, true);
      if (savePoll) clearInterval(savePoll);
      savePoll = setInterval(() => {
        if (editorTaskId && getMarkdown() !== lastSaved) scheduleSave();
      }, 2000);
      loading.style.display = 'none';
    } catch (err) {
      console.warn('[markdown-editor] Crepe unavailable, using plain fallback:', err && err.message);
      crepe = null;
      mountFallback(surface, content);
      loading.style.display = 'none';
    }
  }

  function mountFallback(surface, content) {
    surface.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'dte-fallback';
    const ta = document.createElement('textarea');
    ta.className = 'dte-fallback-ta';
    ta.value = content;
    ta.spellcheck = false;
    ta.addEventListener('input', scheduleSave);
    wrap.appendChild(ta);
    surface.appendChild(wrap);
    fallbackEl = ta;
  }

  // ── Synchronous teardown (the one place state is released) ───────────
  // DRY: called by closeOutputEditor's transition teardown, the closeModal
  // wrap, and openOutputEditor's re-entrancy guard. Removes the single
  // overflow-menu document listener so it never accumulates across opens.
  function destroyEditor() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    if (savePoll) { clearInterval(savePoll); savePoll = null; }
    if (menuClickHandler) { document.removeEventListener('click', menuClickHandler); menuClickHandler = null; }
    if (crepe) { try { crepe.destroy(); } catch (_) {} crepe = null; }
    fallbackEl = null;
    editorTaskId = null;
    const ov = document.querySelector('.dt-editor');
    if (ov && ov.parentNode) ov.parentNode.removeChild(ov);
    const taskPane = document.querySelector('#split-modal .task-pane');
    if (taskPane) taskPane.classList.remove('has-editor');
  }

  function closeOutputEditor() {
    const ov = document.querySelector('.dt-editor');
    if (!ov) return;
    // Persist any pending edit before tearing down.
    flushSave();
    ov.classList.remove('is-open');
    ov.classList.add('is-closing');
    ov.addEventListener('transitionend', function onEnd(e) {
      if (e.target === ov && (e.propertyName === 'opacity' || e.propertyName === 'transform')) {
        ov.removeEventListener('transitionend', onEnd);
        destroyEditor();
      }
    });
    // Safety net if transitionend doesn't fire.
    setTimeout(destroyEditor, 520);
  }

  // ── Card-face / Activity entry: open the task, then jump into the editor ──
  async function openTaskOutput(taskId) {
    if (typeof openTask === 'function') {
      await openTask(taskId);
      // openTask reveals the workspace; let it settle, then slide the doc in.
      setTimeout(() => openOutputEditor(taskId), 240);
    } else {
      openOutputEditor(taskId);
    }
  }

  // Close the editor first when the whole modal closes (so it doesn't linger).
  const _origCloseModal = window.closeModal;
  window.closeModal = function () {
    if (document.querySelector('.dt-editor')) destroyEditor();
    if (typeof _origCloseModal === 'function') return _origCloseModal.apply(this, arguments);
  };

  // Esc closes the editor first (one layer at a time) without closing the modal.
  // Capture-phase + stopImmediatePropagation pre-empts app.js's bubble-phase
  // closeModal Esc handler, so one Esc closes one layer at a time (coupling).
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const ov = document.querySelector('.dt-editor.is-open');
      if (ov) { e.stopImmediatePropagation(); closeOutputEditor(); }
    }
  }, true);

  // Delegated tile-open: registered exactly ONCE for the page lifetime (not
  // per-open), so it never leaks. Reads the task id from the data-attribute the
  // tile renders — no JS-string interpolation in an inline onclick. Registered
  // in the CAPTURE phase: the tile's own onclick calls stopPropagation() (to
  // keep the click off parent card handlers), which would otherwise prevent a
  // bubble-phase document listener from ever seeing it. Capture runs first.
  document.addEventListener('click', (e) => {
    const btn = e.target.closest && e.target.closest('.dt-review[data-output-task]');
    if (btn) openOutputEditor(btn.dataset.outputTask);
  }, true);

  window.openOutputEditor = openOutputEditor;
  window.closeOutputEditor = closeOutputEditor;
  window.openTaskOutput = openTaskOutput;
})();
