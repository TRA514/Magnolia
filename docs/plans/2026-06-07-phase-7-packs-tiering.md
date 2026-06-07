# Phase 7 — Skill Packs + Model Tiering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `active_skill_packs` and `cost_posture` (already written by the Profile room UI) actually do something — packs gate which skills the background workers see; posture + per-worker tiers select the model dispatch enforces.

**Architecture:** Two independent halves shipped as two PRs off `main`. PR 1: a git-tracked `.claude/packs.yaml` manifest + a pure `scripts/packs_lib.py` that derives the pack catalog and resolves the active skill-folder set; `build_skills_catalog()` and `build_profile()` consume it. PR 2: per-worker `tier:` frontmatter + `profile_lib.resolve_model()` (shift ±1 by posture, clamped, per-task override wins) + `dispatch_task` appending `--model`.

**Tech Stack:** Python 3 (bare Homebrew, PEP-668 → `pip install --break-system-packages`), `ruamel.yaml`, `pytest`. No JS test harness — frontend verified on-screen via Chrome.app headless against the dev board on **:8743** (prod is :8742, never touched).

**Design doc:** `docs/plans/2026-06-07-phase-7-packs-tiering-design.md`

**Conventions to mirror:**
- Tests live in `tests/test_*.py`; `conftest.py` puts `scripts/` on `sys.path` and provides the `profile_root` fixture (a tmp PM-OS root with a populated `profile/`).
- All profile readers/writers take `root=None` (defaults to `PM_OS_DIR`); tests pass `root=profile_root`.
- Keep heavy logic in **pure functions** that take their inputs as arguments (easy to unit-test), with thin disk-reading wrappers around them.
- End every commit message with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- Run the suite with `python3 -m pytest -q` (169 passing at Phase 6 close). Keep `python3 scripts/card_schema.py` green.

---

# PR 1 — Skill Packs

**Branch:** `feat/phase-7-skill-packs` (already created; the design doc is committed here).

## Task 1: The `packs.yaml` manifest

**Files:**
- Create: `.claude/packs.yaml`

This is data, not code — no test of its own; Tasks 2–4 validate the code that reads it.

> **⚠️ REVIEW CHECKPOINT:** This skill→pack assignment is a *proposal*. Before committing,
> present it to the operator (same review style as the worker-tier map) and apply edits. The
> assignment below is the starting point.

**Step 1: Write the file**

```yaml
# packs.yaml — skill pack definitions (engine-shared, git-tracked).
#
# A "pack" is a named set of skill folders under .claude/skills/.
# Activating a pack controls which skills the Magnolia BACKGROUND WORKERS see
# (the headless dispatch catalog) and what the Engine/Profile UI lists. It does
# NOT affect your interactive Claude Code session (native auto-discovery there is
# unchanged).
#
# To add a skill to a pack:
#   1. Drop the folder in .claude/skills/  (auto-discovered — no other wiring).
#   2. Add its folder name to a pack's `skills:` list below.
# A skill listed in NO pack stays always-available (gating never hides it).
#
# WHICH packs are active is per-person, in profile/config.yaml `active_skill_packs`.
# `core` is always active regardless of that list.

core:
  label: "Core"
  description: "Baseline PM-OS: tasks, search, meetings, onboarding, doctor, doc sync."
  skills:
    - task-create
    - task-query
    - task-update
    - task-complete
    - task-communicate
    - task-extract-from-meeting
    - context-search
    - context-meeting-synthesis
    - context-source-normalization
    - meta-onboard
    - meta-using-skills
    - meta-skill-discovery
    - meta-create-skill
    - meta-refine-workflow
    - workflow-doctor
    - workflow-schedule-meeting
    - workflow-doc-sync
    - workflow-publish-package
    - quality-meeting-schema-validation
    - quality-documentation-sync

pm:
  label: "Product Management"
  description: "PRDs, roadmaps, strategy, metrics, prioritization, and research."
  skills:
    - workflow-prd-creation
    - workflow-product-planning
    - workflow-roadmap-updating
    - workflow-product-strategy-creation
    - workflow-ambition-expander
    - workflow-devils-advocate
    - workflow-red-team-reviewer
    - workflow-agentic-api-designer
    - workflow-vision-clarifier
    - workflow-launch-announcement
    - workflow-tradeoff-decision
    - workflow-cs-prep
    - workflow-velocity-estimate
    - workflow-metrics-definition
    - workflow-metric-diagnosis
    - workflow-dashboard-design
    - workflow-goal-setting
    - workflow-research-processing
    - metric-funnel-metric-mapping
    - metric-north-star-alignment
    - metric-proxy-metric-selection
    - metric-root-cause-diagnosis
    - metric-tradeoff-evaluation
    - context-priority-scoring
    - context-research-gathering
    - context-pendo-analytics
    - context-databricks-analytics
    - quality-prd-validation
    - quality-product-strategy-validation
    - quality-citation-compliance
    - quality-source-integrity
    - quality-link-verification

exec:
  label: "Executive"
  description: "Strategy memos, sessions, goal-setting, and business-case modeling."
  skills:
    - workflow-strategy-memo
    - workflow-strategy-session
    - workflow-goal-setting
    - workflow-swag-modeler
    - workflow-product-strategy-creation

eng:
  label: "Engineering"
  description: "Ticket drafting, velocity estimation, and tech-spec stress review."
  skills:
    - workflow-jira-home
    - workflow-velocity-estimate
    - workflow-red-team-reviewer
    - workflow-agentic-api-designer

recruiting:
  label: "Recruiting"
  description: "Candidate synthesis and hiring-loop support (no skills yet — factory-extensible)."
  skills: []
```

