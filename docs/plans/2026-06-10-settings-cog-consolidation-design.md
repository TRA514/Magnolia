# Settings cog consolidation — design

**Date:** 2026-06-10
**Status:** Approved
**Scope:** Top-bar UI (`ui/task-board/`). Tier-1 (no external writes).

## Problem

The top-right controls don't read clearly:

- The "gear" icon (a circle with thin radiating spokes) reads as a **sunshine**, so
  the affordance for *settings* is weak.
- Settings is rightmost; Mood sits second-from-right.
- The **Engine** top-bar tab hides two management surfaces (Profile, Workers & prompts)
  that conceptually belong under settings. The operator wants the cog to grow into the
  real settings home as more items are added.

## Changes

### 1. Top-bar reorder
Swap the two mounts in `index.html` so the right cluster reads, left→right:
`+` · stats · **settings-control** · **mood-control**.
Settings = second-from-right, Mood = far-right.

### 2. New cog icon
Redraw `ICON.gear` in `js/icons.js` as a proper toothed cog (teeth around a center hub
with a hole), same `viewBox="0 0 16 16"`, `stroke="currentColor"`, 1.4 stroke weight,
round joins — stays in the line-mark family and inherits theme color.

### 3. Brightness reflects autonomy (no behavior change)
`.settings-btn.autonomy-on` already brightens the cog when autonomous mode is on. The new
icon inherits it automatically via `currentColor`. Kept as-is; verified across Moods.

### 4. Cog menu = the settings surface
Rebuild `#settings-panel` in `settings.js`. Menu order top→bottom:
1. **Profile** — menu item → opens the full-content settings view focused on Profile
2. **Workers and prompts** — menu item → opens it focused on Workers
3. *(divider)*
4. **Autonomous Mode** toggle — bottom, unchanged wiring

Menu items reveal `#tab-engine` then call the existing `switchEngine('profile'|'prompts')`,
then close the popover.

### 5. Remove the Engine tab
Delete the `<button data-tab="engine">Engine</button>` top-bar tab. Keep `#tab-engine`
as the content target (now launched from the cog, not a tab). The internal Profile↔Workers
sub-nav stays. Guard `switchTab()` so revealing a tab whose top-bar button no longer exists
doesn't throw.

## Decisions

- **Display mode:** full-content view (reuse existing panes + sub-nav). Rejected modal
  overlay (dense surfaces feel cramped, larger rewrite) and slide-in drawer (biggest
  departure).
- **Navigation back to board:** click any top-bar tab (Now, Schedules, Quality, Activity).
  No Engine tab to un-highlight.

## Gates & verification

- Green before commit: `pytest`, `scripts/card_schema.py`, `tests/test_engine_no_jay.py`.
- No theme tokens added/hardcoded; no person/team identity introduced.
- Dev board `:8743`: reorder, new cog shape, brightness follows autonomy on/off, both menu
  items open the right view, Engine tab gone, Mood spot-check.
