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
  const shown = (value === null || value === undefined || value === '') ? '-' : String(value);
  const dataVal = escapeAttr(value === null || value === undefined ? '' : String(value));
  return `<span class="fe-value" data-field="${field}" data-task="${escapeAttr(taskId)}" data-value="${dataVal}" onclick="startFieldEdit(this)" title="Click to edit">${escapeHtml(shown)}</span>`;
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