> Note: `quality-content-style` and `workflow-landing-page-creator` are intentionally **unlisted**
> (marketing/content) → they stay always-available under the unlisted rule. Confirm at the checkpoint.

**Step 2: Commit** (after the review checkpoint)

```bash
git add .claude/packs.yaml
git commit -m "feat(phase-7): add packs.yaml skill-pack manifest (core/pm/exec/eng/recruiting)"
```

---

## Task 2: `packs_lib.load_packs` + `pack_catalog`

**Files:**
- Create: `scripts/packs_lib.py`
- Test: `tests/test_packs_lib.py`

**Step 1: Write the failing tests**

```python
import os
import textwrap
import packs_lib


def _write_packs(root, body):
    claude = os.path.join(root, ".claude")
    os.makedirs(claude, exist_ok=True)
    with open(os.path.join(claude, "packs.yaml"), "w") as f:
        f.write(textwrap.dedent(body))


def test_load_packs_parses_manifest(tmp_path):
    _write_packs(str(tmp_path), """\
        core:
          label: "Core"
          description: "Baseline."
          skills: [task-create, context-search]
        pm:
          label: "Product Management"
          description: "PRDs."
          skills: [workflow-prd-creation]
    """)
    packs = packs_lib.load_packs(root=str(tmp_path))
    assert set(packs) == {"core", "pm"}
    assert packs["core"]["skills"] == ["task-create", "context-search"]


def test_load_packs_missing_file_returns_empty(tmp_path):
    assert packs_lib.load_packs(root=str(tmp_path)) == {}


def test_pack_catalog_shape(tmp_path):
    _write_packs(str(tmp_path), """\
        core:
          label: "Core"
          description: "Baseline."
          skills: []
        pm:
          label: "Product Management"
          description: "PRDs."
          skills: []
    """)
    cat = packs_lib.pack_catalog(root=str(tmp_path))
    assert {"id", "label", "description"} <= set(cat[0])
    assert {c["id"] for c in cat} == {"core", "pm"}


def test_pack_catalog_missing_file_returns_empty_list(tmp_path):
    assert packs_lib.pack_catalog(root=str(tmp_path)) == []
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_packs_lib.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'packs_lib'`).

**Step 3: Write the implementation**

