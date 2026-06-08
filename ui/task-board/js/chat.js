// ─── Task assistant · linked chat ────────────────────────────────────
// The right pane of the split workspace. It opens empty — a single centered
// whisper naming what it knows — and waits for an instruction ("Tell me what
// to do…"). Under the hood it's headless Claude Code continuing this card's
// session: a POST to /api/tasks/<id>/chat opens an SSE stream, and the server
// owns the system prompt (identity + voice from profile/, never hardcoded).
// Replies read like Claude: a thinking line, inline tool steps, then streamed
// text. When a turn completes, the left task detail re-settles from real
// persisted state so any artifact edits the agent made appear.
//
// TIER-2 boundary: this chat drafts and edits task artifacts only — it NEVER
// fires an external write (send-message / publish-jira / schedule-meeting).
// Those remain the left-pane gated verbs, each behind one plain-language
// confirm (invariant #5: agent drafts → board publishes). Chat-initiated
// action proposals (an inline confirm that routes to a gated board endpoint)
// are a documented follow-on, not implemented here.
//
// Depends on globals: API, svgIcon, escapeHtml, formatDate, meetingName,
// fetchTasks (board refresh), openTask (left-detail re-render).

let chatState = null; // { task, busy }

// Reveal an element's enter-transition without relying on requestAnimationFrame
// (which is throttled when the tab isn't focused). Forcing a reflow commits the
// hidden baseline, so adding the class animates to the shown state.
function revealNow(el, cls) { void el.offsetWidth; el.classList.add(cls); }

function buildChat(task) {
  chatState = { task, busy: false };

  const anchor = document.getElementById('chat-anchor');
  if (anchor) {
    anchor.innerHTML = `<span class="chat-anchor-dot"></span>linked to ${escapeHtml(task.id)}`;
    anchor.title = `Continuing this card's session`;
  }

  const empty = document.getElementById('chat-empty');
  if (empty) empty.classList.remove('gone');
  const thread = document.getElementById('chat-thread');
  if (thread) thread.innerHTML = '';

  const input = document.getElementById('chat-input');
  if (input) {
    input.value = '';
    input.style.height = 'auto';
    input.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } };
    input.oninput = function () { this.style.height = 'auto'; this.style.height = Math.min(this.scrollHeight, 140) + 'px'; };
    // Land the cursor in the composer once the workspace reveal settles. The
    // chat footer fades in on a .48s delay (see index.html), so we focus just
    // after that so the blinking caret appears in an already-visible field
    // rather than behind the fade.
    setTimeout(() => {
      const a = document.activeElement;
      if (!a || a === document.body || a === input) input.focus();
    }, 520);
  }
  const send = document.getElementById('chat-send');
  if (send) send.disabled = false;
}

// ── Turn rendering (single column — user bubble · assistant prose) ───
function renderTurn(turn, instant) {
  const el = document.createElement('div');
  el.className = `chat-turn turn-${turn.role}${instant ? ' show' : ''}`;
  if (turn.role === 'user') {
    el.innerHTML = `<div class="turn-text">${escapeHtml(turn.text || '')}</div>`;
    return el;
  }
  const stepsBox = document.createElement('div');
  stepsBox.className = 'turn-steps';
  renderStepsInto(stepsBox, turn.steps || [], instant);
  el.appendChild(stepsBox);
  const txt = document.createElement('div');
  txt.className = 'turn-text';
  txt.textContent = turn.text || '';
  el.appendChild(txt);
  return el;
}

function stepHtml(s) {
  const VERB = { read: 'Read', search: 'Searched', write: 'Wrote', run: 'Ran' };
  if (s.kind === 'think') return `<div class="tool-think">${escapeHtml(s.label)}</div>`;
  return `<div class="tool-step"><span class="tool-verb">${VERB[s.kind] || 'Tool'}</span><span class="tool-target">${escapeHtml(s.label)}</span></div>`;
}

// Collapse threshold — runs with this many tool calls fold into one line.
const STEP_COLLAPSE_AT = 5;
const CHEV_SVG = '<svg class="chev-svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 4l4 4-4 4"/></svg>';
const CHECK_SVG = '<svg class="step-check" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8.5l3 3 6-6.5"/></svg>';

function elFromHTML(html) { const h = document.createElement('div'); h.innerHTML = html; return h.firstChild; }

// A collapsible group: a hidden toggle header + an animatable list of rows.
function makeStepsGroup() {
  const group = document.createElement('div'); group.className = 'steps-group';
  const toggle = document.createElement('button'); toggle.className = 'steps-toggle'; toggle.type = 'button'; toggle.style.display = 'none';
  const list = document.createElement('div'); list.className = 'steps-list';
  const inner = document.createElement('div'); inner.className = 'steps-inner';
  list.appendChild(inner); group.appendChild(toggle); group.appendChild(list);
  return { group, toggle, list, inner };
}

