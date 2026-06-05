# Phase 1 — Residual Person/Tenant Reference Triage

Task 11 of the Phase 1 Engine/Profile split. Sweep of the engine for remaining
`Jay`/`Vantaca`/tenant-specific values and a bucketed disposition for each.

## Sweep commands

```bash
git grep -in "jayjenkins\|jay\.jenkins\|jay jenkins\|vantaca\|/Users/jay\|4818486697721856\|is_prod\|jay-voice\|atlassian" \
  -- 'scripts/**' '.claude/**' 'ui/**' '*.json' '*.yaml' '*.yml' '*.sh' ':!docs/plans/*'
git grep -in "\bJay\b" -- 'scripts/**' '.claude/**'
```

## Buckets

- **Migrate now** — clear identity/tenant fact in an ENGINE file with a `profile_lib` home. Migrated in this task.
- **Defer** — belongs to a later phase (integrations / Doctor / LangFuse). Recorded with owning phase. NOT touched.
- **Content / template-reset** — values inside `datasets/**`, design-doc prose, or skill/command knowledge cards. Handled by §10 template-reset pass. NOT touched.

## Summary counts

| Bucket | Hits (grouped) | Files |
|---|---|---|
| Migrate now | 5 spots | `scripts/jira_publish.py`, `scripts/judge.py` |
| Defer | — | `.claude/skills/context-pendo-analytics`, `.claude/skills/context-databricks-analytics` + all skills with Pendo/Databricks query cards, `scripts/sync_config.yaml`, `scripts/setup_doc_sync.sh`, `scripts/doc_sync.py`, `scripts/_sync_manifest.json`, `qmd.yml`, `scripts/qmd-setup.sh`, `scripts/qmd-nightly-update.sh`, `scripts/run_task_server.sh`, `.claude/hooks/hooks.json`, `langfuse/*` |
| Content / template-reset | — | identity-bearing skill knowledge cards (jira-home, schedule-meeting, task-create, etc.), workers, UI Vantaca theme, command examples |

---

## Migrate now (done in this task)

| file:line | snippet | rationale |
|---|---|---|
| `scripts/jira_publish.py:170` | `# Assignee — Features default to Jay Jenkins unless the draft overrides.` | Person name in a code comment. Rewritten to "named-parent types default to the profile assignee". |
| `scripts/jira_publish.py:197` | `For example: JIRA_RESULT:VNT-1234\|https://vantaca.atlassian.net/browse/VNT-1234` | Hardcoded tenant/project in the prompt example. Rebuilt from `JIRA_PROJECT_KEY` + new `JIRA_BROWSE_BASE` (derived from `profile_lib.jira_config()` cloud_id). |
| `scripts/jira_publish.py:256,258` | `re.search(r"(https://vantaca\.atlassian\.net/browse/VNT-\d+)" ...)` fallback URL/key regex | Hardcoded tenant + `VNT` project key in the fallback result parser. Rebuilt from `re.escape(JIRA_PROJECT_KEY)` and `JIRA_BROWSE_BASE`. Behavior-preserving: with a Vantaca profile the pattern is byte-identical. Primary parse path (`JIRA_RESULT:` line) was already profile-driven via the prompt. |
| `scripts/jira_publish.py:339` | `... + " (default: Jay Jenkins)"` | Display string hardcoding the operator name. Now uses `profile_lib.display_name()`. |
| `scripts/judge.py:87-104,157,340` | Rubric prose: "prepared for Jay to send", "sound like Jay", "JAY'S VOICE GUIDE", `DEFAULT_VOICE = "Jay's voice: ..."` | Person-specific prose in the judge rubric/voice fallback. Generalized to "the operator" / "VOICE GUIDE" / "Operator voice: ...". Behavior-preserving. |

New engine constant added: `JIRA_BROWSE_BASE = f"https://{JIRA_CLOUD_ID}/browse"` (empty when no profile). Tests added in `tests/test_jira_config.py`: `test_browse_base_built_from_profile_cloud_id`, `test_fallback_url_parse_uses_profile_project_key`.

---

## Defer to a later phase (NOT touched)