```python
"""Skill-pack definitions (engine-shared).

A pack is a named set of skill folders under .claude/skills/. This module reads
.claude/packs.yaml and answers two questions: what packs exist (pack_catalog,
for the Profile UI) and which skill folders an active-pack list resolves to
(active_skill_folders, for dispatch gating). Pure logic is separated from disk
reads so it unit-tests without a filesystem. Degrades to "no gating" when the
manifest is missing or malformed.
"""
import os
from ruamel.yaml import YAML

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PM_OS_DIR = os.path.dirname(SCRIPT_DIR)

_yaml = YAML(typ="safe")

ALWAYS_ON = "core"


def _packs_path(root=None):
    return os.path.join(root or PM_OS_DIR, ".claude", "packs.yaml")


def load_packs(root=None):
    """Parse .claude/packs.yaml -> {id: {label, description, skills:[...]}}.
    Returns {} when the file is missing or unparseable (degrade to no gating)."""
    path = _packs_path(root)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = _yaml.load(f) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for pid, spec in data.items():
        if not isinstance(spec, dict):
            continue
        out[pid] = {
            "label": spec.get("label") or pid.title(),
            "description": spec.get("description") or "",
            "skills": [s for s in (spec.get("skills") or []) if isinstance(s, str)],
        }
    return out


def pack_catalog(root=None):
    """[{id, label, description}] for the Profile room. Empty when no manifest."""
    return [{"id": pid, "label": spec["label"], "description": spec["description"]}
            for pid, spec in load_packs(root).items()]
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_packs_lib.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/packs_lib.py tests/test_packs_lib.py
git commit -m "feat(phase-7): packs_lib.load_packs + pack_catalog reading .claude/packs.yaml"
```

---

## Task 3: `packs_lib.active_skill_folders` (the gating resolver)

**Files:**
- Modify: `scripts/packs_lib.py`
- Test: `tests/test_packs_lib.py`

The pure resolver: given the active-pack list, the parsed packs, and the set of skill folders
present on disk, return the set of folders gating should keep visible. Rules: `core` is always
included; union the active packs' skills; any on-disk folder belonging to **no** pack stays
visible (unlisted = always-available).

**Step 1: Write the failing tests**

```python
def test_active_skill_folders_unions_core_and_active(tmp_path):
    packs = {
        "core": {"label": "", "description": "", "skills": ["task-create"]},
        "pm":   {"label": "", "description": "", "skills": ["workflow-prd-creation"]},
        "eng":  {"label": "", "description": "", "skills": ["workflow-jira-home"]},
    }
    on_disk = {"task-create", "workflow-prd-creation", "workflow-jira-home"}
    got = packs_lib.active_skill_folders(["pm"], packs=packs, on_disk=on_disk)
    assert got == {"task-create", "workflow-prd-creation"}   # core + pm, not eng


def test_active_skill_folders_core_always_on(tmp_path):
    packs = {"core": {"label": "", "description": "", "skills": ["task-create"]},
             "pm": {"label": "", "description": "", "skills": ["workflow-prd-creation"]}}
    on_disk = {"task-create", "workflow-prd-creation"}
    got = packs_lib.active_skill_folders([], packs=packs, on_disk=on_disk)
    assert "task-create" in got and "workflow-prd-creation" not in got


def test_active_skill_folders_unlisted_stays_visible(tmp_path):
    packs = {"core": {"label": "", "description": "", "skills": ["task-create"]},
             "pm": {"label": "", "description": "", "skills": ["workflow-prd-creation"]}}
    on_disk = {"task-create", "workflow-prd-creation", "quality-content-style"}
    got = packs_lib.active_skill_folders(["pm"], packs=packs, on_disk=on_disk)
    assert "quality-content-style" in got   # in no pack -> always available


def test_active_skill_folders_no_manifest_returns_all(tmp_path):
    on_disk = {"a", "b", "c"}
    assert packs_lib.active_skill_folders(["pm"], packs={}, on_disk=on_disk) == on_disk
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_packs_lib.py -q`
Expected: FAIL (`active_skill_folders` not defined).

**Step 3: Write the implementation** (append to `scripts/packs_lib.py`)

