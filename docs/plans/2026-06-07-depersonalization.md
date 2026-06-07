# Engine De-personalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generalize the engine's per-person identity/voice and per-team Jira specifics into `profile/`
(keeping Vantaca as shared infra), so a different Vantaca team/person can run Magnolia without editing
prompts — and fix the live `message-writer` → dead-`jay-voice.md` break.

**Architecture:** Instruct-to-read-profile — prompts/skills say "the operator" and "read X from
profile; if unset, do Y and flag it" (agents already read files at runtime); no `task_dispatch.py`
template-var changes. Shared *structure* (Vantaca Jira issue types + required fields) stays baked in.
Two risk-ordered PRs: PR1 = workers + onboarding + LangFuse voice; PR2 = skills + commands prose scrub.

**Tech Stack:** Python 3 (bare Homebrew, PEP-668 → `--break-system-packages`), `ruamel.yaml`, `pytest`;
markdown prompt/skill files. Design: `docs/plans/2026-06-07-depersonalization-design.md`.

**Conventions:** PR1 branch `feat/depersonalize-pr1-workers` (already created, design doc committed).
Git author set locally. Commit trailer (exact):
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Keep `python3 -m pytest`
(baseline **213**) and `python3 scripts/card_schema.py` green. Never touch `:8742` / `/Users/jayjenkins/pm-os`.

**Keep (do NOT remove):** `Vantaca`, `VantacaDatabricks`, Gong/Zendesk/Azure-DevOps, the Jira issue-type
structure (Features/Units/Bugs/Regression Defects), the `<!-- JIRA_DRAFT -->` format. `researcher.md`
and `product-analyst.md` carry only Vantaca refs → **leave them unchanged**.

---

# PR 1 — Functional layer (workers + onboarding + LangFuse voice)

## Task 1: Add per-team Jira fields to the profile schema

**Files:**
- Modify: `profile/integrations.yaml` (the `project_management.jira` block)
- Test: `tests/test_jira_config_fields.py` (create)

**Step 1: Write the failing test**

```python
import profile_lib

def test_jira_config_exposes_board_and_product_area():
    """The per-team Jira block must carry board_id + product_area so prompts can
    read the team's target from profile instead of hardcoding it."""
    cfg = profile_lib.jira_config()  # provider may be 'none'; we assert the keys exist in the template
    # jira_config() returns {} when provider != jira, so read the raw block instead:
    import ruamel.yaml, io, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(profile_lib.__file__)))
    with open(os.path.join(root, "profile", "integrations.yaml")) as f:
        data = ruamel.yaml.YAML(typ="safe").load(f)
    jira = data["project_management"]["jira"]
    assert "board_id" in jira
    assert "product_area" in jira
```

**Step 2: Run, confirm FAIL**

Run: `python3 -m pytest tests/test_jira_config_fields.py -v`
Expected: FAIL (`KeyError: 'board_id'`).

**Step 3: Add the fields**

In `profile/integrations.yaml`, under `project_management.jira`, add two keys (keep alignment/comments):

```yaml
    board_id: ""         # e.g. 1096 — the team's Jira board id
    product_area: ""     # e.g. Home AI DLC — the team's product-area / swim-lane label
```

**Step 4: Run, confirm PASS**

Run: `python3 -m pytest tests/test_jira_config_fields.py -v` → PASS.

**Step 5: Commit**

```bash
git add profile/integrations.yaml tests/test_jira_config_fields.py
git commit -m "feat(depersonalize): add board_id + product_area to profile jira block

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Migrate message-writer to profile voice + the operator

**Files:**
- Modify: `scripts/workers/message-writer.md`
- Test: `tests/test_message_writer_depersonalized.py` (create)

**Background:** Today this worker reads `datasets/reference/jay-voice.md` (DOES NOT EXIST) and hardcodes
"Jay" ~18×. The real voice lives at `profile/voice/teams.md` + `profile/voice/email.md`.

**Step 1: Write the failing test**

```python
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(ROOT, "scripts", "workers", "message-writer.md")

def test_message_writer_uses_profile_voice_not_jay():
    text = open(F, encoding="utf-8").read()
    assert "jay-voice" not in text.lower()
    assert "datasets/reference/jay-voice.md" not in text
    assert "profile/voice/teams.md" in text and "profile/voice/email.md" in text
    # no standalone "Jay" identity references
    import re
    assert not re.search(r"\bJay\b", text), "found a standalone 'Jay' reference"
