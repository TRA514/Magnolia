# Phase 9 Factory — PR1: meta-factory-core + meta-create-worker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the factory spine on the lowest-risk artifact — a `meta-create-worker` skill that scaffolds a new `scripts/workers/<name>.md`, plus a shared `meta-factory-core` skill and a testable `scripts/factory_lib.py` that commits precisely and emits a Keep/Undo receipt card. Also add the free-form `conventions` profile slot so team nuance is captured to profile, never into the artifact.

**Architecture:** Skills are markdown; the mechanical work (precise git staging, commit, receipt emission, worker validation) lives in `scripts/factory_lib.py` so it is unit-tested rather than LLM-improvised. The factory self-emits a `receipt` task `.md` carrying `revert_commit` + `receipt_summary`; the existing `task_server.undo_receipt` git-revert handler powers Undo unchanged (no backend change). Generated workers read all identity/team specifics from `profile/` (instruct-to-read-profile) and are therefore denylist-clean by construction, enforced by the standing `tests/test_engine_no_jay.py` guard.

**Tech Stack:** Python 3 (Homebrew, PEP-668 → `pip install --break-system-packages` if needed), `ruamel.yaml`, `pytest`. No JS in this PR. Verify the factory live against the dev board on `:8743`.

**Conventions:**
- Branch already created: `feat/phase-9-factory-pr1-worker`. Git author is set locally.
- Run tests with `python3 -m pytest`. Keep `python3 scripts/card_schema.py` and `python3 -m pytest tests/test_engine_no_jay.py` green.
- End every commit message with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Do NOT touch `/Users/jayjenkins/pm-os` (production). Dev board only on `:8743`.

---

## Task 1: Free-form `conventions` profile slot + accessor/setter

The factory captures team nuance (e.g. "always set Sprint", "titles prefixed `[Area]`") into the profile, never into the artifact. Add a `conventions` field to the Jira block and a generic setter; `jira_config()` already returns the whole jira sub-block, so reads come for free.

**Files:**
- Modify: `profile.example/integrations.yaml` (add `conventions: ""` to the `jira` block)
- Modify: `scripts/profile_lib.py` (add `set_integration_conventions`)
- Test: `tests/test_factory_conventions.py` (create)

**Step 1: Write the failing test**

Create `tests/test_factory_conventions.py`:

```python
"""Phase 9 PR1 — free-form team conventions captured into profile, never the artifact."""
import os
import importlib


def _profile(tmp_path):
    """A throwaway live profile dir with a minimal integrations.yaml."""
    pdir = tmp_path / "profile"
    pdir.mkdir()
    (pdir / "integrations.yaml").write_text(
        "project_management:\n"
        '  provider: "jira"\n'
        "  jira:\n"
        '    project_key: "ABC"\n'
        '    conventions: ""\n'
    )
    return str(tmp_path)


def test_set_and_read_jira_conventions(tmp_path):
    import profile_lib
    importlib.reload(profile_lib)
    root = _profile(tmp_path)
    profile_lib.set_integration_conventions(
        "project_management", "Always set Sprint; titles prefixed [Area].",
        provider="jira", root=root)
    cfg = profile_lib.jira_config(root=root)
    assert cfg["conventions"] == "Always set Sprint; titles prefixed [Area]."


def test_set_conventions_preserves_siblings(tmp_path):
    import profile_lib
    importlib.reload(profile_lib)
    root = _profile(tmp_path)
    profile_lib.set_integration_conventions(
        "project_management", "note", provider="jira", root=root)
    cfg = profile_lib.jira_config(root=root)
    assert cfg["project_key"] == "ABC"  # sibling field untouched


def test_example_integrations_has_conventions_field():
    """The template documents the slot so users/onboarding can see it."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(repo, "profile.example", "integrations.yaml")).read()
    assert "conventions:" in text
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_factory_conventions.py -v`
Expected: FAIL — `AttributeError: module 'profile_lib' has no attribute 'set_integration_conventions'` (and the example-field test fails until Step 4).

**Step 3: Implement the setter**

In `scripts/profile_lib.py`, add after `set_integration_provider` (around line 241):