```python
def _on_disk_skill_folders(root=None):
    skills_dir = os.path.join(root or PM_OS_DIR, ".claude", "skills")
    if not os.path.isdir(skills_dir):
        return set()
    return {name for name in os.listdir(skills_dir)
            if os.path.isfile(os.path.join(skills_dir, name, "SKILL.md"))
            or os.path.isfile(os.path.join(skills_dir, name, "skill.md"))}


def active_skill_folders(active_packs, packs=None, on_disk=None, root=None):
    """Resolve the set of skill folders gating keeps visible.

    core (ALWAYS_ON) is always included; union each active pack's skills; any
    on-disk folder in NO pack stays visible. With no manifest (packs == {}),
    returns every on-disk folder (no gating)."""
    if packs is None:
        packs = load_packs(root)
    if on_disk is None:
        on_disk = _on_disk_skill_folders(root)
    if not packs:
        return set(on_disk)
    listed = {s for spec in packs.values() for s in spec["skills"]}
    keep = set(packs.get(ALWAYS_ON, {}).get("skills", []))
    for pid in active_packs:
        keep |= set(packs.get(pid, {}).get("skills", []))
    keep |= {f for f in on_disk if f not in listed}   # unlisted = always-available
    return keep & set(on_disk)                          # never surface a phantom
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_packs_lib.py -q`
Expected: PASS (all 8 tests).

**Step 5: Commit**

```bash
git add scripts/packs_lib.py tests/test_packs_lib.py
git commit -m "feat(phase-7): packs_lib.active_skill_folders — core-always-on + unlisted-always-available gating resolver"
```

---

## Task 4: Gate `build_skills_catalog` + derive `PACK_CATALOG`

**Files:**
- Modify: `scripts/task_dispatch.py` (`build_skills_catalog`, ~line 192)
- Modify: `scripts/task_server.py` (`build_profile` packs section, ~line 414; remove the `PACK_CATALOG` constant, ~line 279)
- Test: `tests/test_packs_lib.py` (gating integration), `tests/test_profile_api.py` (catalog derivation)

**Step 1: Write the failing tests**

In `tests/test_profile_api.py` (the `profile_root` config already has `active_skill_packs: ["core","pm"]`; add a `.claude/packs.yaml` under the temp root in the test):

```python
def test_build_profile_packs_derive_from_manifest(profile_root):
    import os, textwrap, task_server
    claude = os.path.join(profile_root, ".claude")
    os.makedirs(claude, exist_ok=True)
    with open(os.path.join(claude, "packs.yaml"), "w") as f:
        f.write(textwrap.dedent("""\
            core:  {label: "Core", description: "Baseline.", skills: [task-create]}
            pm:    {label: "Product Management", description: "PRDs.", skills: [workflow-prd-creation]}
            exec:  {label: "Executive", description: "Memos.", skills: [workflow-strategy-memo]}
        """))
    p = task_server.build_profile(root=profile_root)
    ids = {c["id"] for c in p["packs"]["available"]}
    assert ids == {"core", "pm", "exec"}          # from manifest, not the old hardcoded list
    assert "core" in p["packs"]["active"]
```

In `tests/test_packs_lib.py` (gating integration — `build_skills_catalog` lists only active-pack skills):

```python
def test_build_skills_catalog_gates_to_active(tmp_path, monkeypatch):
    import os, textwrap, task_dispatch, profile_lib, packs_lib
    # temp engine root with two skills on disk and a manifest splitting them
    skills = os.path.join(tmp_path, ".claude", "skills")
    for name, desc in [("task-create", "Use when creating tasks"),
                       ("workflow-jira-home", "Use when filing Jira issues")]:
        os.makedirs(os.path.join(skills, name))
        with open(os.path.join(skills, name, "SKILL.md"), "w") as f:
            f.write(f"---\nname: {name}\ndescription: {desc}\n---\n# body\n")
    with open(os.path.join(tmp_path, ".claude", "packs.yaml"), "w") as f:
        f.write(textwrap.dedent("""\
            core: {label: Core, description: x, skills: [task-create]}
            eng:  {label: Engineering, description: x, skills: [workflow-jira-home]}
        """))
    monkeypatch.setattr(task_dispatch, "PM_OS_DIR", str(tmp_path))
    monkeypatch.setattr(packs_lib, "PM_OS_DIR", str(tmp_path))
    monkeypatch.setattr(profile_lib, "PM_OS_DIR", str(tmp_path))
    # config with eng OFF
    prof = os.path.join(tmp_path, "profile"); os.makedirs(prof)
    with open(os.path.join(prof, "config.yaml"), "w") as f:
        f.write('active_skill_packs: ["core"]\n')
    catalog = task_dispatch.build_skills_catalog()
    assert "task-create" in catalog
    assert "workflow-jira-home" not in catalog   # eng pack inactive -> gated out
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_packs_lib.py::test_build_skills_catalog_gates_to_active tests/test_profile_api.py::test_build_profile_packs_derive_from_manifest -q`
Expected: FAIL (catalog still lists all; `available` still the hardcoded 5).

