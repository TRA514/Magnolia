"""Skill-pack definitions (engine-shared).

A pack is a named set of skill folders under .claude/skills/. This module reads
.claude/packs.yaml and answers two questions: what packs exist (pack_catalog,
for the Profile UI) and which skill folders an active-pack list resolves to
(active_skill_folders, for dispatch gating). Pure logic is separated from disk
reads so it unit-tests without a filesystem. Degrades to "no gating" when the
manifest is missing or malformed.
"""
import os
from ruamel.yaml import YAML

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PM_OS_DIR = os.path.dirname(SCRIPT_DIR)

_yaml = YAML(typ="safe")

ALWAYS_ON = "core"


def _packs_path(root=None):
    return os.path.join(root or PM_OS_DIR, ".claude", "packs.yaml")


def load_packs(root=None):
    """Parse .claude/packs.yaml -> {id: {label, description, skills:[...]}}.
    Returns {} when the file is missing or unparseable (degrade to no gating)."""
    path = _packs_path(root)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = _yaml.load(f) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for pid, spec in data.items():
        if not isinstance(spec, dict):
            continue
        out[pid] = {
            "label": spec.get("label") or pid.title(),
            "description": spec.get("description") or "",
            "skills": [s for s in (spec.get("skills") or []) if isinstance(s, str)],
        }
    return out


def pack_catalog(root=None):
    """[{id, label, description}] for the Profile room. Empty when no manifest."""
    return [{"id": pid, "label": spec["label"], "description": spec["description"]}
            for pid, spec in load_packs(root).items()]