```python
def set_integration_conventions(category, text, provider=None, root=None):
    """Write free-form team conventions into integrations.yaml.

    Conventions are fuzzy team nuance that has no structured field (e.g. "always
    set the Sprint field", "bug titles prefixed [Area]"). They live in the PROFILE,
    never in a generated artifact, so the artifact stays denylist-clean and the
    nuance stays editable. With provider set, nests under
    <category>.<provider>.conventions (so jira_config()['conventions'] surfaces it);
    otherwise <category>.conventions. Siblings + comments are preserved."""
    def mutate(doc):
        cat = doc.get(category)
        if not isinstance(cat, dict):
            cat = {}
            doc[category] = cat
        target = cat
        if provider:
            sub = cat.get(provider)
            if not isinstance(sub, dict):
                sub = {}
                cat[provider] = sub
            target = sub
        target["conventions"] = text
    _update_yaml("integrations.yaml", mutate, root)
```

**Step 4: Add the field to the template**

In `profile.example/integrations.yaml`, add to the `jira:` block (after `product_area`):

```yaml
    conventions: ""      # free-form team nuance the factory captures (e.g. "always set Sprint")
```

**Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_factory_conventions.py -v`
Expected: PASS (3 tests).

**Step 6: Commit**

```bash
git add scripts/profile_lib.py profile.example/integrations.yaml tests/test_factory_conventions.py
git commit -m "feat(factory): free-form conventions profile slot + setter

Team nuance with no structured field is captured into profile (never the
artifact), keeping generated artifacts denylist-clean. jira_config() surfaces it.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `scripts/factory_lib.py` — precise commit + receipt emission + worker validation

The shared mechanism for all three factories. Stages **only** the named files (fixes the `git add -A` wart), commits, captures the sha, and emits a `receipt` card with `revert_commit` + `receipt_summary`. Mirrors `task_server.apply_recommendation`'s receipt shape so `undo_receipt` works unchanged.

**Files:**
- Create: `scripts/factory_lib.py`
- Test: `tests/test_factory_lib.py`

**Step 1: Write the failing test**

Create `tests/test_factory_lib.py`:

```python
"""Phase 9 PR1 — factory_lib: precise staging, receipt emission, worker validation.

Git ops run with git -C factory_lib.PM_OS_DIR; the round-trip Undo test also points
task_server.PM_OS_DIR at the same throwaway repo. Uses the tasks_root fixture so
receipt cards write to a throwaway task tree.
"""
import subprocess
import pytest


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(str(repo), "init")
    _git(str(repo), "config", "user.email", "t@e.com")
    _git(str(repo), "config", "user.name", "t")
    (repo / "seed.txt").write_text("seed\n")
    _git(str(repo), "add", "."); _git(str(repo), "commit", "-m", "init")
    return repo


def test_commit_emits_receipt_with_revert_commit(tasks_root, tmp_path, monkeypatch):
    import factory_lib, task_lib
    repo = _repo(tmp_path)
    (repo / "new.md").write_text("scaffolded\n")
    monkeypatch.setattr(factory_lib, "PM_OS_DIR", str(repo))
    rid = factory_lib.commit_and_emit_receipt(
        "a sample worker", files=["new.md"], kind="worker")
    fm = task_lib.read_task(rid)["frontmatter"]
    assert fm["card_type"] == "receipt"
    assert fm.get("revert_commit")
    assert fm.get("receipt_summary") == "a sample worker"
    assert fm.get("factory_kind") == "worker"


def test_staging_is_precise_not_add_all(tasks_root, tmp_path, monkeypatch):
    """Only the named file is committed; an unrelated dirty file stays uncommitted."""
    import factory_lib
    repo = _repo(tmp_path)
    (repo / "new.md").write_text("scaffolded\n")
    (repo / "unrelated.txt").write_text("do not commit me\n")
    monkeypatch.setattr(factory_lib, "PM_OS_DIR", str(repo))
    factory_lib.commit_and_emit_receipt("x", files=["new.md"], kind="worker")
    # unrelated.txt must still be untracked (not swept into the factory commit)
    status = _git(str(repo), "status", "--porcelain").stdout
    assert "unrelated.txt" in status


def test_empty_scaffold_raises(tasks_root, tmp_path, monkeypatch):
    import factory_lib
    repo = _repo(tmp_path)
    monkeypatch.setattr(factory_lib, "PM_OS_DIR", str(repo))
    with pytest.raises(factory_lib.FactoryError):
        factory_lib.commit_and_emit_receipt("x", files=["seed.txt"], kind="worker")  # unchanged


def test_undo_reverts_factory_commit(tasks_root, tmp_path, monkeypatch):
    import factory_lib, task_server
    repo = _repo(tmp_path)
    (repo / "new.md").write_text("scaffolded\n")
    monkeypatch.setattr(factory_lib, "PM_OS_DIR", str(repo))
    monkeypatch.setattr(task_server, "PM_OS_DIR", str(repo))
    rid = factory_lib.commit_and_emit_receipt("x", files=["new.md"], kind="worker")
    assert (repo / "new.md").exists()
    task_server.undo_receipt(rid)
    assert not (repo / "new.md").exists()  # revert removed the added file


def test_validate_worker_accepts_good_and_flags_missing_fields(tmp_path):
    import factory_lib
    good = tmp_path / "good.md"
    good.write_text(
        "---\nname: sample\ndescription: Use when x\npriority: 10\ntier: standard\n"
        "match:\n  task_type: []\nallowed_tools:\n  - \"Bash(*)\"\nskills: []\n"
        "timeout: 300\nmax_turns: 15\n---\n\nbody\n")
    assert factory_lib.validate_worker(str(good)) == []
    bad = tmp_path / "bad.md"
    bad.write_text("---\nname: sample\ndescription: Use when x\n---\n\nbody\n")
    problems = factory_lib.validate_worker(str(bad))
    assert any("tier" in p for p in problems)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_factory_lib.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory_lib'`.

