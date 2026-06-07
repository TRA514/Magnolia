// ─── LangFuse Health ────────────────────────────────────────────────

async function checkLangfuseHealth() {
  const dot = document.getElementById('lf-status-dot');
  if (!dot) return;
  try {
    const res = await fetch(`${API}/langfuse/health`);
    const data = await res.json();
    dot.className = 'lf-status ' + (data.status === 'ok' ? 'ok' : 'error');
    dot.title = data.status === 'ok' ? 'LangFuse connected' : `LangFuse: ${data.message || data.status}`;
  } catch {
    dot.className = 'lf-status error';
    dot.title = 'LangFuse unreachable';
  }
}

// ─── Workers View (file-backed; no LangFuse) ───

async function fetchWorkers() {
  const view = document.getElementById('prompts-view');
  try {
    const res = await fetch(`${API}/workers`);
    const data = await res.json();
    _workerCache = data.workers || [];          // reused by the detail modal
    renderWorkers(_workerCache);
  } catch (err) {
    view.innerHTML = `<div class="loading" style="color:var(--danger)">Could not load workers: ${err.message}</div>`;
  }
}

function renderWorkers(workers) {
  const view = document.getElementById('prompts-view');
  let html = '<div class="prompts-section-title">Workers</div>';
  if (!workers.length) {
    html += '<div style="color:var(--text-muted);font-size:13px;">No workers found in scripts/workers/.</div>';
    view.innerHTML = html;
    return;
  }
  html += '<div class="prompt-cards">';
  for (const w of workers) {
    const tier = w.tier || 'standard';
    const packs = (w.packs || []).join(', ');
    html += `<div class="prompt-card" onclick="openWorkerDetail('${w.name}')" style="cursor:pointer">
      <div class="prompt-card-header">
        <span class="prompt-card-name">${escapeHtml(w.name)}</span>
        <span class="pf-tier ${escapeHtml(tier)}">${escapeHtml(tier)}</span>
      </div>
      <div class="prompt-card-desc">${escapeHtml(w.description || '')}</div>
      <div class="prompt-card-stats">
        <span>Model: ${escapeHtml(w.model || '—')}</span>
        ${packs ? `<span>Packs: ${escapeHtml(packs)}</span>` : ''}
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-top:6px;">Click for details</div>
    </div>`;
  }
  html += '</div>';
  view.innerHTML = html;
}

// ─── Worker Detail Modal ───────────────────────────────────────────

async function fetchWorkerDetails() {
  if (_workerCache) return _workerCache;
  try {
    const res = await fetch(`${API}/workers`);
    const data = await res.json();
    _workerCache = data.workers || [];
    return _workerCache;
  } catch { return []; }
}

async function openWorkerDetail(workerName) {
  const overlay = document.getElementById('modal-overlay');
  const modalBody = document.getElementById('modal-body');
  const modalTitle = document.getElementById('modal-title');
  const modalActions = document.getElementById('modal-actions');

  overlay.classList.add('active');
  modalBody.innerHTML = '<div class="loading">Loading worker details...</div>';
  modalTitle.textContent = workerName;
  modalActions.innerHTML = '';

  const workers = await fetchWorkerDetails();
  const w = workers.find(w => w.name === workerName);
  if (!w) {
    modalBody.innerHTML = '<div class="loading">Worker not found</div>';
    modalActions.innerHTML = '<button class="btn" onclick="closeModal()">Close</button>';
    return;
  }

  let html = '';

  // Description + meta
  html += `<div style="color:var(--text-muted);font-size:13px;margin-bottom:14px;">${escapeHtml(w.description || '')}</div>`;
  html += `<div style="display:flex;gap:12px;font-size:11px;color:var(--text-dim);margin-bottom:16px;">`;
  html += `<span>Priority: ${w.priority}</span>`;
  html += `<span>Timeout: ${w.timeout}s</span>`;
  html += `<span>Max turns: ${w.max_turns}</span>`;
  html += `</div>`;

  // Tier + resolved model + packs
  html += `<div style="display:flex;gap:12px;align-items:center;font-size:11px;color:var(--text-dim);margin-bottom:16px;">`;
  html += `<span class="pf-tier ${escapeHtml(w.tier || 'standard')}">${escapeHtml(w.tier || 'standard')}</span>`;
  html += `<span>Model: ${escapeHtml(w.model || '—')}</span>`;
  if ((w.packs || []).length) html += `<span>Packs: ${escapeHtml(w.packs.join(', '))}</span>`;
  html += `</div>`;

  // Tools
  html += '<div class="worker-detail-section">';
  html += '<div class="worker-detail-section-title">Allowed Tools</div>';
  html += '<div class="worker-tool-badges">';
  for (const tool of (w.allowed_tools || [])) {
    const isMcp = tool.startsWith('mcp__');
    const displayName = isMcp ? tool.replace('mcp__claude_ai_', '').replace('__*', '') : tool.replace('(*)', '');
    html += `<span class="worker-tool-badge ${isMcp ? 'mcp' : ''}" title="${escapeHtml(tool)}">${escapeHtml(displayName)}</span>`;
  }
  html += '</div></div>';

  // Skills
  html += '<div class="worker-detail-section">';
  html += '<div class="worker-detail-section-title">Skills</div>';
  html += '<div class="worker-skill-chips">';
  for (const skill of (w.skills || [])) {
    const shortName = skill.split('/').pop();
    html += `<span class="worker-skill-chip" title="${escapeHtml(skill)}">${escapeHtml(shortName)}</span>`;
  }
  if (!w.skills?.length) html += '<span style="color:var(--text-dim);font-size:12px;">(full catalog)</span>';
  html += '</div></div>';

  // Matching rules
  html += '<div class="worker-detail-section">';
  html += '<div class="worker-detail-section-title">Matching Rules</div>';
  html += '<div class="worker-match-rules">';
  const m = w.match || {};
  if (m.task_type?.length) html += `<div>Task type: ${m.task_type.map(t => `<code>${escapeHtml(t)}</code>`).join(', ')}</div>`;
  if (m.domains?.length) html += `<div>Domains: ${m.domains.map(d => `<code>${escapeHtml(d)}</code>`).join(', ')}</div>`;
  if (m.title_patterns?.length) {
    html += '<div style="margin-top:4px;">Title patterns:</div>';
    for (const p of m.title_patterns) html += `<div style="margin-left:12px;"><code>${escapeHtml(p)}</code></div>`;
  }
  if (m.description_patterns?.length) {
    html += '<div style="margin-top:4px;">Description patterns:</div>';
    for (const p of m.description_patterns) html += `<div style="margin-left:12px;"><code>${escapeHtml(p)}</code></div>`;
  }
  if (!m.task_type?.length && !m.domains?.length && !m.title_patterns?.length) {
    html += '<div style="color:var(--text-dim);">Catch-all (matches everything)</div>';
  }
  html += '</div></div>';

  // Prompt body
  html += '<div class="worker-detail-section">';
  html += '<div class="worker-detail-section-title">Prompt (read-only)</div>';
  html += `<div class="worker-prompt-view">${escapeHtml(w.prompt_body || '(no prompt body)')}</div>`;
  html += '</div>';

  modalBody.innerHTML = html;

  // Actions
  modalActions.innerHTML = `<button class="btn" onclick="closeModal()">Close</button>`;
}
