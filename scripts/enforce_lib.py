#!/usr/bin/env python3
"""enforce_lib — the trust-ladder enforcement policy.

The judge (which already fires after agent:complete) calls apply_post_judge after
scoring; this module decides revise / park / ship by tier × score. Auto-ship runs
ONLY in a trusted backend process (the judge), never the headless LLM agent — and
always through the Tier-2-gated shipper, so the per-integration first-write confirm
still fires. Artifact types are hard-stopped from ever auto-shipping.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402
import ladder_lib    # noqa: E402

# Only ACTION types can auto-ship. Artifacts (PRDs, research, memos) never can —
# autonomy can't transfer the accountability of signing a document.
ACTION_TYPES = {"send-message", "publish-ticket"}

DEFAULT_MAX_REVISIONS = 1
JUDGE_GOOD_THRESHOLD = 7  # mirrors judge.JUDGE_GOOD_THRESHOLD; the quality bar.


def action_type_of(fm):
    """The canonical action type for a task, or None for an artifact.

    Keys off the stamped task_type; falls back to the JIRA_DRAFT body marker so an
    as-yet-unstamped Jira draft still reads as publish-ticket."""
    tt = fm.get("task_type")
    if tt in ACTION_TYPES:
        return tt
    if "<!-- JIRA_DRAFT -->" in (fm.get("body") or ""):
        return "publish-ticket"
    return None


def grouping_key(fm):
    """The ladder/judge grouping key — mirrors graduation_assess/build_quality."""
    return action_type_of(fm) or fm.get("task_type") or fm.get("domain") or "uncategorized"


def revision_bar(path=None):
    """The judge score at/above which work passes (ship/park) vs revises."""
    th = ladder_lib.thresholds(path=path)
    return int(th.get("revision_bar", JUDGE_GOOD_THRESHOLD))


def max_revisions(path=None):
    th = ladder_lib.thresholds(path=path)
    return int(th.get("max_revisions", DEFAULT_MAX_REVISIONS))


def autonomy_enabled(root=None):
    return profile_lib.autonomy_enforcement(root)