**Step 3: Implement `scripts/factory_lib.py`**

```python
"""scripts/factory_lib.py — shared mechanism for the meta-create-* factory skills.

Two jobs:
  1. commit_and_emit_receipt() — stage EXACTLY the scaffolded files (precise
     staging, not `git add -A`), commit, and emit a `receipt` card carrying
     revert_commit + receipt_summary. The existing task_server.undo_receipt
     git-revert handler powers one-tap Undo unchanged. Git stays invisible — the
     board only ever shows Keep / Undo.
  2. validate_worker() — structural gate for a scaffolded worker .md (frontmatter
     parses + required fields). Denylist-cleanliness is enforced separately by the
     standing tests/test_engine_no_jay.py guard, so it is not duplicated here.
"""
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PM_OS_DIR = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import task_lib  # noqa: E402

_REQUIRED_WORKER_FIELDS = ("name", "description", "priority", "tier", "match",
                           "allowed_tools", "timeout", "max_turns")


class FactoryError(RuntimeError):
    """A factory step failed in an operator-actionable way."""


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def commit_and_emit_receipt(summary, files, kind, root=None):
    """Stage exactly `files`, commit, emit a receipt card. Returns the receipt task id.

    summary : human one-liner shown on the card ("a sample worker").
    files   : repo-relative paths the factory created/modified (precise staging).
    kind    : 'worker' | 'card-type' | 'adapter' (stored as factory_kind).
    Raises FactoryError if `files` is empty or nothing was staged (so a no-op
    scaffold can't strand a dangling receipt)."""
    repo = root or PM_OS_DIR
    if not files:
        raise FactoryError("no files to commit")
    add = _git(repo, "add", "--", *files)
    if add.returncode != 0:
        raise FactoryError(f"git add failed: {add.stderr.strip()[:300]}")
    # `git diff --cached --quiet` returns 0 when NOTHING is staged.
    if _git(repo, "diff", "--cached", "--quiet").returncode == 0:
        raise FactoryError("scaffold produced no committable changes")
    commit = _git(repo, "commit", "-m", f"factory: {summary}")
    if commit.returncode != 0:
        raise FactoryError(f"git commit failed: {commit.stderr.strip()[:300]}")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    receipt_id, _ = task_lib.create_task(
        f"Built: {summary}", queue="human", domain="ops", creator="agent",
        description="The factory built this for you. One-tap Undo reverts it cleanly.",
        card_type="receipt")
    task_lib.update_task(receipt_id, changes={
        "revert_commit": sha,
        "receipt_summary": summary,
        "factory_kind": kind,
    })
    return receipt_id


def validate_worker(path, root=None):
    """Return a list of structural problems with a scaffolded worker .md ([] = ok)."""
    import task_dispatch
    problems = []
    try:
        fm, body = task_dispatch._parse_worker_frontmatter(path)
    except Exception as e:
        return [f"frontmatter did not parse: {e}"]
    if not fm:
        return ["frontmatter did not parse"]
    for field in _REQUIRED_WORKER_FIELDS:
        if field not in fm:
            problems.append(f"missing required field: {field}")
    if not (body or "").strip():
        problems.append("empty prompt body")
    return problems


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("commit-and-receipt")
    c.add_argument("--summary", required=True)
    c.add_argument("--kind", required=True)
    c.add_argument("files", nargs="+")
    v = sub.add_parser("validate-worker")
    v.add_argument("path")
    args = ap.parse_args()
    if args.cmd == "commit-and-receipt":
        print(commit_and_emit_receipt(args.summary, args.files, args.kind))
    elif args.cmd == "validate-worker":
        probs = validate_worker(args.path)
        if probs:
            print("\n".join(probs)); sys.exit(1)
        print("ok")
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_factory_lib.py -v`
Expected: PASS (5 tests). If `task_dispatch` import is heavy, the `validate_worker` test still works because it only calls `_parse_worker_frontmatter`.

