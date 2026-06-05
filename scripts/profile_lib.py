"""Single source of truth for per-person profile facts.

The engine reads identity and integration values ONLY through this module.
Resolves the active profile dir as profile/ if present, else profile.example/.
"""
import os
from ruamel.yaml import YAML

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PM_OS_DIR = os.path.dirname(SCRIPT_DIR)

_yaml = YAML(typ="safe")


def profile_dir(root=None):
    root = root or PM_OS_DIR
    live = os.path.join(root, "profile")
    if os.path.isdir(live):
        return live
    return os.path.join(root, "profile.example")


def _load_yaml(name, root=None):
    path = os.path.join(profile_dir(root), name)
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return _yaml.load(f) or {}


def profile(root=None):
    return _load_yaml("profile.yaml", root)


def integrations(root=None):
    return _load_yaml("integrations.yaml", root)


def config(root=None):
    return _load_yaml("config.yaml", root)
