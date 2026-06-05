# Phase 1: Engine / Profile Split — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a per-person `profile/` layer and a single `profile_lib` loader that the engine reads all identity and integration facts from, then migrate the hardcoded "Jay/Vantaca" references onto it — so a new profile fully re-skins the system and no person-specific value lives in the engine.

**Architecture:** A gitignored `profile/` directory holds per-person YAML (`profile.yaml`, `integrations.yaml`, `config.yaml`), voice cards, and `capabilities.json`. A tracked `profile.example/` mirrors the schema and is the seed for onboarding (Phase 2). `scripts/profile_lib.py` is the single source of truth: it resolves the active profile dir (`profile/` if present, else `profile.example/`), loads the YAML with the repo's existing `ruamel.yaml`, and exposes small typed accessors with safe fallbacks. Consumers (`judge.py`, `jira_publish.py`, the qmd MCP config, identity-bearing skills) read from `profile_lib` instead of hardcoding.

**Tech Stack:** Python 3, `ruamel.yaml` (already a dependency, used by `task_lib.py`), `pytest` (introduced in Task 1). Plain shell/JSON/Markdown for config edits.

**Scope guardrail:** Phase 1 builds the loader and migrates the *identity-critical, pattern-setting* consumers. It does **not** rebuild the UI config room (Phases 5–6), wire onboarding (Phase 2), or touch LangFuse/model-tiering (Phases 5/7). The final task sweeps for remaining references and flags (not necessarily migrates) the long tail.

---

## Task 1: Test scaffolding (pytest + profile fixture)

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

**Step 1: Add the dev dependency**

Create `requirements-dev.txt`:
```
pytest>=8.0
ruamel.yaml>=0.18
```

**Step 2: Install it**

Run: `python3 -m pip install -r requirements-dev.txt`
Expected: pytest + ruamel.yaml installed (ruamel likely already present).

**Step 3: Create the shared profile fixture**

Create `tests/__init__.py` (empty file).

Create `tests/conftest.py`:
```python
import os
import sys
import textwrap
import pytest

# Make scripts/ importable as top-level modules (matches how scripts import each other)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


@pytest.fixture
def profile_root(tmp_path):
    """A temp PM-OS root containing a fully populated profile/ dir."""
    prof = tmp_path / "profile"
    (prof / "voice").mkdir(parents=True)
    (prof / "profile.yaml").write_text(textwrap.dedent("""\
        display_name: "Test User"
        email: "test@example.com"
        company: "Acme"
        persona: "pm"
        timezone: "America/New_York"
    """))
    (prof / "integrations.yaml").write_text(textwrap.dedent("""\
        project_management:
          provider: "jira"
          jira:
            cloud_id: "acme.atlassian.net"
            project_key: "ACM"
            component_id: "999"
            auto_label: "team_lane"
            default_assignee: "acct-123"
        transcript:
          provider: "granola"
        calendar:
          provider: "m365"
    """))
    (prof / "config.yaml").write_text(textwrap.dedent("""\
        models:
          judge: "claude-opus-4-8"
          parser: "claude-haiku-4-5"
          cost_posture: "balanced"
        active_skill_packs: ["core", "pm"]
    """))
    (prof / "voice" / "teams.md").write_text("# Teams voice\nTight, lowercase ok.\n")
    (prof / "voice" / "email.md").write_text("# Email voice\nWarm, polished.\n")
    return str(tmp_path)
```

**Step 4: Add a smoke test that proves the harness runs**

Create `tests/test_smoke.py`:
```python
def test_pytest_runs():
    assert True
```

**Step 5: Run it**

Run: `python3 -m pytest tests/test_smoke.py -v`
Expected: 1 passed.

**Step 6: Commit**

```bash
git add requirements-dev.txt tests/
git commit -m "test: add pytest harness + shared profile fixture"
```

---

## Task 2: Profile schema templates + gitignore

**Files:**
- Create: `profile.example/profile.yaml`
- Create: `profile.example/integrations.yaml`
- Create: `profile.example/config.yaml`
- Create: `profile.example/voice/teams.md`
- Create: `profile.example/voice/email.md`
- Create: `profile.example/capabilities.json`
- Create: `profile.example/README.md`
- Modify: `.gitignore`
- Delete: `datasets/reference/jay-voice.md` (voice now lives in profile)

**Step 1: Create the example profile (the schema + seed)**

