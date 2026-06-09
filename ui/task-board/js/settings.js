// ═══════════════════════════════════════════════════════════════════════
//  SETTINGS · top-bar cog
// ───────────────────────────────────────────────────────────────────────
//  A small gear in the top-bar right cluster (next to Mood) opens a calm
//  popover with the global "Autonomous Mode" toggle. The toggle flips the
//  engine's autonomy posture directly via the backend:
//      GET  /api/config/autonomy  → { enabled: bool }
//      POST /api/config/autonomy  { enabled: bool } → { ok, enabled }
//  Like the Mood control, this only ever surfaces/flips state — it never
//  changes any other interaction. Mirrors themes.js's build/open/close shape.
// ═══════════════════════════════════════════════════════════════════════

function buildSettingsControl() {
  const root = document.getElementById('settings-control');
  if (!root) return;

  root.innerHTML = `
    <button class="settings-btn" id="settings-cog" aria-haspopup="true" aria-expanded="false" title="Settings" aria-label="Settings">
      ${svgIcon('gear')}
    </button>
    <div class="settings-menu" id="settings-panel" role="menu" aria-label="Settings">
      <div class="settings-menu-head">Settings</div>
      <label class="settings-row" for="autonomy-toggle">
        <span class="settings-row-text">
          <span class="settings-row-name">Autonomous Mode</span>
          <span class="settings-row-blurb">Let trusted action types ship without asking. Off by default.</span>
        </span>
        <span class="settings-switch">
          <input type="checkbox" id="autonomy-toggle" role="switch" aria-checked="false">
          <span class="settings-switch-track"></span>
        </span>
      </label>
    </div>`;

  const btn   = root.querySelector('#settings-cog');
  const panel = root.querySelector('#settings-panel');
  const toggle = root.querySelector('#autonomy-toggle');

  const close = () => { panel.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); };
  const open  = () => { panel.classList.add('open');    btn.setAttribute('aria-expanded', 'true'); refreshAutonomy(toggle); };

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    panel.classList.contains('open') ? close() : open();
  });
  toggle.addEventListener('change', () => setAutonomy(toggle));
  document.addEventListener('click', (e) => { if (!root.contains(e.target)) close(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });

  // Reflect the real posture on load so the cog tells the truth even before opening.
  refreshAutonomy(toggle);
}

// Pull the current posture from the backend and reflect it in the toggle.
function refreshAutonomy(toggle) {
  if (!toggle) return;
  fetch(`${API}/config/autonomy`)
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => syncAutonomyUI(toggle, !!data.enabled))
    .catch(err => toast(`Couldn't read Autonomous Mode: ${err.message}`));
}

// Push the toggle's new state to the backend. On failure, revert + toast.
function setAutonomy(toggle) {
  if (!toggle) return;
  const want = toggle.checked;
  toggle.disabled = true;
  fetch(`${API}/config/autonomy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: want }),
  })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => {
      syncAutonomyUI(toggle, !!data.enabled);
      // toast() only surfaces errors by design; the flipped switch is its own confirmation.
      toast(`Autonomous Mode ${data.enabled ? 'on' : 'off'}`, 'success');
    })
    .catch(err => {
      syncAutonomyUI(toggle, !want);   // revert
      toast(`Couldn't change Autonomous Mode: ${err.message}`);
    })
    .finally(() => { toggle.disabled = false; });
}

function syncAutonomyUI(toggle, enabled) {
  toggle.checked = enabled;
  toggle.setAttribute('aria-checked', String(enabled));
}

function initSettings() { buildSettingsControl(); }

// Match themes.js: build once the static #settings-control mount exists.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSettings);
} else {
  initSettings();
}