**Step 3: Implement**

In `scripts/task_dispatch.py`, make `build_skills_catalog` pack-aware. Current body walks all of
`.claude/skills/`; add a gate using the active set:

```python
def build_skills_catalog():
    """Walk .claude/skills/ and return a concise catalog of available skills,
    gated to the operator's active skill packs (packs_lib). Skills in no pack
    stay visible; a missing/empty manifest disables gating (all skills shown)."""
    import packs_lib
    import profile_lib
    catalog_lines = []
    skills_dir = os.path.join(PM_OS_DIR, ".claude", "skills")
    if not os.path.isdir(skills_dir):
        return "(no skills directory found)"
    active_packs = profile_lib.config().get("active_skill_packs") or []
    visible = packs_lib.active_skill_folders(active_packs)
    for root, dirs, files in os.walk(skills_dir):
        if "SKILL.md" in files:
            folder = os.path.basename(root)
            if folder not in visible:
                continue
            name, desc = parse_skill_frontmatter(os.path.join(root, "SKILL.md"))
            if name and desc:
                catalog_lines.append(f"- **{name}**: {desc}")
    return "\n".join(catalog_lines) if catalog_lines else "(no skills found)"
```

> Note: `active_skill_folders()` keys on the **folder name** (`os.path.basename(root)`), which is
> what `packs.yaml` lists — not the `name:` field inside the SKILL.md. Keep that distinction.

In `scripts/task_server.py`: delete the `PACK_CATALOG = [...]` constant (~lines 279–290) and change
`build_profile`'s packs block:

```python
    packs = {
        "active": cfg.get("active_skill_packs") or [],
        "available": packs_lib.pack_catalog(root),
    }
```

Add `import packs_lib` near the top of `task_server.py` if not present.

**Step 4: Run the focused tests, then the suite**

Run: `python3 -m pytest tests/test_packs_lib.py tests/test_profile_api.py -q`
Expected: PASS.
Run: `python3 -m pytest -q && python3 scripts/card_schema.py`
Expected: full suite green; card_schema OK.

**Step 5: Commit**

```bash
git add scripts/task_dispatch.py scripts/task_server.py tests/
git commit -m "feat(phase-7): gate build_skills_catalog by active packs; derive PACK_CATALOG from manifest"
```

---

## Task 5: Document the contract + on-screen verify

**Files:**
- Modify: `.claude/CLAUDE.md` (Skills section — add the 3-line "add a skill to a pack" contract)

**Step 1:** Add to the Skills section of `.claude/CLAUDE.md`, after the auto-discovery paragraph:

```markdown
### Skill packs

`.claude/packs.yaml` groups skill folders into packs (core/pm/exec/eng/recruiting). The active list
lives in `profile/config.yaml` `active_skill_packs`; `core` is always active. Packs gate the
**background-worker dispatch catalog** and the Profile UI — not your interactive session. To add a
skill to a pack: drop the folder in `.claude/skills/` (auto-discovered), then add its folder name to
a pack's `skills:` in `packs.yaml`. A skill in no pack stays always-available.
```