`profile.example/profile.yaml`:
```yaml
# WHO THE OPERATOR IS — the only place identity lives.
# Copied to profile/ by onboarding; edit there, never here.
display_name: "Your Name"
email: "you@company.com"
company: "Your Company"
persona: "pm"            # pm | exec
timezone: "America/New_York"
```

`profile.example/integrations.yaml`:
```yaml
# Which external tools this operator uses. Onboarding fills these in.
project_management:
  provider: "none"       # jira | asana | linear | none
  jira:
    cloud_id: ""         # e.g. yourorg.atlassian.net
    project_key: ""      # e.g. ABC
    component_id: ""
    auto_label: ""
    default_assignee: "" # Jira accountId
transcript:
  provider: "none"       # otter | granola | none
calendar:
  provider: "none"       # m365 | google | none
```

`profile.example/config.yaml`:
```yaml
# Engine behavior knobs.
models:
  judge: "claude-opus-4-8"
  parser: "claude-haiku-4-5"
  cost_posture: "balanced"   # low | balanced | high
active_skill_packs: ["core"]
```

`profile.example/voice/teams.md`:
```markdown
# Teams voice (placeholder)

Onboarding studies your message history and rewrites this. For now:
direct, low-caps okay, tight, minimal greeting, no em dashes.
```

`profile.example/voice/email.md`:
```markdown
# Email voice (placeholder)

Onboarding studies your message history and rewrites this. For now:
warm, polished, leads with the point, concrete next step.
```

`profile.example/capabilities.json`:
```json
{}
```

`profile.example/README.md`:
```markdown
# profile.example

The schema + seed for a per-person profile. Onboarding copies this to
`profile/` (gitignored). Edit your real values in `profile/`, never here.
The engine reads identity and integration facts only via `scripts/profile_lib.py`.
```

**Step 2: Update `.gitignore`** — ignore the live profile, keep the example; drop the jay-voice whitelist.

Find this block (around lines 85-87):
```
datasets/reference/*
!datasets/reference/.gitkeep
!datasets/reference/jay-voice.md
```
Replace with:
```
datasets/reference/*
!datasets/reference/.gitkeep

# Per-person profile is gitignored; the .example template is tracked.
/profile/
```

**Step 3: Delete the personal voice file**

Run: `git rm datasets/reference/jay-voice.md`
Expected: file staged for deletion.

**Step 4: Verify the example is tracked and profile/ would be ignored**

Run: `git check-ignore profile/profile.yaml profile.example/profile.yaml || true`
Expected: only `profile/profile.yaml` printed (ignored); the `.example` path prints nothing.

**Step 5: Commit**

```bash
git add profile.example .gitignore
git commit -m "feat(profile): add profile.example schema + gitignore live profile"
```

---

## Task 3: profile_lib — dir resolution + raw loaders

**Files:**
- Create: `scripts/profile_lib.py`
- Test: `tests/test_profile_lib.py`

**Step 1: Write the failing test**

Create `tests/test_profile_lib.py`:
```python
import os
import profile_lib


def test_profile_dir_prefers_live_profile(profile_root):
    assert profile_lib.profile_dir(root=profile_root).endswith("/profile")


def test_profile_dir_falls_back_to_example(tmp_path):
    # No profile/ dir, but a profile.example/ exists
    (tmp_path / "profile.example").mkdir()
    assert profile_lib.profile_dir(root=str(tmp_path)).endswith("/profile.example")


def test_raw_loaders_return_dicts(profile_root):
    assert profile_lib.profile(root=profile_root)["display_name"] == "Test User"
    assert profile_lib.integrations(root=profile_root)["project_management"]["provider"] == "jira"
    assert profile_lib.config(root=profile_root)["models"]["judge"] == "claude-opus-4-8"


def test_missing_file_returns_empty_dict(tmp_path):
    (tmp_path / "profile").mkdir()
    assert profile_lib.profile(root=str(tmp_path)) == {}
```

**Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_profile_lib.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'profile_lib'`.

**Step 3: Implement the loader**

Create `scripts/profile_lib.py`:
```python
"""Single source of truth for per-person profile facts.

The engine reads identity and integration values ONLY through this module.
Resolves the active profile dir as profile/ if present, else profile.example/.
"""
import os
from ruamel.yaml import YAML

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PM_OS_DIR = os.path.dirname(SCRIPT_DIR)

_yaml = YAML(typ="safe")