**Step 5: Commit**

```bash
git add scripts/factory_lib.py tests/test_factory_lib.py
git commit -m "feat(factory): factory_lib — precise commit + receipt emission + worker validation

Stages only the named files (fixes git add -A wart), emits a receipt card with
revert_commit so the existing undo_receipt handler powers Undo. No backend change.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `meta-factory-core` skill (shared lifecycle + capture-to-profile)

**Files:**
- Create: `.claude/skills/meta-factory-core/SKILL.md`
- Test: `tests/test_factory_skills.py` (create; extended again in Task 4)

**Step 1: Write the failing test**

Create `tests/test_factory_skills.py`:

```python
"""Phase 9 PR1 — structural checks on the factory skills (mirrors test_skill_frontmatter)."""
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent


def _read(rel):
    return (REPO / rel).read_text()


def test_meta_factory_core_exists_and_frontmatter():
    body = _read(".claude/skills/meta-factory-core/SKILL.md")
    assert body.startswith("---\n")
    fm = body.split("---\n", 2)[1]
    assert "name: meta-factory-core" in fm
    assert "Use when" in fm
    # documents the shared mechanism + the capture-to-profile rule
    assert "factory_lib" in body
    assert "receipt" in body.lower()
    assert "conventions" in body
    assert "set_integration_conventions" in body
    # forward pointers / deferral noted
    assert "meta-create-skill" in body          # reuses the TDD spine by reference
    assert "Tier" in body                        # Tier-2 forward note for adapters
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_factory_skills.py -v`
Expected: FAIL — file not found.

**Step 3: Write the skill**

Create `.claude/skills/meta-factory-core/SKILL.md`:

```markdown
---
name: meta-factory-core
description: Use when scaffolding a new worker, card-type, or adapter (the meta-create-* factory skills) - establishes the shared scaffold→capture→gate→commit→receipt lifecycle and the capture-to-profile rule
---

# Factory Core

The shared mechanism behind `meta-create-worker`, `meta-create-card-type`, and
`meta-create-adapter`. Read this first; the sibling skill owns the artifact-specific
gate. The factory builds at **authoring time** — durable, reviewable, theme-aware by
construction — never at render time.

## The Core Principle

