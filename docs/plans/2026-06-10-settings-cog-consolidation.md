# Settings Cog Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the top-right "sunshine" gear into a real settings cog that owns the settings surface — reorder it second-from-right (Mood far-right), give it a proper toothed-cog icon, and fold the Profile + Workers&prompts pages into its menu while removing the Engine tab.

**Architecture:** Pure front-end change in `ui/task-board/`. The two management surfaces stay exactly as the full-content `#tab-engine` panes they are today (with their internal Profile↔Workers sub-nav); only the launcher changes from a top-bar tab to items in the cog popover. The cog's autonomy-brightness (`.autonomy-on`) is unchanged. Tier-1 — no external writes.

**Tech Stack:** Vanilla HTML/CSS/JS served by `scripts/task_server.py`; dev board on `localhost:8743`.

**Verification model:** There is no unit-test seam for this vanilla DOM. The three repo gates (`pytest`, `scripts/card_schema.py`, `tests/test_engine_no_jay.py`) are run before each commit as regression safety; correctness is confirmed by live e2e observation on the dev board (Task 3).

---

### Task 1: Reorder controls + new cog icon

**Files:**
- Modify: `ui/task-board/index.html:1283-1284` (swap mount order)
- Modify: `ui/task-board/index.html:1273` (remove Engine tab button)
- Modify: `ui/task-board/js/icons.js:44` (redraw `gear`)
- Modify: `ui/task-board/js/app.js:3-7` (guard `switchTab` against missing tab button)

**Step 1: Swap the right-cluster mounts.** In `index.html`, change the order so settings comes before mood:
```html
    <div class="settings-control" id="settings-control"></div>
    <div class="mood-control" id="mood-control"></div>
```
(Settings = second-from-right, Mood = far-right.)

**Step 2: Remove the Engine top-bar tab.** Delete this line from the `.topbar-tabs` block:
```html
    <button class="topbar-tab" data-tab="engine" onclick="switchTab('engine')">Engine</button>
```
Leave the `#tab-engine` content block (lines ~1304-1321) intact — it's now launched from the cog.

**Step 3: Guard `switchTab` against a tab with no top-bar button.** `#tab-engine` no longer has a matching `.topbar-tab`, so the `querySelector(...).classList.add('active')` would throw. In `js/app.js`:
```js
function switchTab(tabName) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.topbar-tab').forEach(el => el.classList.remove('active'));
  document.getElementById(`tab-${tabName}`).classList.add('active');
  const tabBtn = document.querySelector(`.topbar-tab[data-tab="${tabName}"]`);
  if (tabBtn) tabBtn.classList.add('active');
  if (tabName === 'activity') renderActivity();
  if (tabName === 'quality') renderQuality();
  if (tabName === 'engine') fetchWorkers();
  if (tabName === 'schedules') fetchCronJobs();
}
```

**Step 4: Redraw the cog icon.** Replace `ICON.gear` in `js/icons.js:44` with a proper toothed cog (same viewBox/stroke/weight/joins family):
```js
  // settings — a calm toothed cog that matches the line-mark family above
  gear: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="2.05"/><path d="M8 1.5l.95 1.4a5.6 5.6 0 0 1 1.5.62l1.62-.45.92 1.6-1.1 1.25c.13.5.2 1.02.2 1.53l1.3.99-.6 1.74-1.66-.03c-.3.42-.66.79-1.07 1.09l.18 1.65-1.7.6-1.01-1.31a5.6 5.6 0 0 1-1.61 0L5.6 14.8l-1.7-.6.18-1.65c-.41-.3-.77-.67-1.07-1.09l-1.66.03-.6-1.74 1.3-.99c0-.51.07-1.03.2-1.53L1.15 5.97l.92-1.6 1.62.45c.46-.27.97-.48 1.5-.62L6.14 2.8z"/></svg>`,
```
Note: the outer path traces hub→tooth alternations so it reads unmistakably as a cog. Keep the inner `circle` as the hub hole.

**Step 5: Run the gates.**
```bash
cd /Users/jayjenkins/dev/pm-os-team
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
```
Expected: all pass; `card_schema.py` prints `registry.json OK`.

**Step 6: Commit.**
```bash
git add ui/task-board/index.html ui/task-board/js/icons.js ui/task-board/js/app.js
git commit -m "feat(board): reorder cog second-from-right, real toothed cog icon, drop Engine tab"
```

---

### Task 2: Fold Profile + Workers into the cog menu

**Files:**
- Modify: `ui/task-board/js/settings.js:17-52` (rebuild menu markup + wire the two items)

**Step 1: Rebuild the popover markup.** In `buildSettingsControl()`, replace the `#settings-panel` inner markup so it reads, top→bottom: Profile, Workers and prompts, divider, Autonomous Mode. The two items are buttons that open the settings view:
```html
    <div class="settings-menu" id="settings-panel" role="menu" aria-label="Settings">
      <div class="settings-menu-head">Settings</div>
      <button type="button" class="settings-link" id="settings-open-profile" role="menuitem">Profile</button>
      <button type="button" class="settings-link" id="settings-open-workers" role="menuitem">Workers and prompts</button>
      <div class="settings-divider"></div>
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
    </div>
```

**Step 2: Wire the two items.** After the existing `const toggle = ...` line, add a helper that reveals the engine view, switches to the requested sub-pane, and closes the popover:
```js
  const openSettingsView = (which) => {
    switchTab('engine');        // reveals #tab-engine content (no tab button to highlight)
    switchEngine(which);        // 'profile' | 'prompts' — loads + shows the sub-pane
    close();
  };
  root.querySelector('#settings-open-profile').addEventListener('click', (e) => { e.stopPropagation(); openSettingsView('profile'); });
  root.querySelector('#settings-open-workers').addEventListener('click', (e) => { e.stopPropagation(); openSettingsView('prompts'); });
```

**Step 3: Style the menu items.** Add CSS for `.settings-link` and `.settings-divider` next to the existing `.settings-row` rules in `ui/task-board/css/magnolia.css` (token-only — reuse `--text`, `--text-dim`, `--accent-soft`, existing radii/transitions; no hardcoded color/radius/transition per invariant #3). A left-aligned text button, full width, hover gets `--accent-soft`; the divider is a hairline using an existing border token.

**Step 4: Run the gates.**
```bash
cd /Users/jayjenkins/dev/pm-os-team
python3 -m pytest -q && python3 scripts/card_schema.py && python3 -m pytest tests/test_engine_no_jay.py -q
```
Expected: all pass.

**Step 5: Commit.**
```bash
git add ui/task-board/js/settings.js ui/task-board/css/magnolia.css
git commit -m "feat(board): cog menu launches Profile + Workers, autonomy toggle at bottom"
```

---

### Task 3: Live e2e verification on the dev board

**Not a code task — observation.** Start the dev board and verify against the design. Follow the visual-pass technique (Chrome headless screenshots) if no browser is interactive.

Checklist:
1. Top-right order is `+` · settings cog · Mood (cog second-from-right, Mood far-right).
2. The icon reads as a clear toothed cog, not a sunshine.
3. Toggling Autonomous Mode brightens/dims the cog (`.autonomy-on`); state persists on reload.
4. Clicking the cog → menu shows Profile, Workers and prompts, divider, Autonomous Mode (in that order).
5. "Profile" opens the Profile view; "Workers and prompts" opens the Workers view; sub-nav flips between them; a top-bar tab (Now) returns to the board.
6. No Engine tab in the top bar.
7. Spot-check at least one other Mood — layout/affordance hold.

Restart the board (`:8743`) and hard-reload the browser before checking (server caches static assets / JS).