def profile_dir(root=None):
    root = root or PM_OS_DIR
    live = os.path.join(root, "profile")
    if os.path.isdir(live):
        return live
    return os.path.join(root, "profile.example")


def _load_yaml(name, root=None):
    path = os.path.join(profile_dir(root), name)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return _yaml.load(f) or {}


def profile(root=None):
    return _load_yaml("profile.yaml", root)


def integrations(root=None):
    return _load_yaml("integrations.yaml", root)


def config(root=None):
    return _load_yaml("config.yaml", root)
```

**Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_profile_lib.py -v`
Expected: 4 passed.

**Step 5: Commit**

```bash
git add scripts/profile_lib.py tests/test_profile_lib.py
git commit -m "feat(profile): profile_lib dir resolution + raw yaml loaders"
```

---

## Task 4: profile_lib — identity accessors

**Files:**
- Modify: `scripts/profile_lib.py`
- Test: `tests/test_profile_lib.py`

**Step 1: Add failing tests**

Append to `tests/test_profile_lib.py`:
```python
def test_identity_accessors(profile_root):
    assert profile_lib.display_name(root=profile_root) == "Test User"
    assert profile_lib.email(root=profile_root) == "test@example.com"
    assert profile_lib.company(root=profile_root) == "Acme"
    assert profile_lib.persona(root=profile_root) == "pm"


def test_identity_fallbacks_when_absent(tmp_path):
    (tmp_path / "profile").mkdir()
    assert profile_lib.display_name(root=str(tmp_path)) == "Operator"
    assert profile_lib.persona(root=str(tmp_path)) == "pm"
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_profile_lib.py -k identity -v`
Expected: FAIL with `AttributeError: module 'profile_lib' has no attribute 'display_name'`.

**Step 3: Implement**

Append to `scripts/profile_lib.py`:
```python
def display_name(root=None):
    return profile(root).get("display_name") or "Operator"


def email(root=None):
    return profile(root).get("email", "")


def company(root=None):
    return profile(root).get("company", "")


def persona(root=None):
    return profile(root).get("persona") or "pm"
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_profile_lib.py -k identity -v`
Expected: 2 passed.

**Step 5: Commit**

```bash
git add scripts/profile_lib.py tests/test_profile_lib.py
git commit -m "feat(profile): identity accessors with safe fallbacks"
```

---

## Task 5: profile_lib — integration + jira_config accessors

**Files:**
- Modify: `scripts/profile_lib.py`
- Test: `tests/test_profile_lib.py`

**Step 1: Add failing tests**

Append to `tests/test_profile_lib.py`:
```python
def test_integration_and_provider(profile_root):
    assert profile_lib.provider("transcript", root=profile_root) == "granola"
    assert profile_lib.provider("calendar", root=profile_root) == "m365"
    assert profile_lib.provider("nonexistent", root=profile_root) == "none"


def test_jira_config_when_jira(profile_root):
    jc = profile_lib.jira_config(root=profile_root)
    assert jc["cloud_id"] == "acme.atlassian.net"
    assert jc["project_key"] == "ACM"
    assert jc["default_assignee"] == "acct-123"


def test_jira_config_empty_when_not_jira(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text(
        "project_management:\n  provider: asana\n"
    )
    assert profile_lib.jira_config(root=str(tmp_path)) == {}
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_profile_lib.py -k "integration or jira" -v`
Expected: FAIL (`provider` / `jira_config` undefined).

**Step 3: Implement**

Append to `scripts/profile_lib.py`:
```python
def integration(name, root=None):
    return integrations(root).get(name) or {}


def provider(name, root=None):
    return integration(name, root).get("provider") or "none"


def jira_config(root=None):
    pm = integration("project_management", root)
    if pm.get("provider") != "jira":
        return {}
    return pm.get("jira") or {}
```

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_profile_lib.py -k "integration or jira" -v`
Expected: 3 passed.

**Step 5: Commit**

```bash
git add scripts/profile_lib.py tests/test_profile_lib.py
git commit -m "feat(profile): integration provider + jira_config accessors"
```

---

## Task 6: profile_lib — model + voice accessors

**Files:**
- Modify: `scripts/profile_lib.py`
- Test: `tests/test_profile_lib.py`

**Step 1: Add failing tests**

Append to `tests/test_profile_lib.py`:
```python
def test_model_accessor(profile_root):
    assert profile_lib.model("judge", root=profile_root) == "claude-opus-4-8"
    assert profile_lib.model("missing", default="x", root=profile_root) == "x"


