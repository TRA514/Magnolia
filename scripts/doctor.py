"""Magnolia Doctor — deterministic, side-effect-free capability DETECTION.

Writes profile/capabilities.json. Safe to run headless / on a cron. Remediation
is Claude-driven (see .claude/skills/workflow-doctor); this module never installs
anything or mutates external state — it only observes and records.
"""
import argparse
import importlib.util
import os
import shutil
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_lib  # noqa: E402
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


# Local CLI tools the Doctor knows how to detect (and a remedy hint for each).
_LOCAL_TOOLS = {
    "qmd":        {"remedy": "brew install qmd"},
    "pandoc":     {"remedy": "brew install pandoc"},
    "claude_cli": {"bin": "claude", "remedy": "see claude.ai/code install"},
    "msgraph_cli":{"bin": "mgc", "required": False,
                   "detail": "recommended for doc-sync + bulk Teams/OneDrive"},
}
_PYTHON_DEPS = ["ruamel.yaml"]
# Remote connectors keyed by the integration category that implies them.
_REMOTE_FROM_INTEGRATION = {
    "project_management": lambda prov: prov,   # 'jira'/'asana'/'linear'
    "calendar": lambda prov: "m365" if prov == "m365" else prov,
}


def probe_server(port):
    cap = {"kind": "service", "port": port}
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        cap["status"] = "running" if s.connect_ex(("127.0.0.1", port)) == 0 else "down"
    return cap


def probe_transcript(root=None):
    tc = profile_lib.transcript_config(root)
    provider = tc["provider"]
    cap = {"kind": "feed", "provider": provider, "target": tc["target"]}
    if provider == "none":
        cap["status"] = "not_expected"
        return cap
    # otter: a saved Playwright session.json under the transcript state dir means authed
    session = os.path.join(profile_lib.transcript_state_dir(root), "session.json")
    cap["status"] = "ok" if os.path.isfile(session) else "needs_reauth"
    return cap


def _remote_seeds(root=None):
    seeds = {}
    for category, namer in _REMOTE_FROM_INTEGRATION.items():
        prov = profile_lib.provider(category, root)
        if prov and prov != "none":
            seeds[namer(prov)] = {"kind": "remote", "expected": True, "status": "unknown"}
    return seeds


def detect(root=None):
    caps = {}
    for name, spec in _LOCAL_TOOLS.items():
        binname = spec.get("bin", name)
        c = probe_which(binname, remedy=spec.get("remedy"))
        if "required" in spec:
            c["required"] = spec["required"]
        if "detail" in spec:
            c["detail"] = spec["detail"]
        caps[name] = c
    caps["python_deps"] = probe_python_deps(_PYTHON_DEPS)
    caps["server"] = probe_server(profile_lib.server_port(root))
    caps["transcript"] = probe_transcript(root)
    caps.update(_remote_seeds(root))
    doc = {
        "schema_version": profile_lib.CAPABILITIES_SCHEMA_VERSION,
        "platform": platform_lib.os_kind(),
        "capabilities": caps,
    }
    profile_lib.write_capabilities(doc, root)
    return doc