**Step 2: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs(phase-7): document the skill-pack contract in .claude/CLAUDE.md"
```

**Step 3: On-screen verification (dev board :8743)**

- Find/restart the dev server (it loads `/api/*` at process start): `lsof -ti :8743 -sTCP:LISTEN`,
  confirm `ps` shows `scripts/task_server.py` from **this** repo (NOT `/Users/jayjenkins/pm-os`),
  kill it, relaunch from `/Users/jayjenkins/dev/pm-os-team`.
- Chrome.app headless screenshot + `--dump-dom` of the Engine → Profile room. Confirm the Skill-packs
  section renders the manifest-derived catalog (core/pm/exec/eng/recruiting), `core`+`pm` shown
  active per the live `config.yaml`. Toggle a pack, confirm it persists (re-GET `/api/profile`).
- Sanity: `python3 scripts/task_dispatch.py --dry-run` still runs; spot-check a dispatch log /
  prompt to confirm the catalog reflects active packs.

---

## PR 1 finish

Use **superpowers:finishing-a-development-branch**. Suite green + card_schema green + on-screen
verified → open PR `feat/phase-7-skill-packs` → `main` via `gh`. After merge, start PR 2 from fresh `main`.

---

# PR 2 — Model Tiering

**Branch:** `feat/phase-7-model-tiering` off `main` (after PR 1 merges).

## Task 6: `profile_lib.resolve_model` (the shift resolver)

**Files:**
- Modify: `scripts/profile_lib.py`
- Test: `tests/test_profile_lib.py`

**Step 1: Write the failing tests**

```python
import pytest
import profile_lib


@pytest.mark.parametrize("tier,posture,expected", [
    ("light",    "low",      "claude-haiku-4-5"),
    ("light",    "balanced", "claude-haiku-4-5"),
    ("light",    "high",     "claude-sonnet-4-6"),
    ("standard", "low",      "claude-haiku-4-5"),
    ("standard", "balanced", "claude-sonnet-4-6"),
    ("standard", "high",     "claude-opus-4-8"),
    ("deep",     "low",      "claude-sonnet-4-6"),
    ("deep",     "balanced", "claude-opus-4-8"),
    ("deep",     "high",     "claude-opus-4-8"),
])
def test_resolve_model_matrix(tier, posture, expected):
    assert profile_lib.resolve_model(tier, posture=posture) == expected


def test_resolve_model_override_by_model_id_wins():
    assert profile_lib.resolve_model("light", posture="low",
                                     task_override="claude-opus-4-8") == "claude-opus-4-8"


def test_resolve_model_override_by_tier_name_wins():
    assert profile_lib.resolve_model("light", posture="low", task_override="deep") == "claude-opus-4-8"


def test_resolve_model_defaults_tier_standard_and_posture_balanced():
    assert profile_lib.resolve_model(None) == "claude-sonnet-4-6"
    assert profile_lib.resolve_model("bogus", posture="bogus") == "claude-sonnet-4-6"


def test_resolve_model_reads_posture_from_config(profile_root):
    # profile_root config has cost_posture: balanced -> deep worker => opus
    assert profile_lib.resolve_model("deep", root=profile_root) == "claude-opus-4-8"
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_profile_lib.py -k resolve_model -q`
Expected: FAIL (`resolve_model` not defined).

**Step 3: Implement** (append to `scripts/profile_lib.py`)

```python
TIER_ORDER = ["light", "standard", "deep"]
TIER_MODELS = {
    "light": "claude-haiku-4-5",
    "standard": "claude-sonnet-4-6",
    "deep": "claude-opus-4-8",
}
_POSTURE_SHIFT = {"low": -1, "balanced": 0, "high": 1}
_DEFAULT_TIER = "standard"


def cost_posture(root=None):
    return (config(root).get("models") or {}).get("cost_posture") or "balanced"


def resolve_model(worker_tier, posture=None, task_override=None, root=None):
    """Resolve the model id for a dispatch.

    Precedence: task_override (a model id OR a tier name) wins. Otherwise the
    worker's declared tier is shifted by the posture (low -1 / balanced 0 /
    high +1) and clamped to [light, deep]. Unknown tier -> 'standard';
    unknown posture -> 'balanced'."""
    if task_override:
        if task_override in TIER_MODELS:            # a tier name
            return TIER_MODELS[task_override]
        return task_override                        # an explicit model id
    tier = worker_tier if worker_tier in TIER_ORDER else _DEFAULT_TIER
    if posture is None:
        posture = cost_posture(root)
    shift = _POSTURE_SHIFT.get(posture, 0)
    idx = max(0, min(len(TIER_ORDER) - 1, TIER_ORDER.index(tier) + shift))
    return TIER_MODELS[TIER_ORDER[idx]]
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_profile_lib.py -k resolve_model -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/profile_lib.py tests/test_profile_lib.py
git commit -m "feat(phase-7): profile_lib.resolve_model — tier x posture shift with per-task override"
```

---

## Task 7: Declare worker tiers

**Files:**
- Modify: `scripts/workers/grad-assessor.md`, `scheduler.md` → `tier: light`
- Modify: `scripts/workers/_default.md`, `message-writer.md`, `ticket-creator.md` → `tier: standard`
- Modify: `scripts/workers/eval-analyst.md`, `researcher.md`, `product-analyst.md` → `tier: deep`
- Test: `tests/test_packs_lib.py` is unrelated; add a worker-frontmatter test in a new
  `tests/test_worker_tiers.py`

**Step 1: Write the failing test**

```python
import os, re
WORKERS = os.path.join(os.path.dirname(__file__), "..", "scripts", "workers")
EXPECTED = {
    "grad-assessor": "light", "scheduler": "light",
    "_default": "standard", "message-writer": "standard", "ticket-creator": "standard",
    "eval-analyst": "deep", "researcher": "deep", "product-analyst": "deep",
}

def _tier(name):
    with open(os.path.join(WORKERS, f"{name}.md")) as f:
        fm = f.read().split("---", 2)[1]
    m = re.search(r"^tier:\s*(\S+)\s*$", fm, re.M)
    return m.group(1).strip().strip('"').strip("'") if m else None

def test_every_worker_declares_expected_tier():
    for name, tier in EXPECTED.items():
        assert _tier(name) == tier, f"{name} tier"
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_worker_tiers.py -q`
Expected: FAIL (no `tier:` lines yet).

**Step 3: Add `tier:` to each worker's frontmatter** (one line, e.g. after `priority:`). Example for
`researcher.md`:

```yaml
name: researcher
description: ...
priority: 10
tier: deep
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_worker_tiers.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/workers/ tests/test_worker_tiers.py
git commit -m "feat(phase-7): declare per-worker model tiers (light/standard/deep)"
```

---

## Task 8: Dispatch enforces `--model`

**Files:**
- Modify: `scripts/task_dispatch.py` (`dispatch_task`, ~lines 706–740; `_parse_worker_frontmatter`
  already returns the full frontmatter dict so `worker.get("tier")` works with no parser change)
- Test: `tests/test_dispatch_model.py`

**Step 1: Write the failing test**

Test the resolution wiring without launching `claude` — assert the resolved model and that `--model`
lands in the command. Factor the model decision into a tiny pure helper `_resolve_task_model(task, worker)`
so it is unit-testable:

```python
import task_dispatch

def test_resolve_task_model_uses_worker_tier(monkeypatch):
    monkeypatch.setattr("profile_lib.cost_posture", lambda root=None: "balanced")
    worker = {"name": "researcher", "tier": "deep"}
    assert task_dispatch._resolve_task_model({"id": "TASK-1"}, worker) == "claude-opus-4-8"

def test_resolve_task_model_task_override_wins(monkeypatch):
    monkeypatch.setattr("profile_lib.cost_posture", lambda root=None: "balanced")
    worker = {"name": "scheduler", "tier": "light"}
    task = {"id": "TASK-2", "model": "claude-opus-4-8"}
    assert task_dispatch._resolve_task_model(task, worker) == "claude-opus-4-8"

def test_resolve_task_model_defaults_when_no_tier(monkeypatch):
    monkeypatch.setattr("profile_lib.cost_posture", lambda root=None: "balanced")
    assert task_dispatch._resolve_task_model({"id": "T"}, {"name": "x"}) == "claude-sonnet-4-6"
```

**Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_dispatch_model.py -q`
Expected: FAIL (`_resolve_task_model` not defined).

**Step 3: Implement**

Add the helper and wire it into the command. In `scripts/task_dispatch.py`:

```python
def _resolve_task_model(task, worker):
    """Resolve the --model for a dispatch from the worker's tier + posture, with
    a per-task override (task frontmatter 'model' or 'tier')."""
    import profile_lib
    override = task.get("model") or task.get("tier")
    tier = (worker or {}).get("tier")
    return profile_lib.resolve_model(tier, task_override=override)
```

Then in `dispatch_task`, after the prompt/tools block (~line 715), resolve and inject the flag:

```python
    model = _resolve_task_model(task, worker)
    log(f"Model: {model}", task_id=task_id)

    claude_cmd = [
        "claude",
        prompt,
        "--model", model,
        "--allowedTools", tools_str,
        "--max-turns", max_turns,
        "--permission-mode", "bypassPermissions",
    ]
```

> The dispatcher's `task` dict comes from `task.sh list --json` (no `model`/`tier` keys today) — a
> per-task override is read straight off that dict, so the override path is exercised only when a
> task sets it. That is fine; the worker-tier path is the default.

**Step 4: Run focused, then suite**

Run: `python3 -m pytest tests/test_dispatch_model.py -q`
Expected: PASS.
Run: `python3 -m pytest -q`
Expected: full suite green.

**Step 5: Commit**

```bash
git add scripts/task_dispatch.py tests/test_dispatch_model.py
git commit -m "feat(phase-7): dispatch passes --model resolved from worker tier + posture (per-task override)"
```

---

## Task 9: Surface resolved model in `build_profile`

**Files:**
- Modify: `scripts/task_server.py` (`_profile_workers` ~line 325, `build_profile` model_posture
  ~line 419)
- Test: `tests/test_profile_api.py`

**Step 1: Write the failing test**

```python
def test_model_posture_workers_include_resolved_model(profile_root, monkeypatch):
    import task_server
    # Make _profile_workers return a known worker tier regardless of real files
    monkeypatch.setattr(task_server, "_profile_workers",
                        lambda root=None: [{"name": "researcher", "tier": "deep"}])
    p = task_server.build_profile(root=profile_root)   # config posture: balanced
    w = p["model_posture"]["workers"][0]
    assert w["tier"] == "deep"
    assert w["model"] == "claude-opus-4-8"   # deep @ balanced
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_profile_api.py -k resolved_model -q`
Expected: FAIL (`workers[0]` has no `model` key).

**Step 3: Implement** — in `build_profile`, enrich the worker list with the resolved model at the
current posture:

```python
    posture_level = (cfg.get("models") or {}).get("cost_posture") or "balanced"
    workers = _profile_workers(root)
    for w in workers:
        w["model"] = profile_lib.resolve_model(w.get("tier"), posture=posture_level)
    model_posture = {"level": posture_level, "workers": workers}
```

**Step 4: Run focused, then suite + card_schema**

Run: `python3 -m pytest tests/test_profile_api.py -q`
Expected: PASS.
Run: `python3 -m pytest -q && python3 scripts/card_schema.py`
Expected: full suite green; card_schema OK.

**Step 5: Commit**

```bash
git add scripts/task_server.py tests/test_profile_api.py
git commit -m "feat(phase-7): build_profile surfaces resolved model per worker at current posture"
```

---

## Task 10: On-screen verify (dev board :8743)

- Restart the dev server (same procedure as Task 5 Step 3 — `/api/*` loads at process start).
- Chrome.app headless screenshot + `--dump-dom` of Engine → Profile → Model-posture section.
  Confirm the eight workers now list with their tiers (the list was empty before). Switch posture
  low → balanced → high via the UI; confirm the resolved model per worker shifts per the matrix
  (e.g. researcher: Sonnet → Opus → Opus; scheduler: Haiku → Haiku → Sonnet) and persists
  (re-GET `/api/profile`).
- Optional: `python3 scripts/task_dispatch.py --task TASK-9201 --dry-run` and confirm a `Model: …`
  line appears in the dispatch log for the matched worker.

---

## PR 2 finish

Use **superpowers:finishing-a-development-branch**. Suite green + card_schema green + on-screen
verified → open PR `feat/phase-7-model-tiering` → `main` via `gh`.

---

## Notes carried from the design (do NOT pull in)

The factory (`meta-create-*`, step 8); UI skill-authoring; pack-contents in the UI; judge-driven
downshift suggestions; ladder-tier dispatch enforcement; task→transcript join;
`description_patterns` matcher; `ladder.json` concurrency; `receipt_summary` backend; commit
scoping. All remain out of scope.
