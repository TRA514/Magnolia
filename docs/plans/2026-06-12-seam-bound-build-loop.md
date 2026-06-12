# Seam-Bound Build Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `/magnolia-build` keep less-technical operators "in the fairway" by binding every extension to the architecture's seam before code is written — via two new pre-factory sub-skills and one portability gate.

**Architecture:** Add `meta-scope-extension` (decompose the ask onto the four extension surfaces; decide reuse/extend/new; emit a build-contract) and `meta-integration-discovery` (probe external-system capability before building an adapter). Add `scripts/portability_gate.py`, a dumb-fast denylist scan over runtime code that mirrors `test_engine_no_jay.py` and closes the `platform_lib` seam. Rewrite `workflow-magnolia-build` to run these in the loop and brief subagents with each surface's contract. The new skills sit *in front of* the existing `meta-create-*` factories without changing them.

**Tech Stack:** Python 3.12 (stdlib `re`/`glob`/`pathlib`), pytest, markdown SKILL.md files, ruamel.yaml for packs.

Design doc: `docs/plans/2026-06-12-seam-bound-build-loop-design.md`

**Gates (run before every code commit):**
- `python3 -m pytest -q`
- `python3 scripts/card_schema.py` → `registry.json OK`
- `python3 -m pytest tests/test_engine_no_jay.py -q`
- (after Task 1) `python3 scripts/portability_gate.py` → `portability OK`

---

## Task 1: Portability gate

The one new gate. A denylist scan over runtime code (NOT markdown — `.md` legitimately
uses em-dashes). Catches the source-code manifestation of the beta-user failures:
em-dash/en-dash in string literals, direct `.sh`/bash invocation, OS branches outside
the `platform_lib` seam, `start_new_session=`, and hardcoded path separators.

**Files:**
- Create: `scripts/portability_gate.py`
- Test: `tests/test_portability_gate.py`

**Step 1: Write the failing test**

```python
# tests/test_portability_gate.py
import sys, os, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import portability_gate as pg

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_flags_em_dash_in_source(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text('msg = "9 AM—5 PM"\n', encoding="utf-8")  # em-dash U+2014
    offenders = pg.scan([str(f)])
    assert any("em-dash" in o or "non-ascii" in o for o in offenders)


def test_flags_direct_sh_invocation(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text('subprocess.Popen(["bash", "x.sh"])\n', encoding="utf-8")
    offenders = pg.scan([str(f)])
    assert any("shell script" in o or ".sh" in o for o in offenders)


def test_flags_os_name_branch_outside_seam(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("if os.name == 'nt':\n    pass\n", encoding="utf-8")
    offenders = pg.scan([str(f)])
    assert any("os.name" in o or "platform branch" in o for o in offenders)


def test_flags_start_new_session(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("Popen(cmd, start_new_session=True)\n", encoding="utf-8")
    offenders = pg.scan([str(f)])
    assert any("start_new_session" in o for o in offenders)


def test_clean_file_passes(tmp_path):
    f = tmp_path / "good.py"
    f.write_text('msg = "9 AM - 5 PM"\nPopen([sys.executable, "x.py"], **process_group_kwargs())\n',
                 encoding="utf-8")
    assert pg.scan([str(f)]) == []


def test_repo_is_green():
    """The gate MUST pass on the real repo or it is not shippable."""
    assert pg.validate() == [], "portability offenders on main:\n" + "\n".join(pg.validate())
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_portability_gate.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'portability_gate'`

**Step 3: Write minimal implementation**

