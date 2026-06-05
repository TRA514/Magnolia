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
    with open(path, encoding="utf-8") as f:
        return _yaml.load(f) or {}


def profile(root=None):
    return _load_yaml("profile.yaml", root)


def integrations(root=None):
    return _load_yaml("integrations.yaml", root)


def config(root=None):
    return _load_yaml("config.yaml", root)


def display_name(root=None):
    return profile(root).get("display_name") or "Operator"


def email(root=None):
    return profile(root).get("email", "")


def company(root=None):
    return profile(root).get("company", "")


def persona(root=None):
    return profile(root).get("persona") or "pm"


def integration(name, root=None):
    return integrations(root).get(name) or {}


def provider(name, root=None):
    return integration(name, root).get("provider") or "none"


def jira_config(root=None):
    pm = integration("project_management", root)
    if pm.get("provider") != "jira":
        return {}
    return pm.get("jira") or {}


def model(role, default=None, root=None):
    return (config(root).get("models") or {}).get(role, default)


def voice_path(channel, root=None):
    return os.path.join(profile_dir(root), "voice", f"{channel}.md")


def voice_text(channel=None, root=None):
    """Return voice guidance. channel='teams'|'email', or None for both concatenated."""
    channels = [channel] if channel else ["teams", "email"]
    chunks = []
    for ch in channels:
        path = voice_path(ch, root)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                chunks.append(f.read().strip())
    return "\n\n".join(chunks)


if __name__ == "__main__":
    import sys
    if "--display-name" in sys.argv:
        print(display_name())