// Fold the run down to one calm line; click toggles the full list back open.
function collapseGroup(g, count) {
  g.list.classList.add('collapsed');
  g.toggle.style.display = 'inline-flex';
  g.toggle.innerHTML = `${CHECK_SVG}<span class="steps-count">Worked across ${count} steps</span>${CHEV_SVG}`;
  g.toggle.onclick = () => {
    const collapsed = g.list.classList.toggle('collapsed');
    g.toggle.classList.toggle('open', !collapsed);
    scrollThread();
  };
}

// Render steps into a box (instant, for history). Leading reasoning lines stay
// visible; from the first tool call on, rows go into a group that collapses if
// the run is long.
function renderStepsInto(stepsBox, steps, instant) {
  if (!steps || !steps.length) return;
  const firstTool = steps.findIndex(s => s.kind !== 'think');
  const lead = firstTool < 0 ? steps : steps.slice(0, Math.max(firstTool, 0));
  const rest = firstTool < 0 ? [] : steps.slice(firstTool);
  lead.forEach(s => { const r = elFromHTML(stepHtml(s)); if (instant) r.classList.add('in'); stepsBox.appendChild(r); });
  if (!rest.length) return;
  const g = makeStepsGroup();
  rest.forEach(s => { const r = elFromHTML(stepHtml(s)); if (instant) r.classList.add('in'); g.inner.appendChild(r); });
  stepsBox.appendChild(g.group);
  const toolCount = rest.filter(s => s.kind !== 'think').length;
  if (toolCount >= STEP_COLLAPSE_AT) collapseGroup(g, toolCount);
}

function scrollThread() {
  const body = document.getElementById('chat-body');
  if (body) body.scrollTop = body.scrollHeight;
}

// streamText — kept for parity with the render layer (history replay can use
// it). The LIVE path appends tokens directly as SSE 'text' events arrive, which
// is simpler and robust for real streaming; this helper stays harmless.
async function streamText(box, text) {
  const _sleep = ms => new Promise(r => setTimeout(r, ms));
  const words = String(text).split(/(\s+)/);
  box.textContent = '';
  box.classList.add('streaming');
  for (let i = 0; i < words.length; i++) {
    box.textContent += words[i];
    if (i % 2 === 0) { scrollThread(); await _sleep(26); }
  }
  box.classList.remove('streaming');
  scrollThread();
}

function actionNote(turnEl, label) {
  const note = document.createElement('div');
  note.className = 'turn-result';
  note.innerHTML = `${svgIcon('done')}<span>${escapeHtml(label)}</span>`;
  turnEl.appendChild(note);
  revealNow(note, 'in');
  scrollThread();
}