```python
# scripts/portability_gate.py
"""Portability gate — a dumb-fast denylist scan over runtime code.

Mirrors tests/test_engine_no_jay.py. Catches the leak-past-the-seam patterns that
broke beta users on Windows: em-dash/en-dash in source string literals, direct
.sh/bash invocation, OS branches outside the platform_lib seam, start_new_session=,
and hardcoded path separators. Scans CODE only (.py/.js) — markdown docs legitimately
use em-dashes and are not emitted to a Windows terminal. Runtime-GENERATED text
(agent output) is out of scope here and stays loop discipline.

The OS seam is scripts/platform_lib.py — it is allowlisted (it legitimately branches
on OS so the rest of the engine never has to).
"""
import os, re, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEAM = os.path.join(ROOT, "scripts", "platform_lib.py")

# (pattern, label) — each flags one leak class.
RULES = [
    (re.compile(r"[–—]"),               "non-ascii dash (use '-' — em/en-dash garbles on Windows CP437)"),
    (re.compile(r"[‘’“”]"),    "non-ascii smart quote (use ASCII quotes)"),
    (re.compile(r"\bstart_new_session\s*="),       "start_new_session= (use platform_lib.process_group_kwargs())"),
    (re.compile(r"os\.name\s*==\s*['\"]nt['\"]"),  "os.name=='nt' platform branch (route through platform_lib)"),
    (re.compile(r"sys\.platform"),                 "sys.platform branch (route through platform_lib.os_kind())"),
    (re.compile(r"""\[\s*["']bash["']"""),         "direct bash invocation of a shell script (call Python via sys.executable)"),
    (re.compile(r"""["'][^"']*\.sh["']"""),        "invoking a .sh shell script (port to Python; .sh is non-portable)"),
]


def _targets():
    return [
        f for f in (
            glob.glob(os.path.join(ROOT, "scripts", "**", "*.py"), recursive=True) +
            glob.glob(os.path.join(ROOT, "ui", "task-board", "js", "**", "*.js"), recursive=True) +
            glob.glob(os.path.join(ROOT, "scripts", "adapters", "**", "*.py"), recursive=True)
        )
        if os.path.abspath(f) != os.path.abspath(SEAM)
        and "__pycache__" not in f
        and os.path.sep + "tests" + os.path.sep not in f
    ]


def scan(paths):
    offenders = []
    for f in paths:
        try:
            text = open(f, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for rx, label in RULES:
            if rx.search(text):
                offenders.append(f"{os.path.relpath(f, ROOT)}: {label}")
    return offenders


def validate():
    return scan(_targets())


if __name__ == "__main__":
    import sys
    errs = validate()
    if errs:
        print("\n".join(errs)); sys.exit(1)
    print("portability OK")
```

**Step 4: Run the unit tests (not yet the repo-green one)**

Run: `python3 -m pytest tests/test_portability_gate.py -q -k "not repo_is_green"`
Expected: PASS (all five fixture tests)

**Step 5: Triage the repo-green test**