### Phases 2-3 — Integrations + Doctor (Pendo / Databricks)

The Pendo subId, Vantaca app IDs, and Databricks `is_prod` catalog are integration
facts that belong to the integration-config + Doctor work, not Phase 1 identity.

| file:line | snippet | owning phase |
|---|---|---|
| `.claude/skills/context-pendo-analytics/SKILL.md:41,48-53,...` | `subId: 4818486697721856`; app IDs (`-323232`, `5961191088521216`, etc.); "Subscription: Vantaca" | Phase 2-3 |
| `.claude/skills/context-databricks-analytics/SKILL.md:22-23,28,48,...` | `Catalog: is_prod`; `is_prod.gongio`, `is_prod.zendesk`, `is_prod.azure_devops` table refs | Phase 2-3 |
| Pendo/Databricks query cards across skills | `subId: 4818486697721856` / `is_prod.*` query templates in `context-meeting-synthesis`, `context-priority-scoring`, `context-research-gathering`, `context-search`, `metric-north-star-alignment`, `metric-proxy-metric-selection`, `metric-root-cause-diagnosis`, `workflow-cs-prep`, `workflow-dashboard-design`, `workflow-goal-setting`, `workflow-metric-diagnosis`, `workflow-product-planning`, `workflow-product-strategy-creation`, `workflow-strategy-session`, `workflow-tradeoff-decision` | Phase 2-3 |
| `scripts/workers/product-analyst.md:44,133`, `scripts/workers/researcher.md:36,63` | `mcp__claude_ai_VantacaDatabricks__*` tool allowlist + description | Phase 2-3 |

### Phase 2 — Doctor (SharePoint / OneDrive / qmd local paths)

Local filesystem and tenant doc-sync paths handled by the cross-platform Doctor install.

| file:line | snippet | owning phase |
|---|---|---|
| `scripts/sync_config.yaml:9,18,19` | `onedrive_root: ~/Library/CloudStorage/OneDrive-Vantaca,LLC/`; `sharepoint_tenant_url: https://vantaca-my.sharepoint.com`; `sharepoint_doc_root: /personal/jay_jenkins_vantaca_com/Documents` | Phase 2 |
| `scripts/setup_doc_sync.sh` (+ `PLIST_NAME`) | doc-sync LaunchAgent setup | Phase 2 |
| `scripts/doc_sync.py:549` | example SharePoint URL `https://vantaca-my.sharepoint.com/...` (docstring) | Phase 2 |
| `scripts/_sync_manifest.json` (entire file) | ~190 `local_path`/`remote_path` pairs under `/Users/jayjenkins/pm-os/...` and `OneDrive-Vantaca,LLC` | Phase 2 (regenerated per-operator; also runtime state, not authored config) |
| `qmd.yml:18-82,91` | collection `path: ~/pm-os/datasets/...`; `com.jayjenkins.qmd-embed.plist` comment | Phase 2 |
| `scripts/qmd-setup.sh:9` | `PMDIR="$HOME/pm-os"` | Phase 2 |
| `scripts/qmd-nightly-update.sh:3` | `LOG="/Users/jayjenkins/pm-os/logs/qmd-update.log"` | Phase 2 |
| `scripts/run_task_server.sh:10,13` | `com.jayjenkins.task-server.plist`; `REPO="/Users/jayjenkins/pm-os"` | Phase 2 |
| `.claude/hooks/hooks.json:9` | `command: /Users/jayjenkins/pm-os/.claude/hooks/session-start.sh` (absolute hook path) | Phase 2 |

> Note: `.claude/mcp.json` hardcoded `cwd` and `.claude/hooks/session-start.sh` `SKILL_ROOT` were the Phase-1-scoped items (Tasks 9-10). The `hooks.json` absolute `command` path above is a sibling absolute path left for the Doctor pass.

### Phase 5 — LangFuse

| file:line | snippet | owning phase |
|---|---|---|
| `scripts/langfuse_setup.py:270,277,292` | `judge-voice-jay` prompt name; docstring "Register Jay's voice guide"; `config={"source": "datasets/reference/jay-voice.md"}` | Phase 5 (LangFuse prompt-name + source migration) |
| `langfuse/*` | any `Jay` references in the LangFuse stack | Phase 5 |

