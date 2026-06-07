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


def _on_disk_skill_folders(root=None):
    skills_dir = os.path.join(root or PM_OS_DIR, ".claude", "skills")
    if not os.path.isdir(skills_dir):
        return set()
    return {name for name in os.listdir(skills_dir)
            if os.path.isfile(os.path.join(skills_dir, name, "SKILL.md"))
            or os.path.isfile(os.path.join(skills_dir, name, "skill.md"))}


def active_skill_folders(active_packs, packs=None, on_disk=None, root=None):
    """Resolve the set of skill folders gating keeps visible.

    core (ALWAYS_ON) is always included; union each active pack's skills; any
    on-disk folder in NO pack stays visible. With no manifest (packs == {}),
    returns every on-disk folder (no gating)."""
    if packs is None:
        packs = load_packs(root)
    if on_disk is None:
        on_disk = _on_disk_skill_folders(root)
    if not packs:
        return set(on_disk)
    listed = {s for spec in packs.values() for s in spec.get("skills", [])}
    keep = set(packs.get(ALWAYS_ON, {}).get("skills", []))
    for pid in active_packs:
        keep |= set(packs.get(pid, {}).get("skills", []))
    keep |= {f for f in on_disk if f not in listed}   # unlisted = always-available
    return keep & set(on_disk)                          # never surface a phantom