Run: `python3 scripts/portability_gate.py`
- If it prints `portability OK` → great, the repo is clean; skip to Step 6.
- If it lists offenders → triage EACH:
  - A genuine leak (e.g. an `os.name=='nt'` in a non-seam file) → fix it by routing
    through `scripts/platform_lib.py` (see `os_kind`, `resolve_tool`, `open_file_cmd`,
    `process_group_kwargs`). This is the gate doing its job.
  - A false positive (a regex that's too broad for legitimate code) → tighten the
    RULE pattern in `portability_gate.py`, do NOT weaken the intent. Re-run.
- Note: `ui/task-board/js/tasks.js` may contain an en-dash in a time formatter; if so,
  replace it with a hyphen (this is exactly the bug class, now caught on main).

**Step 6: Run the full test file + commit**

Run: `python3 -m pytest tests/test_portability_gate.py -q`
Expected: PASS (including `test_repo_is_green`)

```bash
git add scripts/portability_gate.py tests/test_portability_gate.py
# plus any platform_lib-routing fixes from Step 5
git commit -m "feat(gate): portability scan closes the platform_lib seam

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `meta-scope-extension` sub-skill

The decomposition brain. Maps the ask onto the four surfaces, decides reuse/extend/new,
emits a build-contract. Structural test first (RED), then write the SKILL.md (GREEN) —
mirrors `meta-create-skill`'s RED-GREEN spine and `test_factory_skills.py`'s style.

**Files:**
- Create: `.claude/skills/meta-scope-extension/SKILL.md`
- Test: add to `tests/test_factory_skills.py` (keep all factory-skill structural checks together)

**Step 1: Write the failing test** (append to `tests/test_factory_skills.py`)

```python
def test_meta_scope_extension_exists_and_frontmatter():
    body = _read(".claude/skills/meta-scope-extension/SKILL.md")
    assert body.startswith("---\n")
    fm = body.split("---\n", 2)[1]
    assert "name: meta-scope-extension" in fm
    assert "Use when" in fm
    # decomposes onto the four extension surfaces
    for surface in ("adapter", "worker", "card", "platform"):
        assert surface in body.lower()
    # the reuse/extend/new decision is explicit
    assert "reuse" in body.lower()
    assert "build contract" in body.lower() or "build-contract" in body.lower()
    # routes to the factories + names the JS-vs-compose boundary for cards
    assert "meta-create-worker" in body
    assert "meta-create-card-type" in body
    assert "meta-create-adapter" in body
    assert "meta-integration-discovery" in body   # delegates external probing
    assert "card-registry.js" in body or "JS work" in body  # composition boundary
    # binds to the seam, names platform_lib
    assert "platform_lib" in body


def test_meta_scope_extension_denylist_clean():
    import re
    body = _read(".claude/skills/meta-scope-extension/SKILL.md")
    for pat in (r"\bjay\b", r"board 1096", r"/Users/", r"~/pm-os"):
        assert not re.search(pat, body, re.IGNORECASE), f"leaks /{pat}/"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_factory_skills.py -q -k scope_extension`
Expected: FAIL with `FileNotFoundError` (SKILL.md not created yet)

**Step 3: Write `.claude/skills/meta-scope-extension/SKILL.md`**

Frontmatter:
```yaml
---
name: meta-scope-extension
description: Use when /magnolia-build has an approved design and must decompose it onto the engine's extension surfaces — decides reuse vs extend vs build-new per surface and emits a build contract that briefs each subagent. Runs before the meta-create-* factories.
---
```

Body MUST contain, as sections:
1. **The four surfaces** — a table: `adapter` → `scripts/adapters/<family>/<provider>.py`;
   `worker` → `scripts/workers/<name>.md`; `card` → `registry.json` (compose) OR
   `js/card-registry.js` (new piece = JS work); `platform/UI` → existing code +
   `scripts/platform_lib.py`.
2. **The reuse-first rule** — inventory what exists before proposing new. For workers:
   list `scripts/workers/*.md` and ask "does one already match?" For cards: list the
   existing signals/actions/body-renderers (point at `meta-create-card-type` which
   enumerates them) and decide compose-vs-JS-work; flag JS work to the operator *now*.
   For adapters: check `profile/integrations.yaml` + existing `scripts/adapters/<family>/`.
3. **When external → delegate to `meta-integration-discovery`** before deciding the
   adapter, so the capability is validated first.
4. **The build contract (output)** — a section the skill writes into the plan, listing
   per touched surface: the decision (reuse | extend | build-new), the exact factory or
   seam to use, and the gate that proves it (`validate-worker` / `card_schema.py` /
   `validate-adapter` / `portability_gate.py` + `pytest`). This is what the orchestrator
   hands each subagent.
5. **Iron laws** — never propose build-new where reuse fits; never let a card reference
   a piece that doesn't exist (that's JS work, hand it to engineering — mirror
   `meta-create-card-type`'s hard boundary); capture team nuance to `profile/`, never the
   artifact; bind every surface to its seam.
6. **Related skills** — the `meta-create-*` trio, `meta-integration-discovery`,
   `meta-factory-core`.

Keep it denylist-clean (read identity from `profile/`; use no personal literals).

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_factory_skills.py -q -k scope_extension`
Expected: PASS (both new tests)

**Step 5: Commit**

```bash
git add .claude/skills/meta-scope-extension/SKILL.md tests/test_factory_skills.py
git commit -m "feat(skill): meta-scope-extension — decompose onto surfaces, emit build contract

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `meta-integration-discovery` sub-skill

The external-capability probe. Invoked by `meta-scope-extension` when a surface touches
an external system; de-risks the mechanism choice before `meta-create-adapter`.

**Files:**
- Create: `.claude/skills/meta-integration-discovery/SKILL.md`
- Test: add to `tests/test_factory_skills.py`

**Step 1: Write the failing test** (append to `tests/test_factory_skills.py`)

```python
def test_meta_integration_discovery_exists_and_frontmatter():
    body = _read(".claude/skills/meta-integration-discovery/SKILL.md")
    assert body.startswith("---\n")
    fm = body.split("---\n", 2)[1]
    assert "name: meta-integration-discovery" in fm
    assert "Use when" in fm
    # the four-step probe
    assert "mechanism" in body.lower()      # enumerate MCP / CLI / REST
    assert "MCP" in body
    assert "read-only" in body.lower()      # validate capability via read-only probe
    assert "scope" in body.lower()          # auth/scope reality
    assert "Tier-2" in body or "Tier 2" in body  # consent surface
    # feeds the adapter factory + reads structured targets from profile
    assert "meta-create-adapter" in body
    assert "profile/integrations.yaml" in body
    # produces a findings doc
    assert "findings" in body.lower()


def test_meta_integration_discovery_denylist_clean():
    import re
    body = _read(".claude/skills/meta-integration-discovery/SKILL.md")
    for pat in (r"\bjay\b", r"board 1096", r"/Users/", r"~/pm-os"):
        assert not re.search(pat, body, re.IGNORECASE), f"leaks /{pat}/"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_factory_skills.py -q -k integration_discovery`
Expected: FAIL with `FileNotFoundError`

**Step 3: Write `.claude/skills/meta-integration-discovery/SKILL.md`**

Frontmatter:
```yaml
---
name: meta-integration-discovery
description: Use when an extension touches an external system and the mechanism is unsettled (MCP vs CLI vs REST) — probes which mechanism can actually do the job, validates the capability read-only, confirms auth/scope reality, and writes a findings doc that feeds meta-create-adapter. Invoked by meta-scope-extension.
---
```

Body MUST contain, as sections:
1. **The four-step probe** — (a) *enumerate mechanisms*: connected MCP server? a CLI
   (e.g. `mgc`)? a REST API? what's already wired in `profile/integrations.yaml`?
   (b) *validate the capability exists* via read-only probes ONLY (e.g. can the M365 MCP
   read incoming invites? does the CLI expose the needed command?) — never a write
   during discovery; (c) *confirm auth/scope reality*: what is authorized now, what needs
   consent, which scopes — name that the first external write is **Tier-2** (one
   plain-language confirm); (d) *findings doc*: mechanism chosen + why, capability
   evidence, auth/scope needs, gaps.
2. **Hand-off to `meta-create-adapter`** — the findings doc fills the adapter factory's
   "capture the spec" with the decision already de-risked; structured targets land in
   `profile/integrations.yaml`, fuzzy nuance via `set_integration_conventions`.
3. **Iron laws** — read-only during discovery (no external writes); never assume a
   capability exists without a probe; structured targets to `profile/`, never the
   artifact; the first real write is Tier-2.
4. **Worked example** — the calendar-invite-triage case (recommend accept/decline):
   decide M365 MCP vs a CLI, prove it can read invites + calendar, note the scopes.
5. **Related skills** — `meta-scope-extension` (caller), `meta-create-adapter` (callee),
   `workflow-doctor` (for auth remediation), `meta-factory-core`.

Keep it denylist-clean.

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_factory_skills.py -q -k integration_discovery`
Expected: PASS

**Step 5: Commit**

```bash
git add .claude/skills/meta-integration-discovery/SKILL.md tests/test_factory_skills.py
git commit -m "feat(skill): meta-integration-discovery — probe external capability before building an adapter

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Rewrite `workflow-magnolia-build` to run the new loop

Wire the two sub-skills + the gate into the orchestrator, and add the seam-bound
subagent-briefing discipline. This is an edit, not a rewrite from scratch — preserve the
preflight (Step 0), reference grounding (Step 1), kickoff/merge-authority (Step 2), and
the iron laws.

**Files:**
- Modify: `.claude/skills/workflow-magnolia-build/SKILL.md`
- Test: `tests/test_magnolia_build_loop.py` (new)

**Step 1: Write the failing test**

```python
# tests/test_magnolia_build_loop.py
import pathlib, re
REPO = pathlib.Path(__file__).resolve().parent.parent
SKILL = REPO / ".claude/skills/workflow-magnolia-build/SKILL.md"


def test_loop_wires_the_new_subskills_and_gate():
    body = SKILL.read_text()
    # the new scoping step sits between brainstorm and writing-plans
    assert "meta-scope-extension" in body
    assert "meta-integration-discovery" in body
    # the portability gate is named among the gates the loop runs
    assert "portability_gate" in body
    # the seam-binding idea is explicit: subagents get a per-surface contract
    assert "build contract" in body.lower() or "build-contract" in body.lower()
    assert "contract" in body.lower()
    # preserved structure
    assert "brainstorming" in body
    assert "writing-plans" in body
    assert "subagent-driven-development" in body
    assert "finishing-a-development-branch" in body


def test_magnolia_build_denylist_clean():
    body = SKILL.read_text()
    for pat in (r"\bjay\b", r"board 1096", r"/Users/", r"~/pm-os"):
        assert not re.search(pat, body, re.IGNORECASE), f"leaks /{pat}/"
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_magnolia_build_loop.py -q`
Expected: FAIL (`portability_gate`, `meta-scope-extension`, etc. not yet in the SKILL.md)

**Step 3: Edit the SKILL.md**

Make these surgical changes:
- **Step 4 (Route):** expand so that BEFORE routing, the loop runs `meta-scope-extension`
  to decompose onto surfaces and produce the build contract. Known single-surface
  extensions still go to the matching factory; multi-surface/novel features run the full
  loop — but in BOTH cases the build contract is produced first.
- **Step 5 (Run the loop):** insert a new sub-step between `brainstorming` and
  `writing-plans`: "**scope-extension** — decompose onto surfaces, decide reuse/extend/new,
  emit the build contract; run `meta-integration-discovery` for any external surface."
  Then in the `subagent-driven-development` sub-step, add: "brief each subagent with its
  surface's **contract** from the build contract — the exact factory/seam, the
  composition boundary, the gate — never a bare 'build a card'. Bind it to the seam."
- **Gates:** wherever the loop names the green gates, add the fourth:
  `python3 scripts/portability_gate.py` → `portability OK`.
- **Iron laws:** add one — "**Bind to the seam before building.** Decompose onto a
  surface and brief the subagent with that surface's contract; never let it improvise in
  a layer the architecture already owns (`platform_lib` for OS, the card registry for
  display, `profile_lib` for identity)."
- **Ship step:** keep it simple for a local, no-PR project (gates green → commit on a
  branch / merge to main per the kickoff choice). Do not add PR ceremony.

Keep denylist-clean.

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_magnolia_build_loop.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add .claude/skills/workflow-magnolia-build/SKILL.md tests/test_magnolia_build_loop.py
git commit -m "feat(skill): magnolia-build runs scope-extension + portability gate, briefs subagents with seam contracts

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Pack membership + reference docs + full gate sweep

Make the new skills discoverable to background workers/Profile UI, record the new gate
as a first-class invariant, and prove everything green together.

**Files:**
- Modify: `.claude/packs.yaml` (add both skills to `core`)
- Modify: `docs/reference/invariants.md` (add the portability law)
- Modify: `docs/reference/conventions.md` (§2 — name the fourth gate)
- Test: add to `tests/test_factory_skills.py`

**Step 1: Write the failing test** (append to `tests/test_factory_skills.py`)

```python
def test_scope_skills_in_core_pack():
    from ruamel.yaml import YAML
    packs = YAML(typ="safe").load((REPO / ".claude/packs.yaml").read_text())
    core = packs["core"]["skills"]
    assert "meta-scope-extension" in core
    assert "meta-integration-discovery" in core
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_factory_skills.py -q -k core_pack`
Expected: FAIL (`test_scope_skills_in_core_pack`)

**Step 3: Make the changes**

- `.claude/packs.yaml`: add `meta-scope-extension` and `meta-integration-discovery` to
  the `core` pack's `skills:` list (next to the `meta-create-*` entries).
- `docs/reference/invariants.md`: add invariant **#8** —
  `Code stays portable; OS/encoding specifics go through scripts/platform_lib.py — never hand-rolled.`
  Why: `The platform_lib epic built the OS seam; leaking past it reintroduces the Windows/encoding bugs.`
  Enforced by: `python3 scripts/portability_gate.py` (→ `portability OK`).
- `docs/reference/conventions.md` §2: add the fourth gate to the list operators run
  before a code commit: `python3 scripts/portability_gate.py`.

**Step 4: Run the test**

Run: `python3 -m pytest tests/test_factory_skills.py -q -k core_pack`
Expected: PASS

**Step 5: Full gate sweep (all four gates green together)**

Run, expecting all green:
```bash
python3 -m pytest -q
python3 scripts/card_schema.py            # registry.json OK
python3 -m pytest tests/test_engine_no_jay.py -q
python3 scripts/portability_gate.py       # portability OK
```

**Step 6: Commit**

```bash
git add .claude/packs.yaml docs/reference/invariants.md docs/reference/conventions.md tests/test_factory_skills.py
git commit -m "feat: register scope skills in core pack; record portability as invariant #8

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Definition of done

- All four gates green (`pytest`, `card_schema.py`, `test_engine_no_jay.py`, `portability_gate.py`).
- `meta-scope-extension` and `meta-integration-discovery` exist, are denylist-clean, and are in the `core` pack.
- `workflow-magnolia-build` runs scope-extension (+ integration-discovery for external surfaces) and the portability gate, and briefs subagents with per-surface contracts.
- Portability invariant #8 recorded with the gate as its enforcement.
- e2e: run `/magnolia-build` mentally against the calendar-invite-triage example and confirm the loop decomposes it (adapter via integration-discovery → reuse-or-new worker → compose-or-JS card) before any code — verified in the build session.
```