The factory scaffolds a **clean** artifact and captures every team/person specific
into the **profile**, never into the artifact. This is the same line
`tests/test_engine_no_jay.py` enforces: generated workers/skills/commands must read
identity and team facts from `profile/` (instruct-to-read-profile), so they stay
denylist-clean by construction.

This is Test-Driven scaffolding — it reuses `meta-create-skill`'s RED-GREEN-REFACTOR
spine: define the gate, scaffold to pass it, then commit only when green.

## The Lifecycle (every factory skill follows this)

1. **Capture.** Gather the spec conversationally. Structured specifics that already
   have a profile home (e.g. Jira board/project/assignee in
   `profile/integrations.yaml`) are read, not asked. Fuzzy team nuance with no
   structured field ("always set Sprint", "titles prefixed [Area]") is written to a
   free-form `conventions` slot in the profile via
   `profile_lib.set_integration_conventions(category, text, provider=…)` — **never
   written into the artifact.**
2. **Scaffold.** Produce the artifact from the sibling skill's embedded skeleton
   (profile-read boilerplate + token-only references baked in).
3. **Gate (GREEN).** Run the artifact's gate (the sibling skill names it). It MUST
   pass before committing — nothing non-conformant lands.
4. **Commit + receipt.** Call the shared helper:
   `python3 scripts/factory_lib.py commit-and-receipt --summary "<one-liner>" --kind <worker|card-type|adapter> <file> [<file> …]`
   It stages **only** those files (never `git add -A`), commits, captures the sha,
   and emits a `receipt` card with `revert_commit` + `receipt_summary`.
5. **Hand back.** Tell the operator in plain language: *"Built you an X → check the
   receipt card. Keep / Undo."* **Never mention git.** Undo is the existing
   `undo_receipt` git-revert handler; the board only shows Keep / Undo.

## Iron Laws

1. **NEVER write team/person specifics into the artifact** — capture to profile.
2. **NEVER commit before the gate is green.**
3. **Stage only the scaffolded files** — use `factory_lib`, never `git add -A`.
4. **Git is never user-facing** — speak in Keep / Undo, never commits/reverts.

## Tier-2 (adapters only)