def test_voice_text_concatenates_channels(profile_root):
    txt = profile_lib.voice_text(root=profile_root)
    assert "Teams voice" in txt
    assert "Email voice" in txt


def test_voice_text_single_channel(profile_root):
    assert "Teams voice" in profile_lib.voice_text("teams", root=profile_root)
    assert "Email voice" not in profile_lib.voice_text("teams", root=profile_root)
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_profile_lib.py -k "model or voice" -v`
Expected: FAIL (`model` / `voice_text` undefined).

**Step 3: Implement**

Append to `scripts/profile_lib.py`:
```python
def model(role, default=None, root=None):
    return (config(root).get("models") or {}).get(role, default)


def voice_path(channel, root=None):
    return os.path.join(profile_dir(root), "voice", f"{channel}.md")


def voice_text(channel=None, root=None):
    """Return voice guidance. channel='teams'|'email', or None for both concatenated."""
    channels = [channel] if channel else ["teams", "email"]
    chunks = []
    for ch in channels:
        path = voice_path(ch, root)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                chunks.append(f.read().strip())
    return "\n\n".join(chunks)
```

Note: voice files always live at `<profile_dir>/voice/<channel>.md` (resolved via `profile_dir()`, honoring the `profile.example/` fallback) — there is no config override.

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_profile_lib.py -k "model or voice" -v`
Expected: 3 passed.

**Step 5: Run the full profile_lib suite**

Run: `python3 -m pytest tests/test_profile_lib.py -v`
Expected: all passed (~15 tests).

**Step 6: Commit**

```bash
git add scripts/profile_lib.py tests/test_profile_lib.py
git commit -m "feat(profile): model + voice accessors"
```

---

## Task 7: Migrate jira_publish.py onto profile_lib

**Files:**
- Modify: `scripts/jira_publish.py:21-25`
- Test: `tests/test_jira_config.py`

**Step 1: Write the failing test**

Create `tests/test_jira_config.py`:
```python
import importlib


def test_jira_constants_come_from_profile(profile_root, monkeypatch):
    import profile_lib
    # Force jira_publish to resolve config against the temp profile.
    monkeypatch.setattr(profile_lib, "PM_OS_DIR", profile_root)
    import jira_publish
    importlib.reload(jira_publish)
    assert jira_publish.JIRA_CLOUD_ID == "acme.atlassian.net"
    assert jira_publish.JIRA_PROJECT_KEY == "ACM"
    assert jira_publish.JIRA_COMPONENT_ID == "999"
    assert jira_publish.JIRA_DEFAULT_ASSIGNEE == "acct-123"
```

**Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_jira_config.py -v`
Expected: FAIL — constants still equal the old hardcoded Vantaca values.

**Step 3: Replace the hardcoded block**

In `scripts/jira_publish.py`, replace lines 21-25:
```python
JIRA_CLOUD_ID = "vantaca.atlassian.net"
JIRA_PROJECT_KEY = "VNT"
JIRA_COMPONENT_ID = "10011"  # Vantaca HXP
JIRA_AUTO_LABEL = "home_aidlc"  # AI DLC swim lane indicator. ...
JIRA_DEFAULT_ASSIGNEE = "712020:aeec48b7-3829-433b-9125-c8c2a4c84e6f"  # Jay Jenkins ...
```
with:
```python
import profile_lib

_jira = profile_lib.jira_config()
JIRA_CLOUD_ID = _jira.get("cloud_id", "")
JIRA_PROJECT_KEY = _jira.get("project_key", "")
JIRA_COMPONENT_ID = _jira.get("component_id", "")
JIRA_AUTO_LABEL = _jira.get("auto_label", "")
JIRA_DEFAULT_ASSIGNEE = _jira.get("default_assignee", "")
```
(Ensure `import profile_lib` sits with the other imports at the top if the file's import ordering requires it; the assignment block stays where the constants were.)

**Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_jira_config.py -v`
Expected: 1 passed.

**Step 5: Sanity-check the module still imports cleanly**

Run: `cd scripts && python3 -c "import jira_publish; print('ok')" && cd ..`
Expected: `ok` (constants now empty against profile.example, which is correct pre-onboarding).

**Step 6: Commit**