---

## Content / template-reset (NOT touched — §10 pass)

Identity-bearing skill knowledge cards, worker prose, command examples, and the
Vantaca UI theme. These are domain knowledge / presentation, re-skinned by the
template-reset pass rather than read through `profile_lib`.

| file:line | snippet | note |
|---|---|---|
| `.claude/commands/jira-create.md:4,9,29,42,56` | Vantaca Home AI DLC / VNT / `Vantaca HXP` / "Assignee defaults to Jay Jenkins" / `vantaca.atlassian.net` | Command knowledge card — §10 |
| `.claude/commands/strategy-memo.md:55,65` | `stakeholders: ["Jay Jenkins", "Nathan Snell"]` example | Example data in command — §10 |
| `.claude/skills/workflow-jira-home/SKILL.md` (many) | cloud id, project key, component id, board 1096, default assignee Jay Jenkins | Identity-bearing skill knowledge card — §10 |
| `.claude/skills/workflow-schedule-meeting/SKILL.md` (many) | "Jay picks", "Jay's calendar", Jay-only fallback, Calendar Structure Reference | Operator-specific skill prose — §10 |
| `.claude/skills/task-create/SKILL.md:33,40,42` | "Jay's physical presence", "When Jay needs to connect" | Skill prose — §10 |
| `.claude/skills/task-extract-from-meeting/SKILL.md:102,196,213` | `zach.lastname@vantaca.com`, `*-Vantaca-*.txt` example filenames | Example data — §10 (note: Task 10 already de-Jay'd this skill's body; remaining hits are example email/filenames) |
| `.claude/skills/context-source-normalization/SKILL.md:35` | `/Users/jay/llm/datasets/meetings/...` example path | Example path in skill — §10 |
| `.claude/skills/context-search/SKILL.md:255` | "Stan AI already building on Vantaca APIs" (meeting-quote example) | Example content — §10 |
| `.claude/skills/context-pendo-analytics/SKILL.md` (product names) | "HOAi, Vantaca IQ", white-label brands | Product-domain knowledge — §10 (separate from the deferred subId/appId integration facts above) |
| `.claude/skills/workflow-landing-page-creator/SKILL.md:19`, `workflow-velocity-estimate/SKILL.md:40,54,56` | "Vantaca needs a branded preview"; `~/dev/Vantaca/...` repo paths; `Vantaca HXP` team tag | Skill knowledge/example paths — §10 |
| `scripts/workers/message-writer.md` (many) | "Jay's voice", `datasets/reference/jay-voice.md` | Worker prose + voice-file path; voice now lives in profile (Task 8). Worker text re-skin — §10 |
| `scripts/workers/scheduler.md`, `eval-analyst.md`, `ticket-creator.md`, `_default.md`, `scripts/task_dispatch.py:629` | "Jay", "Vantaca Home AI DLC board", default assignee UUID | Worker/dispatch prose — §10 |
| `scripts/eval_meeting_classifier.py:137` | "(Vantaca — property management software)" classifier hint | Domain hint string — §10 |
| `ui/task-board/js/core.js:89` | `replace(/^\/Users\/jayjenkins\/pm-os\//, '')` path strip | UI path normalization — §10 (also Doctor-adjacent) |
| `ui/task-board/js/tasks.js:243` | "Project VNT · Vantaca HXP · Board AI DLC (1096)" hint | UI display string — §10 |
| `ui/task-board/index.html:19`, `ui/task-board/js/themes.js:52-56`, `ui/task-board/themes/vantaca.css` (whole file) | Vantaca brand theme (`vantacan` mood, colors, V favicon) | Intentional brand theme — §10 decides keep/rename |

### Intentionally kept (not findings)

- `"recruiting"` as a task-domain / qmd collection — kept by design, not person/tenant-specific.
- `.claude/settings.local.json` — untracked (`git ls-files` confirms it is not committed), so it never ships. No action.
- `profile.example/integrations.yaml:5` — `# e.g. yourorg.atlassian.net` is the placeholder template comment, correct as-is.