Creating an artifact writes local files only → Tier-1, no confirm. Anything that
writes to the **outside world** (an adapter's first `publish`) is **Tier-2** and gets
exactly one plain-language confirm before its first external action — see
`meta-create-adapter`. Workers and card-types are Tier-1.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Baking the board id / team nuance into the worker | Capture it to `profile/` via `set_integration_conventions`; the artifact reads it |
| `git add -A` then commit | Use `factory_lib commit-and-receipt` with explicit files |
| Telling the operator "I committed / reverted" | Say "Keep / Undo on the card" |
| Committing before the gate passes | Gate first; commit only when green |

## Deferred (future work)

Personalizing an **arbitrary third-party skill someone drops in** (that the factory
did not author) to the operator's team/voice is a separate card-driven flow, not part
of the factory. Instruct-to-read-profile already makes dropped skills runtime
profile-aware.

## Related Skills

- **meta-create-skill**: the TDD spine these factories reuse (RED-GREEN-REFACTOR + CSO).
- **meta-create-worker** / **meta-create-card-type** / **meta-create-adapter**: the siblings.
```

**Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_factory_skills.py -v`
Expected: PASS.
Also run the guard: `python3 -m pytest tests/test_engine_no_jay.py -v` → PASS (the new skill is denylist-clean).

**Step 5: Commit**

```bash
git add .claude/skills/meta-factory-core/SKILL.md tests/test_factory_skills.py
git commit -m "feat(factory): meta-factory-core skill — shared lifecycle + capture-to-profile

Documents scaffold→capture→gate→commit→receipt, the capture-to-profile rule, the
Keep/Undo (git-invisible) hand-back, and the Tier-2 forward note for adapters.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `meta-create-worker` skill (scaffolds a worker .md)

**Files:**
- Create: `.claude/skills/meta-create-worker/SKILL.md`
- Modify: `tests/test_factory_skills.py` (add a meta-create-worker block)

**Step 1: Add the failing test**

Append to `tests/test_factory_skills.py`:

```python
def test_meta_create_worker_exists_and_frontmatter():
    body = _read(".claude/skills/meta-create-worker/SKILL.md")
    assert body.startswith("---\n")
    fm = body.split("---\n", 2)[1]
    assert "name: meta-create-worker" in fm
    assert "Use when" in fm
    # references the core + the gate + the helper + profile-read pattern
    assert "meta-factory-core" in body
    assert "factory_lib" in body
    assert "test_engine_no_jay" in body
    assert "profile/integrations.yaml" in body
    # embeds a worker skeleton with the dispatch placeholders
    assert "{task_id}" in body
    assert "{skills_catalog}" in body
    assert "tier:" in body


def test_meta_create_worker_skeleton_is_denylist_clean():
    """The embedded skeleton must carry no per-person/per-team literals."""
    import re
    body = _read(".claude/skills/meta-create-worker/SKILL.md")
    for pat in (r"\bjay\b", r"board 1096", r"/Users/", r"~/pm-os"):
        assert not re.search(pat, body, re.IGNORECASE), f"skeleton leaks /{pat}/"
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_factory_skills.py -v`
Expected: FAIL — meta-create-worker file not found.

**Step 3: Write the skill**

Create `.claude/skills/meta-create-worker/SKILL.md`:

````markdown
---
name: meta-create-worker
description: Use when the operator asks to build, add, or scaffold a new background worker / agent for a kind of task - generates a profile-driven scripts/workers/<name>.md, validates it, and emits a Keep/Undo receipt card
---

# Create Worker

Scaffold a new background worker (`scripts/workers/<name>.md`) that the dispatcher
matches and runs. **Read `meta-factory-core` first** — this skill is its worker
specialization. Reuses `meta-create-skill`'s RED-GREEN-REFACTOR spine.

## When to Use

- The operator wants a new kind of task handled autonomously ("build me a worker that
  files bugs", "add an agent that drafts release notes").
- **Not** for a new card type (use `meta-create-card-type`) or a new external
  integration (use `meta-create-adapter`).

## The Gate (must be green before commit)

1. `python3 scripts/factory_lib.py validate-worker scripts/workers/<name>.md` → `ok`
   (frontmatter parses + required fields present).
2. `python3 -m pytest tests/test_engine_no_jay.py -q` → passes (the new worker is
   denylist-clean — it reads team/identity specifics from `profile/`, never hardcodes).
3. The dispatcher loads it: `python3 -c "import sys; sys.path.insert(0,'scripts'); import task_dispatch; print(any(w['name']=='<name>' for w in task_dispatch.load_workers()))"` → `True`.

## Workflow

1. **Capture the spec.** Ask what tasks it handles, the title/description keywords
   that should route to it, which tier (`light`/`standard`/`deep`), tools, and skills.
   For team-specific nuance with no profile field (required fields, title format,
   labels), write it to the profile — do **not** put it in the worker:
   `python3 -c "import sys; sys.path.insert(0,'scripts'); import profile_lib; profile_lib.set_integration_conventions('project_management', '<nuance>', provider='jira')"`
   (use the relevant category/provider). Structured targets (board/project/assignee)
   are already in `profile/integrations.yaml` — the worker reads them at runtime.
2. **Scaffold** `scripts/workers/<name>.md` from the skeleton below. Fill the
   frontmatter; keep the body's "read specifics from profile" boilerplate.
3. **Gate** — run all three gate checks above. Fix until green.
4. **Commit + receipt** — `python3 scripts/factory_lib.py commit-and-receipt --summary "a <name> worker" --kind worker scripts/workers/<name>.md`
   (add any profile file you changed to the same command's file list).
5. **Hand back** — tell the operator: *"Built you a `<name>` worker → it's on the
   Workers tab and there's a receipt card. Keep / Undo."* Never mention git.

## Worker Skeleton (token-only, profile-driven, denylist-clean)

```yaml
---
name: <worker-name>
description: <one-line trigger — what tasks this worker handles>
priority: 10
tier: standard          # light | standard | deep — cheapest model that does the job well
match:
  task_type: []
  domains: []
  title_patterns:
    - "(?i)<keyword>"
  description_patterns: []
allowed_tools:
  - "Bash(*)"
  - "Read(*)"
  - "Write(*)"
skills: []
langfuse_prompt: "worker-<worker-name>"
timeout: 300
max_turns: 15
---

You are the PM-OS <role> agent working in this project. Read and follow CLAUDE.md.

## Your Focus

<what this worker specializes in>

## Team specifics

Read any team-specific configuration and conventions from `profile/` at runtime —
never hardcode them here. For external systems, read the target from
`profile/integrations.yaml`; read free-form team conventions from the relevant
`conventions` field. If a field is unset, proceed without it and flag it for the
operator's review. Sound like the operator by reading `profile/voice/*` when drafting.

## Available Skills

{skills_catalog}

## Your Assignment

Task {task_id}. Follow these steps:

0. Read CLAUDE.md in the project root.
1. Read the full task: `./scripts/task.sh show {task_id}`
2. Mark it started: `./scripts/task.sh agent:start {task_id}`
3. <do the work, reading profile/ for any team/identity specifics>
4. Finish one of:
   - Done: `./scripts/task.sh agent:complete {task_id} --output "<path>"`
   - Need a decision: `./scripts/task.sh agent:ask {task_id} "your question"` then STOP
   - Failed: `./scripts/task.sh agent:fail {task_id} --error "what happened"`

{rerun_block}Important rules:
- Read the task and any source meeting first.
- Read identity/team specifics from `profile/`, never hardcode them.
```

## Iron Laws

1. **The worker reads team/identity specifics from `profile/`** — never hardcoded.
2. **Gate green before commit** (validate-worker + test_engine_no_jay + dispatcher loads it).
3. **Stage only the worker file (+ any profile change)** via `factory_lib`.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Hardcoding the board/project/assignee in the worker | Read from `profile/integrations.yaml` at runtime |
| Hardcoding "always set Sprint" in the prompt | Capture it to `conventions` in profile |
| Committing before `test_engine_no_jay` passes | Run the gate first |
| Telling the operator about the commit | Speak in Keep / Undo |

## Related Skills

- **meta-factory-core**: the shared lifecycle + capture-to-profile rule (read first).
- **meta-create-skill**: the TDD spine.
````

**Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_factory_skills.py -v`
Expected: PASS.
Run the guard: `python3 -m pytest tests/test_engine_no_jay.py -v` → PASS.

**Step 5: Commit**

```bash
git add .claude/skills/meta-create-worker/SKILL.md tests/test_factory_skills.py
git commit -m "feat(factory): meta-create-worker skill — scaffold profile-driven workers

Embeds a denylist-clean, profile-reading worker skeleton; gates on
validate-worker + test_engine_no_jay + dispatcher load; commits via factory_lib
and hands back a Keep/Undo receipt.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Register the factory skills in the `core` pack

Per master design §8, the factory is always-on core. Add both skills to the `core` pack so the worker dispatch catalog and Profile UI list them.

**Files:**
- Modify: `.claude/packs.yaml` (add to `core.skills`)
- Test: `tests/test_factory_skills.py` (add a pack-membership test)

**Step 1: Add the failing test**

Append to `tests/test_factory_skills.py`:

```python
def test_factory_skills_in_core_pack():
    import yaml
    packs = yaml.safe_load((REPO / ".claude/packs.yaml").read_text())
    core = packs["core"]["skills"]
    assert "meta-factory-core" in core
    assert "meta-create-worker" in core
```

**Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_factory_skills.py::test_factory_skills_in_core_pack -v`
Expected: FAIL — not in core.

**Step 3: Edit `.claude/packs.yaml`**

In the `core:` pack's `skills:` list, add after `meta-create-skill`:

```yaml
    - meta-factory-core
    - meta-create-worker
```

**Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_factory_skills.py -v` → PASS.
Run: `python3 -m pytest tests/test_packs_lib.py -v` → still PASS (no regressions).

**Step 5: Commit**

```bash
git add .claude/packs.yaml tests/test_factory_skills.py
git commit -m "feat(factory): register meta-factory-core + meta-create-worker in core pack

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Full-suite green + documentation-sync gate

**Step 1: Run the whole suite + the two standing gates**

```bash
python3 -m pytest -q
python3 scripts/card_schema.py
python3 -m pytest tests/test_engine_no_jay.py -q
```
Expected: all green; pytest count = prior 222 + the new tests.

**Step 2: Documentation-sync (meta-create-skill iron law #6)**

Invoke the `quality-documentation-sync` skill to check the six system docs are
consistent with the two new skills. Update only what it flags (likely a no-op given
auto-discovery; if it flags the `.claude/CLAUDE.md` naming/category table or a skill
index, update that). Do NOT hand-edit the auto-generated available-skills list.

**Step 3: Commit any doc updates**

```bash
git add -A
git commit -m "docs(factory): documentation-sync for the factory skills

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(Skip if nothing changed.)

---

## Task 7: Live integration verification (the real proof)

Per the PR #12 lesson — verify the INTERACTION, not just unit tests. Drive the factory end-to-end against the dev board, then Undo to leave the tree clean.

**Step 1: Restart the dev board (backend changed — factory_lib is imported by task_server's process at start)**

```bash
PID=$(lsof -ti :8743 -sTCP:LISTEN) && [ -n "$PID" ] && lsof -a -p $PID -d cwd -Fn   # confirm cwd is THIS repo, NOT /Users/jayjenkins/pm-os
kill $PID 2>/dev/null; sleep 1
nohup python3 scripts/task_server.py > logs/devserver.log 2>&1 &
sleep 2; curl -s localhost:8743/api/workers | python3 -c "import sys,json; print(len(json.load(sys.stdin)['workers']),'workers')"
```

**Step 2: Drive `meta-create-worker` to scaffold a throwaway worker**

In this session, invoke the `meta-create-worker` skill with a trivial spec (e.g. a
`release-notes-drafter` worker, tier `standard`, title pattern `(?i)release notes`).
Let it run the full lifecycle: scaffold → gate → `factory_lib commit-and-receipt`.

**Step 3: Verify the worker surfaces + the receipt card exists**

```bash
curl -s localhost:8743/api/workers | python3 -c "import sys,json; ws=json.load(sys.stdin)['workers']; print([w['name'] for w in ws if 'release' in w['name']])"
./scripts/task.sh list --queue human | grep -i "Built:"
```
Expected: the new worker appears in `/api/workers` (so it renders in the Workers &
Prompts tab); a `Built:` receipt task exists.

**Step 4: Chrome-verify the receipt card renders (optional but recommended)**

Screenshot the human queue via Chrome headless against `:8743` and confirm the
receipt card shows the summary + Keep / Undo buttons.

**Step 5: Undo to clean up + confirm the revert path**

Hit the receipt's Undo (POST `/api/tasks/<receipt_id>/undo`) or call
`task_server.undo_receipt`. Confirm the throwaway worker file is gone and the tree is
clean:
```bash
git log --oneline -3
git status --porcelain   # expect clean (factory commit + its revert)
ls scripts/workers/ | grep -i release || echo "worker reverted — clean"
```

**Step 6: Final state**

`python3 -m pytest -q` green; tree clean (the verification commits are a factory
commit + its revert, which is fine to keep as evidence, or squash if you prefer a
tidy history). Do NOT leave the throwaway worker committed.

---

## Done criteria for PR1

- [ ] `conventions` slot + `set_integration_conventions` (Task 1) — tests green.
- [ ] `factory_lib.py` precise-commit + receipt + validate_worker (Task 2) — tests green, Undo round-trips.
- [ ] `meta-factory-core` + `meta-create-worker` skills (Tasks 3–4) — structural tests green, denylist-clean.
- [ ] Both skills in `core` pack (Task 5).
- [ ] Full suite + `card_schema.py` + `test_engine_no_jay.py` green; documentation-sync done (Task 6).
- [ ] Live proof: scaffolded worker appears in Workers tab + receipt card + Undo reverts (Task 7).
- [ ] Open PR `feat/phase-9-factory-pr1-worker` → main with the superpowers two-stage review (spec-compliance, then code-quality).