```bash
git add scripts/jira_publish.py tests/test_jira_config.py
git commit -m "refactor(jira): read Jira config from profile_lib, not hardcoded Vantaca"
```

---

## Task 8: Migrate judge.py voice + model onto profile_lib

**Files:**
- Modify: `scripts/judge.py:40` (VOICE_FILE) and `:45` (JUDGE_MODEL)
- Modify: `scripts/judge.py` `fetch_voice()` (around lines 234-256)

**Step 1: Repoint the voice source**

In `scripts/judge.py`, replace line 40:
```python
VOICE_FILE = os.path.join(PM_OS_DIR, "datasets", "reference", "jay-voice.md")
```
with:
```python
import profile_lib  # add with the other imports near the top
# voice now comes from profile/voice/* via profile_lib.voice_text()
```

**Step 2: Make the model configurable (default preserved)**

Replace line 45:
```python
JUDGE_MODEL = "claude-opus-4-8"
```
with:
```python
JUDGE_MODEL = profile_lib.model("judge", default="claude-opus-4-8")
```

**Step 3: Update `fetch_voice()` to use profile_lib**

Locate `fetch_voice()` (around lines 234-256). It currently tries a LangFuse prompt `judge-voice-jay`, then falls back to reading `VOICE_FILE`, then an inline default. Change the file-fallback to call `profile_lib.voice_text()` instead of reading `VOICE_FILE`, and rename the LangFuse prompt key from the Jay-specific `judge-voice-jay` to a generic `judge-voice`. The inline default stays. Keep the function's return contract `(text, source_label)` unchanged.

Concretely, the file-read fallback becomes:
```python
        voice = profile_lib.voice_text()
        if voice:
            return voice, "profile:voice"
```

**Step 4: Verify the module imports and the voice resolves from the example profile**

Run: `cd scripts && python3 -c "import judge; print(judge.JUDGE_MODEL); import profile_lib; print(bool(profile_lib.voice_text()))" && cd ..`
Expected: prints `claude-opus-4-8` and `True` (example voice placeholders exist).

**Step 5: Commit**

```bash
git add scripts/judge.py
git commit -m "refactor(judge): source voice + model from profile_lib"
```

---

## Task 9: De-hardcode the qmd MCP working directory

**Files:**
- Modify: `.mcp.json`

**Step 1: Inspect current value**

Run: `cat .mcp.json`
Expected: shows `"cwd": "/Users/jayjenkins/pm-os"`.

**Step 2: Remove the hardcoded cwd**

Edit `.mcp.json` to drop the `cwd` line so qmd runs in the project root by default (and remove the trailing comma on the line above):
```json
{
  "mcpServers": {
    "qmd": {
      "type": "stdio",
      "command": "/opt/homebrew/bin/qmd",
      "args": ["mcp"]
    }
  }
}
```
> Note: the `command` path (`/opt/homebrew/bin/qmd`) is macOS/Homebrew-specific and is handled by the Doctor layer in Phase 2 (cross-platform install). Leave it for now.

**Step 3: Validate JSON**

Run: `python3 -c "import json; json.load(open('.mcp.json')); print('valid')"`
Expected: `valid`.

**Step 4: Commit**

```bash
git add .mcp.json
git commit -m "refactor(mcp): drop hardcoded cwd so qmd runs in project root"
```

---

## Task 10: Operator identity — inject from profile + generalize the meeting-extraction skill

**Files:**
- Modify: `.claude/hooks/session-start.sh`
- Modify: `.claude/skills/task-extract-from-meeting/SKILL.md`

**Step 1: Inspect the session-start hook**

Run: `cat .claude/hooks/session-start.sh`
Expected: a script that reads `meta-using-skills/SKILL.md` and emits it as `additionalContext`. Note exactly how it prints/escapes the JSON `additionalContext` so the next step matches that format.

**Step 2: Add an operator-identity line to the injected context**

Modify `session-start.sh` so the `additionalContext` it emits is prefixed with a single line resolved from the profile. Add, before the context is assembled:
```bash
OPERATOR=$(python3 "$(dirname "$0")/../../scripts/profile_lib.py" --display-name 2>/dev/null || echo "the operator")
```
and include in the emitted context text:
```
You are the chief of staff for ${OPERATOR}. Where skills refer to "the operator", that means ${OPERATOR}.
```
This requires a tiny CLI shim in `profile_lib.py` — append:
```python
if __name__ == "__main__":
    import sys
    if "--display-name" in sys.argv:
        print(display_name())
```

