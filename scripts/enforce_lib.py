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
JUDGE_GOOD_THRESHOLD = 7  # the quality bar (mirrors graduation_assess.JUDGE_GOOD_THRESHOLD)


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


def tier_of(key, path=None):
    return ladder_lib.tier_of(key, path=path)


def _read_fm(task_id):
    import task_lib
    return task_lib.read_task(task_id).get("frontmatter") or {}


def _trigger_revision(task_id, judge_why, revision_count):
    """Bounce a below-bar task back to the agent, carrying the judge's feedback.

    Safe against racing the dispatcher: the judge fires strictly AFTER the run that
    produced the artifact has completed, so resetting the task's agent state here
    cannot clobber a live dispatch. Bumps revision_count (the loop bound) before
    re-dispatching via the shared respawn path."""
    import task_lib
    import task_dispatch
    task_lib.update_task(task_id, changes={
        "status": "open", "agent_status": "", "agent_error": "",
        "agent_output": "", "agent_started": "", "agent_completed": "",
        "revision_count": revision_count + 1,
    }, comment=f"[revision] Judge sent this back for revision: {judge_why}", actor="judge")
    if task_dispatch.respawn(task_id, rerun=True) is None:
        # Re-dispatch failed; the task is left status=open so the dispatcher cron
        # re-picks it. Make the failure visible rather than silently stranding it.
        task_lib.update_task(task_id, changes={},
            comment="[revision] Re-dispatch failed; left open for the next dispatch cycle.",
            actor="judge")


def _autoship(task_id, action_type):
    import shipper
    return shipper.autoship(task_id, action_type)


def apply_post_judge(task_id, verdict, *, root=None, ladder_path=None):
    """Run the tier × score policy after the judge scores. Returns one of:
    'park' | 'revise' | 'shipped' | 'needs_confirm' | 'error'. Never raises into
    the judge — any failure returns 'park' (the safe default: human reviews)."""
    try:
        fm = _read_fm(task_id)
        score = verdict.get("score")
        if score is None:
            return "park"
        key = grouping_key(fm)
        tier = tier_of(key, path=ladder_path)
        if tier == "shadow":
            return "park"
        if score < revision_bar(path=ladder_path):
            if int(fm.get("revision_count") or 0) < max_revisions(path=ladder_path):
                _trigger_revision(task_id, verdict.get("why", ""), int(fm.get("revision_count") or 0))
                return "revise"
            return "park"
        action = action_type_of(fm)
        if tier == "autonomous" and action in ACTION_TYPES and autonomy_enabled(root):
            return _autoship(task_id, action)
        return "park"
    except Exception:
        return "park"
