# Phase 2: Doctor + Onboarding — Design Baseline

**Date:** 2026-06-05
**Status:** Design approved (brainstorm complete) — ready to write the implementation plan
**Companions:**
- `2026-06-05-pm-os-portability-design.md` (overall architecture; this is build-sequence step 2)
- `2026-06-05-pm-os-ui-spec.md` (§4 onboarding presentation + Engine/Profile room are Phase-2-adjacent)
- `2026-06-05-phase-1-engine-profile-split.md` (the `profile/` layer + `profile_lib` this builds on)
- `2026-06-05-phase-1-residual-references.md` (several deferred items are absorbed here)

---

## Goal

Make a freshly-cloned Magnolia install itself. A non-technical teammate opens Claude Code in
the folder, types **"onboard me,"** and is walked — by a warm concierge persona — through
identity, integrations, a self-healing tool/auth check, a server spin-up that ends with their
board appearing in the browser, voice discovery, and pack selection. The human does only the
irreducible minimum (answer a question, click "Authorize," paste a token); everything
automatable is automated, and every missing capability degrades gracefully instead of blocking.

This is build-sequence **step 2** from the portability design. Phase 1 built the `profile/`
layer and `profile_lib`; Phase 2 **populates** `profile/` and writes `profile/capabilities.json`.

## Non-negotiable principles (inherited)

- **Chief of staff, not a wizard.** Onboarding lowers anxiety and builds delight; it teaches by
  doing. Calm > snappy. Plain language — no jargon, no git, no model IDs surfaced unasked.
- **Simplicity is the architecture.** Simple Python + markdown skills. Headless Claude does the
  adaptive work; deterministic Python does the cron-safe, testable work.
- **Local-first, cross-platform.** macOS is run-validated on the dev machine; Windows branches
  are written and unit-tested against a mocked OS seam but are **design-validated, not
  run-validated** (no Windows box available).
- **Graceful degradation everywhere.** A missing capability disables only its own features.

---

## 1. Architecture decisions (locked in brainstorm)

1. **Doctor = deterministic Python probe + Claude-driven remediation.**
   `scripts/doctor.py detect` is a **pure, side-effect-free** function that writes
   `profile/capabilities.json`. It is cron-safe and runs headless. **Remediation** (installing
   tools, walking through auth) is **Claude-in-session**, encoded as the `workflow-doctor` skill.
   Clean seam: *detection is data, remediation is conversation.*

2. **MCP detection is two-tier.** Most integration MCPs (Jira, M365, Pendo, Databricks, Asana,
   Linear) are **claude.ai-managed remote connectors** a local script cannot probe or refresh.
   So: `doctor.py` truly probes **local stdio MCPs** (qmd) and writes their status; for **remote
   connectors** it seeds only `expected` (from `integrations.yaml`), and **Claude stamps
   `status`/`last_seen` in-session**. The standing re-auth loop is **failure-triggered** (a
   recorded tool-call failure flips status to `needs_reauth` and emits a card), modeled on the
   existing Otter reauth — never script-polled.

3. **Existing-install = adopt content into a clean engine** (non-destructive). The freshly-cloned
   Magnolia stays the canonical engine. Onboarding **copies** the prior install's per-person
   layers in (`datasets/`, legacy voice → `profile/voice/`, integration values →
   `integrations.yaml`); custom skills not in the engine are copied into `.claude/skills/`
   (auto-discovery handles them); **diverged** engine skills keep the engine's version and the
   diff is surfaced as a card to reconcile — never silently merged. The old directory is read,
   never written.