**Step 3: Verify the shim**

Run: `python3 scripts/profile_lib.py --display-name`
Expected: prints `Your Name` (from profile.example) or the real name if a `profile/` exists.

**Step 4: Generalize the skill's hardcoded operator name**

In `.claude/skills/task-extract-from-meeting/SKILL.md`, replace person-specific phrasing ("Jay", "Jay owns it", "does Jay need to") with operator-neutral phrasing ("the operator", "the operator owns it", "does the operator need to"). Do this as a careful find-and-replace, reading each hit in context so meaning is preserved.

Run to find them: `grep -n "Jay" .claude/skills/task-extract-from-meeting/SKILL.md`
After editing, run again and expect `(no matches)`.

**Step 5: Commit**

```bash
git add .claude/hooks/session-start.sh scripts/profile_lib.py .claude/skills/task-extract-from-meeting/SKILL.md
git commit -m "feat(profile): inject operator identity at session start; de-Jay meeting-extraction skill"
```

---

## Task 11: Reference sweep — find and triage the long tail

**Files:**
- Create: `docs/plans/2026-06-05-phase-1-residual-references.md` (a triage list, not code)

**Step 1: Sweep the engine for remaining person/tenant-specific values**

Run each and capture results:
```bash
git grep -in "jayjenkins\|jay\.jenkins\|jay jenkins\|vantaca\|/Users/jay\|4818486697721856\|is_prod\|jay-voice" \
  -- 'scripts/**' '.claude/**' 'ui/**' '*.json' '*.yaml' '*.yml' '*.sh' ':!docs/plans/*'
```

**Step 2: Triage each hit into one of three buckets** and record in the residual-references doc:
- **Migrate now** — a clear identity/integration fact with a profile_lib home (do it, with a test if it's Python).
- **Defer to a later phase** — Pendo subId / Databricks `is_prod` / SharePoint paths belong to the integrations + Doctor work (Phases 2–3); LangFuse `Jay` belongs to Phase 5. Note the phase.
- **Content, not engine** — values inside `datasets/**` or design docs (`ROADMAP.md`, `UX_VISION.md`) handled by the §10 template-reset pass. Note it.

**Step 3: Migrate the "now" bucket** using the Task 7/8 pattern (profile_lib accessor + test where Python). Commit each migration separately with a `refactor(profile): ...` message.

**Step 4: Commit the triage doc**

```bash
git add docs/plans/2026-06-05-phase-1-residual-references.md
git commit -m "docs(profile): triage of residual person/tenant references after Phase 1"
```

---

## Task 12: Local QA — instantiate a real profile + smoke-run

**Files:**
- Create: `profile/` (copied from `profile.example/`, gitignored — not committed)

**Step 1: Create a working profile from the template**

Run: `cp -R profile.example profile`
Expected: `profile/` now exists (and is gitignored).

**Step 2: Verify the loader now prefers the live profile**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import profile_lib; print(profile_lib.profile_dir())"`
Expected: path ending in `/profile` (not `/profile.example`).

**Step 3: Run the full test suite**

Run: `python3 -m pytest -v`
Expected: all tests pass.

**Step 4: Confirm profile/ is not tracked**

Run: `git status --short profile/`
Expected: no output (ignored).

**Step 5: Final verification — no engine import is broken**

Run:
```bash
cd scripts && for m in profile_lib jira_publish judge task_lib; do python3 -c "import $m" && echo "$m ok"; done && cd ..
```
Expected: each prints `ok`.

> No commit — `profile/` is intentionally untracked. Phase 1 is complete: the engine reads identity/integration facts through `profile_lib`, a fresh clone runs against `profile.example/`, and a real profile fully re-skins it. Phase 2 (Doctor + onboarding) populates `profile/` for a real teammate.

---

## Definition of done

- [ ] `python3 -m pytest` passes from a clean checkout.
- [ ] `git grep` finds no `jayjenkins`/`vantaca.atlassian.net`/Jira-assignee-UUID in `scripts/`, `.mcp.json`, or migrated skills.
- [ ] Deleting `profile/` leaves the engine importable (falls back to `profile.example/`).
- [ ] `jira_publish` / `judge` constants reflect whatever profile is active, with zero hardcoded person/tenant values.
- [ ] Residual references are triaged in the Phase 1 residual-references doc with an owning phase each.
