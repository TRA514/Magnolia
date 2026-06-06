#!/usr/bin/env python3
"""ladder_lib — per-task-type trust-tier store for the graduation ladder.

Tiers climb shadow -> gated -> autonomous. State lives in datasets/evals/ladder.json
(runtime, gitignored). Tiers are ADVISORY in Phase 4: displayed and managed, but they
do not yet change dispatch/review behavior (that enforcement is deferred to the Review
surface work). Thresholds are config in the same file with moderate defaults here.

All public functions take an optional `path=` (defaults to the repo ladder.json) so
tests can point at a temp file without monkeypatching.
"""
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PM_OS_DIR = os.path.dirname(SCRIPT_DIR)
LADDER_FILE = os.path.join(PM_OS_DIR, "datasets", "evals", "ladder.json")

TIERS = ["shadow", "gated", "autonomous"]

DEFAULT_THRESHOLDS = {
    "window_days": 60,
    "shadow_to_gated": {"min_judged": 6, "min_approval": 0.75, "min_agreement": 0.70},
    "gated_to_autonomous": {"min_judged": 12, "min_approval": 0.85, "min_agreement": 0.80},
    "demote_consecutive": 2,
}


def _path(path):
    return path or LADDER_FILE


def _load(path):
    p = _path(path)
    if not os.path.exists(p):
        return {"tiers": {}, "thresholds": {}, "demote_signals": {}}
    try:
        with open(p) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {"tiers": {}, "thresholds": {}, "demote_signals": {}}
    d.setdefault("tiers", {})
    d.setdefault("thresholds", {})
    d.setdefault("demote_signals", {})
    return d


def _save(d, path):
    p = _path(path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, p)


def tier_of(task_type, path=None):
    return _load(path)["tiers"].get(task_type, "shadow")


def set_tier(task_type, tier, path=None):
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}")
    d = _load(path)
    d["tiers"][task_type] = tier
    _save(d, path)
    return tier


def advance(task_type, path=None):
    cur = tier_of(task_type, path=path)
    i = min(TIERS.index(cur) + 1, len(TIERS) - 1)
    return set_tier(task_type, TIERS[i], path=path)


def demote(task_type, path=None):
    cur = tier_of(task_type, path=path)
    i = max(TIERS.index(cur) - 1, 0)
    return set_tier(task_type, TIERS[i], path=path)


def all_tiers(path=None):
    return dict(_load(path)["tiers"])


def thresholds(path=None):
    """Deep-merge file overrides onto DEFAULT_THRESHOLDS."""
    over = _load(path)["thresholds"]
    out = json.loads(json.dumps(DEFAULT_THRESHOLDS))  # deep copy
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def note_demotion_signal(task_type, below, path=None):
    """Track consecutive 'below entry bar' assessments. Returns the running count.

    below=True increments; below=False resets to 0. Used by graduation_assess to
    auto-demote only after `demote_consecutive` consecutive bad windows.
    """
    d = _load(path)
    n = d["demote_signals"].get(task_type, 0)
    n = n + 1 if below else 0
    d["demote_signals"][task_type] = n
    _save(d, path)
    return n