```

**Step 2: Run, confirm FAIL.** `python3 -m pytest tests/test_message_writer_depersonalized.py -v`

**Step 3: Rewrite `scripts/workers/message-writer.md`** (read it first). Apply these rules to BOTH the
frontmatter `description:` and the body:
- `description:` → "Drafts Teams + email messages in **the operator's** voice for send-message tasks — produces a review-ready draft, never sends".
- Step 2 ("Read Jay's voice guide"): replace with reading **both** `profile/voice/teams.md` and
  `profile/voice/email.md`; describe Teams vs Email voice from those files; **if a voice file is empty
  or absent, draft in a clean neutral professional voice and note that the operator hasn't set their
  voice yet.** Keep the "no em dashes / no corporate filler" rules.
- Every "Jay" → "the operator" (e.g. "messages for the operator to send", "the operator's own voice",
  "sending is always the operator's manual step", "the draft must sound like the operator", "Thanks,
  {the operator's name}" → use a generic sign-off placeholder like "{operator sign-off}", "Channel:
  Teams or email (the operator's call)", "Status: DRAFT — for the operator's review", "Context for the
  operator").
- "Voice first. Match `jay-voice.md`" → "Match the operator's voice files precisely."
- Also generalize the stale personal path `working in ~/pm-os/` (line ~29) → "working in this project".

**Step 4: Run, confirm PASS.**

**Step 5: Commit**

```bash
git add scripts/workers/message-writer.md tests/test_message_writer_depersonalized.py
git commit -m "fix(depersonalize): message-writer reads profile voice, not dead jay-voice.md

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Lift ticket-creator's per-team Jira specifics into profile

**Files:**
- Modify: `scripts/workers/ticket-creator.md`
- Test: `tests/test_ticket_creator_depersonalized.py` (create)

**Background:** Hardcodes board `1096`, project `VNT`, assignee UUID
`712020:aeec48b7-3829-433b-9125-c8c2a4c84e6f`, and "Home AI DLC". Keep the Vantaca issue-type structure
and the `<!-- JIRA_DRAFT -->` format; lift the team-specific target into profile.

**Step 1: Write the failing test**

```python
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(ROOT, "scripts", "workers", "ticket-creator.md")

def test_ticket_creator_reads_jira_target_from_profile():
    text = open(F, encoding="utf-8").read()
    # per-team literals removed
    assert "712020:aeec48b7-3829-433b-9125-c8c2a4c84e6f" not in text
    assert "board 1096" not in text
    assert not re.search(r"\bJay\b", text)
    # now sourced from profile
    assert "profile/integrations.yaml" in text
    # Vantaca + issue-type structure preserved
    assert "Vantaca" in text
    assert "Regression Defect" in text and "Unit" in text
```

**Step 2: Run, confirm FAIL.**

**Step 3: Rewrite `scripts/workers/ticket-creator.md`** (read it first):
- `description:` and "Your Focus": "Jira issue drafting … on **the team's configured Jira board**
  (read `profile/integrations.yaml` → `project_management.jira`)." Drop "VNT, board 1096"; keep
  "Vantaca". Keep "Home AI DLC" only if rephrased as the *example* product area, otherwise generalize
  to "the team's product area".
- Add a step (after step 1) instructing: read the team's Jira target from `profile/integrations.yaml`
  `project_management.jira` (`project_key`, `board_id`, `default_assignee`, `component_id`,
  `product_area`). **If a field is unset, draft without it and flag it for the operator.**
- `JIRA_ASSIGNEE` rule: replace the hardcoded UUID default with "default to the `default_assignee` from
  `profile/integrations.yaml` if set; otherwise leave empty."
- Labels rule: replace `home_aidlc` hardcode with "the configured `product_area` swim-lane label from
  profile (if set)"; keep the "never invent topical labels" guidance.
