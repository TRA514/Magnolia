"""Magnolia Doctor — deterministic, side-effect-free capability DETECTION.

Writes profile/capabilities.json. Safe to run headless / on a cron. Remediation
is Claude-driven (see .claude/skills/workflow-doctor); this module never installs
anything or mutates external state — it only observes and records.
"""
import argparse
import importlib.util
import shutil
import socket
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import profile_lib  # noqa: E402


def probe_which(name, remedy=None):
    found = shutil.which(name) is not None
    cap = {"kind": "local", "status": "ok" if found else "missing"}
    if not found and remedy:
        cap["remedy"] = remedy
    return cap


def _dep_missing(module):
    try:
        return importlib.util.find_spec(module) is None
    except ModuleNotFoundError:
        # A dotted name whose PARENT package is absent makes find_spec raise
        # rather than return None. The Doctor runs on unhealthy environments by
        # design, so treat that as "missing", never a crash.
        return True


def probe_python_deps(modules):
    missing = [m for m in modules if _dep_missing(m)]
    cap = {"kind": "local"}
    if missing:
        cap["status"] = "degraded"
        cap["missing"] = missing
    else:
        cap["status"] = "ok"
        cap["detail"] = ", ".join(modules)
    return cap
