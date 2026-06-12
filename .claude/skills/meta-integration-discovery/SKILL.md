---
name: meta-integration-discovery
description: Use when an extension touches an external system and the mechanism is unsettled (MCP vs CLI vs REST) — probes which mechanism can actually do the job, validates the capability read-only, confirms auth/scope reality, and writes a findings doc that feeds meta-create-adapter. Invoked by meta-scope-extension.
---

# Integration Discovery — probe the capability before anyone builds against it

You are the external-capability probe. `meta-scope-extension` hands you any piece of an
approved design that touches an external system and the mechanism is **not yet settled**:
is the right path a connected **MCP** server, a **CLI** (e.g. `mgc`), or a **REST** API?
Your job is to answer that with evidence, prove the capability actually exists, confirm
the auth/scope reality, and write a **findings doc** that lands the decision already
de-risked into `meta-create-adapter`'s "capture the spec" step.

You exist to prevent the most expensive mistake in this layer: an agent confidently
building an adapter against a capability that does not exist, or a mechanism that cannot
do the job. **Decide and prove. Do not build.** The adapter factory builds — you point
at it.

## When to Use

- `meta-scope-extension` flagged an external surface and routed the probe to you before
  the adapter row of the build contract is written.
- An ask names a new external integration whose mechanism is unsettled ("hook up our
  calendar", "read incoming invites") and nobody has proven which mechanism can do it.
- **Not** for an external system whose mechanism is already settled and proven — that's
  `meta-create-adapter` directly. **Not** for re-auth of an already-chosen mechanism —
  that's `workflow-doctor`.

## The four-step probe

### (a) Enumerate mechanisms

Inventory every way the capability could be reached, in this order, and write down what
is already wired:

- **MCP** — is there a connected MCP server for this system? List its tools and check
  whether one names the capability the design assumes (e.g. a calendar/invite read).
- **CLI** — is there an installed CLI for this system (e.g. `mgc`)? Probe with a
  `which`/`--help` and read its command surface for the needed verb.
- **REST** — does the system expose a REST API the engine could call directly? Note the
  endpoint that would carry the capability.
- **Already wired** — read `profile/integrations.yaml`. An existing family or provider
  may already cover this; a "new integration" is often a config selection, not new code.

Record which mechanisms exist and which name the capability at all. A mechanism that
cannot name the capability is out before you spend a probe on it.

### (b) Validate the capability exists — READ-ONLY probes only

For each surviving mechanism, prove the capability is real with a **read-only** probe.
**Never a write during discovery** — see the Iron Laws.

- MCP: make the cheapest read call that would exercise the capability (e.g. "can it read
  incoming invites? can it list the calendar?") and confirm a real response.
- CLI: confirm the command exists and a read subcommand returns data (e.g. `... --help`,
  then a list/get, never a create/send).
- REST: a read endpoint (GET) only — never a probe that mutates state.

If no surviving mechanism can read what the design needs, the finding is *"no mechanism
can do this job"* — stop and report that. That is a successful discovery, not a failure.

### (c) Confirm auth/scope reality

Establish what is authorized **now** vs. what needs consent:

- What is already authorized (the probe in step b returned data → that scope is live).
- What is missing — which scopes/permissions the write side will need that the read
  probe did not exercise. Name them explicitly.
- Where re-auth or first-time auth is needed, the remediation is `workflow-doctor` (it
  detects with `scripts/doctor.py` and walks the human through authorizing) — point at
  it; do not re-implement auth here.
- Name plainly that the **first external WRITE is Tier-2**: exactly one plain-language
  confirm fires before the adapter's first publish (the general publish gate handles it;
  the adapter does not build a per-adapter prompt). Discovery itself never writes, so
  discovery is Tier-1.

### (d) Write the findings doc

Produce a short findings doc that records the de-risked decision:

| Section | Contents |
|---|---|
| **Mechanism chosen + why** | MCP / CLI / REST, and why it beat the alternatives |
| **Capability evidence** | the read-only probe(s) run and what they returned |
| **Auth/scope needs** | authorized now; scopes the write path still needs; re-auth path via `workflow-doctor` |
| **Tier-2 note** | the first external write fires one plain-language confirm |
| **Gaps / open questions** | anything unproven, anything the operator must decide |

Read any identity/team specifics this doc needs (the operator's mailbox, the team's
calendar) from `profile/` via `profile_lib` — never write personal literals into the doc.

## Hand-off to `meta-create-adapter`

The findings doc fills the adapter factory's **"capture the spec"** step with the
mechanism decision already proven, so the factory scaffolds against a capability that is
known to exist instead of an assumed one:

- **Structured targets** (cloud id, calendar id, mailbox, project key) land in
  `profile/integrations.yaml` — the adapter reads them at runtime, never hardcoded.
- **Fuzzy team nuance** with no structured field goes to the profile `conventions` slot
  via `profile_lib.set_integration_conventions(category, text, provider=…)` — never into
  the adapter or the findings doc.
- The chosen mechanism + scope list tells the factory which contract methods are reachable
  and arms the Tier-2 confirm (`confirmed: false`) for the first real write.

## Iron Laws

1. **Read-only during discovery** — every probe is a read. NO external writes, ever,
   while discovering. A write belongs to the adapter, behind the Tier-2 confirm.
2. **Never assume a capability exists without a probe** — if it was not proven by a
   read-only call, it is a gap in the findings doc, not a fact.
3. **Structured targets and identity go to `profile/`, never the artifact** — read them
   via `profile_lib`; the findings doc and the adapter both read from the profile.
4. **The first real write is Tier-2** — name it in the findings; one plain-language
   confirm before the adapter's first publish (the general publish gate owns it).

## Worked example — calendar-invite triage

Ask, routed in from `meta-scope-extension`: *"Every time a meeting invite comes in,
recommend accept/decline."* This touches an external calendar; the mechanism is unsettled.

- **(a) Enumerate.** Two candidates name the capability: an M365 MCP (calendar/email read
  tools) and a CLI for the same tenant. Both could reach invites; `profile/integrations.yaml`
  shows no calendar provider selected yet, so this is a real new integration.
- **(b) Validate, read-only.** Through the M365 MCP, do a cheap read: list recent invites
  in the inbox and read the calendar for the proposed times. It returns both → the read
  capability is proven. (Had it not, the CLI would be probed next; if neither read invites,
  the finding is "no mechanism can do this.")
- **(c) Auth/scope.** Calendar + mail **read** scope is live (the probe returned data).
  Accept/decline is a calendar **write** — that scope is not exercised by the read probe;
  name it as a needed scope, and note the first accept/decline action is **Tier-2** (one
  confirm). Re-auth, if the read had failed, routes to `workflow-doctor`.
- **(d) Findings.** Mechanism: M365 MCP (chosen over the CLI for stable read tools);
  evidence: invite-list + calendar reads succeeded; auth: read live, write scope needed;
  Tier-2 on first accept/decline; gap: confirm the operator wants auto-recommend vs.
  auto-respond. This doc hands to `meta-create-adapter`, which scaffolds the calendar
  adapter against a capability now known to exist.

## Related Skills

- **meta-scope-extension** — the caller; routes external surfaces to you before deciding the adapter.
- **meta-create-adapter** — the callee; your findings doc fills its "capture the spec".
- **workflow-doctor** — auth remediation; where missing/expired auth gets fixed conversationally.
- **meta-factory-core** — the shared scaffold→capture→gate→commit→receipt lifecycle behind the factories.