// ── Send + real SSE stream ───────────────────────────────────────────
async function sendChat() {
  if (!chatState || chatState.busy) return;
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = ''; input.style.height = 'auto';
  chatState.busy = true;
  document.getElementById('chat-send').disabled = true;
  const empty = document.getElementById('chat-empty'); if (empty) empty.classList.add('gone');
  const thread = document.getElementById('chat-thread');
  const userTurn = renderTurn({ role: 'user', text }, false);
  thread.appendChild(userTurn); revealNow(userTurn, 'show'); scrollThread();

  // assistant turn shell with typing indicator
  const a = document.createElement('div');
  a.className = 'chat-turn turn-assistant show';
  a.innerHTML = `<div class="turn-steps"></div><div class="turn-text"><span class="typing"><span></span><span></span><span></span></span></div>`;
  thread.appendChild(a); scrollThread();
  const stepsBox = a.querySelector('.turn-steps');
  const textBox = a.querySelector('.turn-text');
  let typingCleared = false, liveGroup = null, toolCount = 0, sawText = false;
  const clearTyping = () => { if (!typingCleared) { textBox.innerHTML = ''; typingCleared = true; } };

  try {
    const resp = await fetch(`${API}/tasks/${chatState.task.id}/chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    if (resp.status === 409) { clearTyping(); textBox.textContent = 'The agent is currently working on this task. Try again in a moment.'; throw new Error('busy'); }
    if (!resp.ok || !resp.body) { clearTyping(); textBox.textContent = 'Could not reach the assistant. You can retry.'; throw new Error('http'); }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      // SSE frames are separated by a blank line.
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const frame = buf.slice(0, idx); buf = buf.slice(idx + 2);
        handleFrame(frame);
      }
    }
  } catch (e) { /* message already shown on the turn */ }

  function handleFrame(frame) {
    // A frame may carry "event: done" and/or a "data: {...}" line.
    let isDone = false, dataLine = null;
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:') && line.slice(6).trim() === 'done') isDone = true;
      else if (line.startsWith('data:')) dataLine = line.slice(5).trim();
    }
    if (isDone) return;            // terminal sentinel; the read loop will end
    if (!dataLine) return;
    let ev; try { ev = JSON.parse(dataLine); } catch (_) { return; }
    renderEvent(ev);
  }

  function renderEvent(ev) {
    if (ev.kind === 'think') {
      clearTyping();
      const t = elFromHTML(stepHtml({ kind: 'think', label: ev.text || '' }));
      stepsBox.appendChild(t); revealNow(t, 'in'); scrollThread();
    } else if (ev.kind === 'tool_step') {
      clearTyping();
      if (!liveGroup) { liveGroup = makeStepsGroup(); stepsBox.appendChild(liveGroup.group); }
      const verb = (ev.verb || 'tool').toLowerCase();
      const kindMap = { read: 'read', grep: 'search', glob: 'search', write: 'write', edit: 'write', bash: 'run' };
      const row = elFromHTML(stepHtml({ kind: kindMap[verb] || 'run', label: ev.target || ev.verb || '' }));
      liveGroup.inner.appendChild(row); revealNow(row, 'in'); scrollThread();
      toolCount += 1;
      if (toolCount === STEP_COLLAPSE_AT) collapseGroup(liveGroup, toolCount);
      else if (toolCount > STEP_COLLAPSE_AT) { liveGroup.toggle.querySelector('.steps-count').textContent = `Worked across ${toolCount} steps`; }
    } else if (ev.kind === 'text') {
      clearTyping();
      if (!sawText) { sawText = true; textBox.textContent = ''; }
      textBox.textContent += ev.text || '';
      scrollThread();
    } else if (ev.kind === 'error') {
      clearTyping();
      textBox.textContent = ev.text || 'The chat run failed. You can retry.';
      a.classList.add('turn-error');
    } else if (ev.kind === 'result') {
      // turn complete — settle the left detail from real persisted state
      settleDetailFromServer();
    }
  }

  chatState.busy = false;
  document.getElementById('chat-send').disabled = false;
  scrollThread();
}

// ── Settle the LEFT detail from real persisted state ─────────────────
// On a turn's `result` event, re-read the current task and refresh the left
// pane so any artifact edits the agent made during the turn appear, plus the
// (blurred) board behind. The chat itself never fires an external write — this
// is read-and-reflect only. Prefer the board's own detail renderer (openTask)
// so the left pane stays a single source of truth; fall back to in-place chip /
// activity updates if openTask isn't available.
function pulse(el) { if (!el) return; el.classList.remove('dt-pulse'); void el.offsetWidth; el.classList.add('dt-pulse'); }

function setStatus(label, cls) {
  const st = document.getElementById('dt-status');
  if (st) { st.className = `dt-status ${cls}`; st.innerHTML = `${svgIcon('complete')}${label}`; pulse(st); }
}
function markFooterDone(label) {
  const right = document.querySelector('#modal-actions .dt-foot-right');
  if (right) right.innerHTML = `<span class="dt-done-note">${svgIcon('complete')}${escapeHtml(label || 'Cleared')}</span>`;
}
function addDetailActivity(content, type) {
  const thread = document.getElementById('dt-thread');
  if (!thread) return;
  const e = document.createElement('div');
  e.className = `dt-event ev-${type} dt-event-new`;
  e.innerHTML = `<span class="dt-ev-dot"></span><div><div class="dt-ev-meta"><span class="dt-ev-actor">Task assistant</span><span>just now</span><span class="dt-ev-kind">${escapeHtml(type.replace(/-/g, ' '))}</span></div><div class="dt-ev-body">${escapeHtml(content)}</div></div>`;
  thread.appendChild(e);
  revealNow(e, 'in');
}

async function settleDetailFromServer() {
  if (!chatState || !chatState.task) return;
  const id = chatState.task.id;
  // Refresh the (blurred) board behind so card state stays current.
  if (typeof fetchTasks === 'function') { try { fetchTasks(); } catch (_) {} }

  // Re-render the left detail in place via the board's own renderer. openTask
  // re-fetches GET /api/tasks/<id> and rebuilds the task pane, so any artifact
  // edits the agent persisted this turn appear. It targets the same modal nodes
  // the split workspace reuses (#modal-body / #modal-actions / #modal-title),
  // and leaves the chat pane untouched.
  if (typeof openTask === 'function') {
    try { await openTask(id, true); return; } catch (_) { /* fall through to lightweight update */ }
  }

  // Fallback: lightweight in-place refresh if the full renderer is unavailable.
  try {
    const res = await fetch(`${API}/tasks/${id}`);
    if (!res.ok) return;
    const task = await res.json();
    chatState.task = task;
    const lastOut = (task.activity_log || []).filter(e => e.type === 'output').pop();
    if (lastOut) addDetailActivity(lastOut.content, 'output');
    const body = document.getElementById('message-body-text');
    if (body && task.message_body) { body.textContent = task.message_body; pulse(body.closest('.dt-msg-bubble')); }
  } catch (_) {}
}