- Example keys `VNT-12345` / `VNT-42920` → generic `<PROJECT>-12345` placeholders.
- "~/pm-os/" → "this project".
- KEEP: issue types, the exact `<!-- JIRA_DRAFT -->` markers/format, the Description-hygiene rules, the
  "NEVER call Jira MCP" rule. (The `home_aidlc` / `HXP` / `AI-DLC` match patterns in frontmatter are
  additive routing triggers — leave them; they don't break other teams.)

**Step 4: Run, confirm PASS.**

**Step 5: Commit**

```bash
git add scripts/workers/ticket-creator.md tests/test_ticket_creator_depersonalized.py
git commit -m "feat(depersonalize): ticket-creator reads team Jira target from profile

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: De-Jay the identity pronouns in the remaining workers

**Files:**
- Modify: `scripts/workers/_default.md`, `scripts/workers/eval-analyst.md`, `scripts/workers/scheduler.md`
- Test: `tests/test_workers_no_jay.py` (create — this is the consolidated PR1 grep-guard)

**Step 1: Write the failing test** (covers ALL workers; locks PR1's scrub)

```python
import os, re, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKERS = glob.glob(os.path.join(ROOT, "scripts", "workers", "*.md"))
DENY = [r"\bJay\b", r"jay-voice", r"712020:aeec48b7-3829-433b-9125-c8c2a4c84e6f", r"board 1096"]

def test_no_per_person_or_per_team_literals_in_workers():
    offenders = []
    for f in WORKERS:
        text = open(f, encoding="utf-8").read()
        for pat in DENY:
            if re.search(pat, text):
                offenders.append(f"{os.path.basename(f)}: /{pat}/")
    assert not offenders, "Per-person/per-team literals remain:\n" + "\n".join(offenders)

def test_vantaca_still_allowed():
    # guard against over-scrubbing: Vantaca is shared infra and must remain
    joined = "".join(open(f, encoding="utf-8").read() for f in WORKERS)
    assert "Vantaca" in joined
```

**Step 2: Run, confirm FAIL** (offenders in `_default`/`eval-analyst`/`scheduler`, plus any not yet
done if Tasks 2–3 were skipped). If Tasks 2–3 are already committed, the only remaining offenders are
the three pronoun files.

**Step 3: Edit the three files** — replace each "Jay" with "the operator" (preserving meaning):
- `_default.md:60` "what Jay needs" → "what the operator needs".
- `eval-analyst.md:53` "Jay reviews each card" → "the operator reviews each card".
- `scheduler.md:41,82` "Jay confirms…" → "the operator confirms…".
- Also generalize any `~/pm-os/` personal paths in these files → "this project".

**Step 4: Run, confirm PASS** (both tests).

**Step 5: Commit**

```bash
git add scripts/workers/_default.md scripts/workers/eval-analyst.md scripts/workers/scheduler.md tests/test_workers_no_jay.py
git commit -m "fix(depersonalize): worker pronouns Jay -> the operator; lock with grep-guard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Point the LangFuse voice prompt at profile voice

**Files:**
- Modify: `scripts/langfuse_setup.py` (`register_voice`, ~line 269)
- Test: `tests/test_langfuse_voice_source.py` (create)

**Background:** `register_voice` imports `VOICE_FILE` from `judge` and reads
`datasets/reference/jay-voice.md`. `judge.py` already sources voice via `profile_lib.voice_text()`.

**Step 1: Write the failing test**

```python
import inspect, scripts.langfuse_setup as ls  # if import path differs, use: import langfuse_setup as ls

def test_register_voice_uses_profile_not_dead_path():
    src = inspect.getsource(ls.register_voice)
    assert "datasets/reference/jay-voice.md" not in src
    assert "voice_text" in src or "profile/voice" in src
    assert "judge-voice-operator" in src
```

(If `import langfuse_setup` is how other tests import scripts modules — check `tests/conftest.py` — use
that form.)

**Step 2: Run, confirm FAIL.**

**Step 3: Rewrite `register_voice`** to:
- name = `"judge-voice-operator"`.
- text = `profile_lib.voice_text()` (the concatenated operator voice; `import profile_lib` at top of the
  function or module — match existing import style). Skip/register-skip gracefully if it returns empty.
- `config={"source": "profile/voice/teams.md + profile/voice/email.md"}`.
- Update the docstring; remove the `from judge import VOICE_FILE` dependency.

**Step 4: Run, confirm PASS.**

**Step 5: Commit**

```bash
git add scripts/langfuse_setup.py tests/test_langfuse_voice_source.py
git commit -m "fix(depersonalize): langfuse register_voice reads profile voice (judge-voice-operator)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Teach onboarding to collect the per-team Jira block

**Files:**
- Modify: `.claude/skills/meta-onboard/SKILL.md` (the Integrations step, ~line 53)
- Test: `tests/test_onboard_collects_jira.py` (create)

**Step 1: Write the failing test** (prose-presence guard)

```python
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = os.path.join(ROOT, ".claude", "skills", "meta-onboard", "SKILL.md")

def test_onboard_collects_per_team_jira_fields():
    text = open(F, encoding="utf-8").read().lower()
    # when jira is the PM provider, onboarding must capture the team target
    assert "project_key" in text
    assert "board_id" in text
    assert "default_assignee" in text
```

**Step 2: Run, confirm FAIL.**

**Step 3: Edit the Integrations step** so that, when the project-management provider is `jira`,
onboarding asks for and writes into `profile/integrations.yaml` `project_management.jira`:
`project_key`, `board_id`, `default_assignee`, `component_id`, `product_area`. Keep it conversational
and on-voice with the rest of meta-onboard; note these can be left blank and filled later.

**Step 4: Run, confirm PASS.**

**Step 5: Final PR1 gates**

Run: `python3 -m pytest -q && python3 scripts/card_schema.py`
Expected: all green (213 + the new PR1 tests).

**Step 6: Commit**

```bash
git add .claude/skills/meta-onboard/SKILL.md tests/test_onboard_collects_jira.py
git commit -m "feat(depersonalize): onboarding collects per-team Jira block into profile

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**PR1 done:** run finishing-a-development-branch → push + PR + merge to main. Factory work can begin in
parallel once this lands (worker exemplars are clean).

---

# PR 2 — Prose scrub (skills + commands)

> Do this on a FRESH branch off main AFTER PR1 merges: `git checkout main && git pull && git checkout -b feat/depersonalize-pr2-skills`.

## Task 7: De-personalize the skills + commands; extend the grep-guard

**Files (~12, read each first):**
- `.claude/skills/workflow-jira-home/SKILL.md` (heaviest — board/project/assignee → "read from
  `profile/integrations.yaml`"; KEEP the Vantaca issue-type structure + field requirements)
- `.claude/commands/jira-create.md`, `.claude/commands/strategy-memo.md`
- `.claude/skills/context-search/SKILL.md`, `.claude/skills/context-source-normalization/SKILL.md`,
  `.claude/skills/quality-meeting-schema-validation/SKILL.md`, `.claude/skills/task-create/SKILL.md`,
  `.claude/skills/task-extract-from-meeting/SKILL.md`,
  `.claude/skills/workflow-landing-page-creator/SKILL.md`,
  `.claude/skills/workflow-schedule-meeting/SKILL.md`,
  `.claude/skills/workflow-velocity-estimate/SKILL.md`,
  `.claude/skills/context-databricks-analytics/SKILL.md`
- Test: extend the grep-guard to `.claude/skills/` + `.claude/commands/`.

**Rules (same as PR1):** "Jay" → "the operator"; per-team Jira specifics (board/project/assignee/
product-area) → "read from `profile/integrations.yaml`"; the dead `jay-voice.md` path → `profile/voice/*`;
**keep Vantaca/VantacaDatabricks/Gong/Zendesk/ADO and all shared structure.** `task-extract-from-meeting`
also has a stale nested skill path `.claude/skills/task-management/task-extract-from-meeting/SKILL.md`
(layout is flat) — fix to the flat path while you're in there.

**Step 1: Write/extend the failing guard test** — generalize `tests/test_workers_no_jay.py` into a
parametrized sweep over `scripts/workers/*.md` + `.claude/skills/**/*.md` + `.claude/commands/*.md`
(create `tests/test_engine_no_jay.py`), with the same DENY list (`\bJay\b`, `jay-voice`, the assignee
UUID, `board 1096`) and the Vantaca-still-present allowlist guard. Run → FAIL (skills/commands still
carry the literals).

**Step 2: Scrub each file** per the rules above (read → rewrite → keep Vantaca).

**Step 3: Run, confirm PASS:** `python3 -m pytest -q && python3 scripts/card_schema.py` → green.

**Step 4: Commit + finish.** One commit (or per-file if you prefer), then finishing-a-development-branch
→ PR + merge.

---

## Done criteria (whole phase)

- `python3 -m pytest` green and grown (213 + PR1 tests + PR2 guard); `card_schema.py` green.
- No `\bJay\b` / `jay-voice` / assignee-UUID / `board 1096` anywhere in `scripts/workers/`,
  `.claude/skills/`, `.claude/commands/`; Vantaca preserved.
- `message-writer` reads `profile/voice/*`; `ticket-creator` + `workflow-jira-home` read the team Jira
  target from `profile/integrations.yaml`; onboarding collects it.
- Both PRs merged to main. (Phase 9 factory then clones clean exemplars.)