4. **Magnolia owns the transcript feed.** The single most important guarantee: **one feed,
   writing to Magnolia's `datasets/meetings/`.** Onboarding stands up Magnolia's own sync,
   then scans for **competing downloaders** (stray LaunchAgents / Scheduled Tasks / an old
   install's `otter_sync.py`). If found, it explains plainly and offers **one-tap disable of the
   old one** (user confirms before anything external is touched). If it can't safely identify or
   disable it, it falls back to a **loud, explicit warning** naming exactly what to turn off.

5. **Port the Otter pipeline into the engine** as the meeting-download module, profile-driven.
   Granola + the formal pluggable `transcript` adapter interface are **Phase 3** — but onboarding
   **presents Granola as a live option now** (it ships before real teammates onboard).

---

## 2. Component map

All Python lives in `scripts/`. Only markdown instruction packs live under `.claude/skills/`.

```
scripts/
  doctor.py            detect() → profile/capabilities.json; CLI: detect | check <cap> | report
  platform_lib.py      OS seam: brew↔winget, launchd↔Task Scheduler, open-url, paths
  server_lib.py        is_running() · start() · url() · open()  (port from config)
  persist_lib.py       install() · remove() · is_installed()  (LaunchAgent | Scheduled Task)
  transcript_sync.py   ported Otter pipeline (auth/sync/classify/rename), profile-driven
  feed_guard.py        detect competing downloaders; guided disable
.claude/skills/
  meta-onboard/SKILL.md     the "onboard me" conversational driver + Magnolia host persona
  workflow-doctor/SKILL.md  the remediation playbook (calls doctor.py; runs brew/winget via Bash)
profile.example/
  capabilities.json    schema seed (currently {})
datasets/cron/
  jobs.json            + a default Monday-9am doctor self-heal job
```

The ported Otter module is multi-file in production (`otter_sync.py`, `otter_auth.py`,
`otter_classify.py`, `otter_rename.py`, `otter_reauth_check.sh`, `requirements.txt`, `.env`,
`session.json`, `downloaded.json`, the `otterai` pip package). The port consolidates/relocates
these under the engine with **creds + target dir read from `profile/`** (the gitignored profile is
the credential home). `otter_classify.py`/`otter_rename.py` are what guarantee files land with
the correct YAML frontmatter and naming — i.e. *in the right place* — so they are load-bearing for
the feed-ownership guarantee. `otter_reauth_check.sh`'s logic becomes the template for the standing
re-auth loop.

## 3. The `capabilities.json` contract

The single contract every other piece reads. One entry per capability, kind-tagged so
graceful-degradation logic is uniform across the engine and the UI.

```json
{
  "schema_version": 1,
  "generated_at": "2026-06-05T12:00:00Z",
  "platform": "darwin",
  "capabilities": {
    "python_deps":  {"kind": "local",   "status": "ok",          "detail": "ruamel.yaml, otterai"},
    "qmd":          {"kind": "local",   "status": "missing",     "remedy": "brew install qmd"},
    "pandoc":       {"kind": "local",   "status": "ok"},
    "claude_cli":   {"kind": "local",   "status": "ok"},
    "msgraph_cli":  {"kind": "local",   "status": "missing",     "required": false,
                     "detail": "recommended for doc-sync + bulk Teams/OneDrive"},
    "transcript":   {"kind": "feed",    "status": "ok",          "provider": "otter",
                     "target": "datasets/meetings/"},
    "server":       {"kind": "service", "status": "running",     "port": 8742, "persistent": true},
    "jira":         {"kind": "remote",  "expected": true,  "status": "ok",          "last_seen": "2026-06-05"},
    "m365":         {"kind": "remote",  "expected": true,  "status": "needs_reauth", "reason": "tool call failed 2026-06-04"}
  }
}
```

- **`status` vocabulary:** `ok | missing | degraded | needs_reauth | running | down | not_expected`.
- **Who writes what:** `doctor.py` writes `local` / `feed` / `service` entries (it can truly probe
  them). For `remote`, `doctor.py` seeds `expected` from `integrations.yaml`; **Claude stamps
  `status`/`last_seen` in-session**; **failure events** flip to `needs_reauth`.
- **`required: false`** marks recommended-not-required capabilities (e.g. `msgraph_cli`) so
  onboarding never blocks on them.
- **`schema_version`** lets the Doctor migrate the file forward as later phases add capabilities.

## 4. The Doctor (`doctor.py`) — detection

Pure detection, zero side effects; safe on a cron and from a fresh checkout.

| Capability | Probe (via `platform_lib` where OS-specific) | `status` logic |
|---|---|---|
| `python_deps` | `importlib.util.find_spec` for `ruamel.yaml`, `otterai`, … | `ok`, else `degraded` + missing names |
| `qmd` | `shutil.which("qmd")` then `qmd status` exit code | `ok` / `missing` |
| `pandoc` | `shutil.which("pandoc")` | `ok` / `missing` |
| `claude_cli` | `shutil.which("claude")` | `ok` / `missing` |
| `msgraph_cli` | `shutil.which("mgc")` | `ok` / `missing` (`required: false`) |
| `transcript` | provider from `integrations.yaml`; creds file present + last-run freshness from dedup ledger | `ok` / `needs_reauth` / `not_expected` |
| `server` | TCP connect to configured port + `GET /api/tasks` → 200; `persistent` = agent/task installed | `running` / `down` |
| `jira`/`m365`/`pendo`/… | seed `expected` from `integrations.yaml` only | Claude / failure events own `status` |

CLI surface: `doctor.py detect` (writes the file) · `doctor.py check <cap>` (exit 0/1, for scripts) ·
`doctor.py report` (human-readable summary for the terminal and the Engine tab).

**Auto-remediation** (the `workflow-doctor` skill, Claude-in-session): because Claude is already in
the terminal, there is **no "spawn a Terminal window" machinery** — Claude runs the install command
(`brew install qmd` / the `winget` equivalent) via Bash and shows output. The only irreducible-manual
steps are OAuth ("click Authorize") and pasting a token. The playbook: read `capabilities.json` → for
each non-`ok` local cap, run its install → for each `remote` cap, walk the user to the claude.ai
connector → re-run `doctor.py detect` → confirm. `msgraph_cli` install route is pinned during
implementation (Windows `winget`; macOS exact route is a verify-step — `mgc` is not a clean single
brew formula).

**Standing self-heal loop:** a default cron (**Monday 9:00am**) in `datasets/cron/jobs.json` runs
`doctor.py detect`. If anything degrades (e.g. Otter `needs_reauth`), it writes a **recommendation
task** — *"Otter needs re-auth — want me to walk you through it?"* — which, when actioned, re-enters
`workflow-doctor`. No silent auto-fix; the human accepts on a card.

## 5. Cross-platform seam (`platform_lib.py`)

Everything OS-specific funnels through here so the rest of the engine stays platform-blind:

```
platform_lib.os_kind()                   # "darwin" | "windows" | "linux"
platform_lib.package_install_cmd(name)   # ["brew","install",name] | ["winget","install",...]
platform_lib.launch_agents_dir()         # ~/Library/LaunchAgents | None (Task Scheduler has no dir)
platform_lib.open_url(url)               # `open` | `start` | `xdg-open`
```

This is also the **honest Windows boundary**: macOS paths are run-tested; Windows branches are written
and unit-tested against a mocked `os_kind()` but flagged in code + plan as design-validated only.

## 6. Server lifecycle + reboot persistence

**`server_lib.py`** — four port-aware primitives:

- `is_running()` — TCP connect to the configured port + `GET /api/tasks` → 200. The one-tap
  "is it on?" check (also on the Engine tab).
- `start()` — launch `task_server.py` detached, poll `is_running()` until it serves or times out
  (never hand over a dead URL).
- `url()` → `http://localhost:<port>`; `open()` via `platform_lib.open_url`.
- **Port becomes configurable:** `task_server.py`'s hardcoded `PORT = 8742` reads
  `config.yaml` (`server.port`, default 8742). Critical for **collision-safety** — a teammate
  adopting an existing install must not clash with another PM-OS on 8742; onboarding picks the next
  free port and records it.

**`persist_lib.py`** — same `install()` / `remove()` / `is_installed()` API on both platforms:

- **macOS (run-tested):** per-user **LaunchAgent** plist (`com.pm-os.task-server.plist`) with
  `RunAtLoad` + `KeepAlive`, generalized from the existing `run_task_server.sh` pattern — repo path
  resolved at install (no hardcoded `/Users/jayjenkins`), env injected, port from config.
- **Windows (design-validated only): Task Scheduler at logon.** Chosen over a service wrapper
  (NSSM-style) because it needs **no admin/UAC**, **no third-party binary**, runs in the **correct
  user context** (can read the user's files/creds), and simply re-triggers next logon on failure. A
  service runs as SYSTEM (wrong context) and needs elevation. `persist_lib` emits a
  `Register-ScheduledTask` PowerShell invocation with an `AtLogon` trigger.

## 7. Conversational onboarding (`meta-onboard`)

**Entry:** clone → open Claude Code → type **"onboard me."** The skill is **resumable**: on entry it
reads `profile/` + `capabilities.json` and picks up where it left off.

**Each step is a task** (`domain: onboarding`) in the existing task system, created up front as a
visible checklist and marked `in_progress`→`done` as the conversation advances. No new queue. This is
what makes onboarding **double as the tutorial**.

**Chicken-and-egg, handled deliberately:** the board doesn't exist until the server spins up at
step 5. Steps 0–4 happen in the **terminal conversation**; their tasks are written to disk as they
go, so when the board first appears at step 5, the journey-so-far is already there as completed
cards — the first thing the user sees is *"here's everything I just set up for you."* (UI spec §4
renders this later; Phase 2 produces the task data.)

| Step | What happens | Writes |
|---|---|---|
| 0 · Bootstrap | `cp -R profile.example profile` so `profile_lib` resolves to the live profile | `profile/` |
| 1 · Identity | name, email, company, persona, timezone | `profile.yaml` |
| 2 · Existing-install | detect prior install → adopt `datasets/` + voice + custom skills (non-destructive); **transcript-feed reconciliation** | `datasets/`, `profile/voice/` |
| 3 · Integrations | "Otter or Granola? Jira/Asana/Linear/none? Teams/Outlook?" — **M365 Teams+Outlook on by default**; **Granola presented as live** | `integrations.yaml` |
| 4 · Doctor pass | `doctor.py detect` → `workflow-doctor` remediation until green-as-possible | `capabilities.json` |
| 5 · Spin-up | `server_lib.start` → verify → `persist_lib.install` → open `localhost:<port>` — **the board appears** | LaunchAgent/Task |
| 6 · Voice discovery | study message history (M365) + adopted/feed transcripts → draft voice cards → "here's how you sound, change anything?" | `voice/teams.md`, `voice/email.md` |
| 7 · Pack selection | activate `core` + persona pack | `config.yaml` |

**Degradation is first-class:** if step 4 leaves a capability not-`ok`, onboarding **continues** —
that integration's features show disabled-with-a-reason rather than blocking. A teammate with only
M365 still finishes with a working board. Step 6 depends on M365 auth; if absent it falls back to the
`profile.example` voice placeholders and leaves a recommendation card to regenerate later.

### 7a. Host persona & voice — "Magnolia"

The onboarding host is a **character**, specified in `meta-onboard/SKILL.md` (with 3–4 example lines so
the voice is reproducible, not vibes-only):

> **Magnolia** — your concierge. Warm, sunny, genuinely thrilled to get you set up. A host walking a
> guest in, not software running a wizard. Southern-summer ease: unhurried, delighted, encouraging.
> She says up front what the two of you are about to do and roughly how long it takes. She **teaches as
> she goes** — each step gets a plain-language *what this is and why it matters*, so you learn the
> product by being set up in it. She **builds anticipation toward the moment the board spawns** — the
> payoff she's walking you toward: stepping out into the sunshine.

Tasteful **Sugar Magnolia** motifs as flavor, never cosplay — sunshine, blossom, the willow, *"come
along with me."* Signature beat: when `server_lib.start()` succeeds at step 5 and the board appears,
that's the **"come on out singing, I'll walk you in the sunshine"** moment — she welcomes the user onto
their live board. **Guardrails:** clarity first; motifs at most a light touch per stretch; plain
language throughout (no jargon, no git, no model IDs) — consistent with the UI tone spec.

## 8. De-personalization absorbed here

The residual-references doc assigned these path/persistence items to Phase 2 (the Pendo/Databricks
**integration facts** stay Phase 3 and are NOT pulled forward):

- `session-start.sh` `SKILL_ROOT` + `hooks.json` `command` hardcode `/Users/jayjenkins/pm-os/...` —
  currently pointing the **team** repo's hook at the **production** install (a latent bug). → resolve
  to the repo root dynamically.
- `qmd.yml` collection paths + `qmd-setup.sh` `PMDIR` + `qmd-nightly-update.sh` log path → derive from
  repo root / profile; folded into the Doctor's qmd setup.
- `run_task_server.sh` `REPO=` + plist label → generalized by `persist_lib` (resolved at install).
- `sync_config.yaml` SharePoint/OneDrive/tenant paths → move to `integrations.yaml` + auto-detect
  (the `setup_doc_sync.sh` OneDrive auto-detect logic generalizes into the Doctor).

## 9. Testing strategy

Reuses the Phase 1 `pytest` harness + `profile_root` fixture (`tests/conftest.py`).

- `doctor.py` probes with mocked `shutil.which`/`importlib`; `capabilities.json` round-trips;
  `schema_version` present.
- `platform_lib` tested **both branches** via mocked `os_kind()` — how Windows gets design-validation
  without a Windows box.
- `server_lib` against an ephemeral port (start → `is_running()` true → stop).
- `persist_lib` by asserting the **rendered** plist / Scheduled-Task content (not by loading agents in CI).
- `feed_guard` competing-downloader detection against fixture LaunchAgent dirs.
- End-to-end **macOS** smoke: real `cp -R profile.example profile` → `doctor.py detect` →
  `server_lib.start` → board serves → teardown. Run-validated on this Mac; **Windows explicitly
  marked design-only** in the Definition of Done.

## 10. Scope boundary

**In Phase 2:** Doctor (detect + Claude remediation), `capabilities.json`, cross-platform seam,
server lifecycle + reboot persistence, configurable port, the ported Otter feed + feed-guard,
conversational onboarding with the Magnolia persona, existing-install adoption, the Monday-9am
self-heal cron, `msgraph_cli` as a recommended capability, and the path/persistence de-personalization.

**Deferred:** Granola adapter + formal `transcript` adapter interface (Phase 3); Pendo/Databricks
integration-fact migration (Phase 3); declarative card registry + the new card kinds' rendering
(Phases 4–6, frontend commissioned later — Phase 2 only emits the task/recommendation **data**);
eval substrate off Docker + in-box crons (Phase 4); model tiering, skill-pack factory (Phases 7–8).

## 11. Open questions carried into planning

- `msgraph_cli` exact macOS install route (verify during implementation).
- Whether the ported Otter module keeps its own venv or installs into the repo's bare `python3`
  (lean: bare `python3` + `--break-system-packages`, matching the rest of the engine).
- Precise `feed_guard` heuristics for identifying a "competing" downloader vs. an unrelated agent
  (start from label/target-dir matching; conservative — warn rather than disable on ambiguity).
