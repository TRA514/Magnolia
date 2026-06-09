// quickadd.js — capture a task in plain language.
// A quiet + in the top bar (or the C key) opens one auto-focused box; you type a
// task in your own words, hit Enter, and it drops into the normal pipeline —
// parsed, classified, worker-matched, and dispatched server-side. The card
// landing in Now is the real confirmation; a gentle toast acknowledges receipt.
// Depends on globals from the board: API, fetchTasks, toast, svgIcon.

function openQuickAdd() {
  const overlay = document.getElementById('qa-overlay');
  const input = document.getElementById('qa-input');
  if (!overlay || !input || overlay.classList.contains('active')) return;
  overlay.classList.add('active');
  input.value = '';
  // focus on open so you start typing immediately
  try { input.focus({ preventScroll: true }); } catch (e) { input.focus(); }
  requestAnimationFrame(() => input.focus());
}

function closeQuickAdd() {
  const overlay = document.getElementById('qa-overlay');
  if (overlay) overlay.classList.remove('active');
}

async function submitQuickAdd() {
  const input = document.getElementById('qa-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) { input.focus(); return; }
  closeQuickAdd();
  try {
    const res = await fetch(`${API}/tasks/quick-add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, auto_dispatch: true }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    quickAddConfirm('Got it — Magnolia is sorting this and routing it to a worker.');
    if (typeof fetchTasks === 'function') fetchTasks();   // the card lands in Now
  } catch (err) {
    toast(`Couldn't add that task: ${err.message}`);       // loud, persistent
  }
}

// Gentle, self-dismissing confirmation — separate from the error-only toast().
function quickAddConfirm(msg) {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const el = document.createElement('div');
  el.className = 'toast qa-confirm';
  el.setAttribute('role', 'status');
  const mark = typeof svgIcon === 'function' ? svgIcon('complete') : '';
  el.innerHTML = `<span class="qa-confirm-mark">${mark}</span><span class="qa-confirm-text"></span>`;
  el.querySelector('.qa-confirm-text').textContent = msg;
  const fade = () => { el.classList.add('toast-out'); setTimeout(() => el.remove(), 240); };
  el.addEventListener('click', fade);
  c.appendChild(el);
  setTimeout(fade, 1700);
}

// ── wiring ──────────────────────────────────────────────────────────
(function () {
  const overlay = document.getElementById('qa-overlay');
  const input = document.getElementById('qa-input');
  document.getElementById('qa-add')?.addEventListener('click', submitQuickAdd);
  document.getElementById('qa-cancel')?.addEventListener('click', closeQuickAdd);
  // backdrop click cancels; clicking the sheet does not
  overlay?.addEventListener('mousedown', (e) => { if (e.target === overlay) closeQuickAdd(); });

  input?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitQuickAdd(); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeQuickAdd(); }
  });

  function isTyping() {
    const el = document.activeElement; if (!el) return false;
    const t = el.tagName;
    return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT' || el.isContentEditable;
  }
  function anyLayerOpen() {
    return document.querySelector('.modal-overlay.active, .confirm-overlay.active, .qa-overlay.active') != null;
  }
  document.addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;   // leave browser/OS chords alone
    const k = e.key.toLowerCase();
    if (k !== 'c' && k !== 'n') return;
    if (isTyping() || anyLayerOpen()) return;
    e.preventDefault(); openQuickAdd();
  });
})();
