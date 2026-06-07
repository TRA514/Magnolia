import os
from task_dispatch import load_workers

PM_OS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(PM_OS_DIR, ".claude", "skills")


def _folder_exists(name):
    d = os.path.join(SKILLS_DIR, name)
    return os.path.isfile(os.path.join(d, "SKILL.md")) or os.path.isfile(os.path.join(d, "skill.md"))


def test_every_worker_skill_resolves_to_a_flat_folder():
    """Worker skills: must be flat folder names that exist on disk. Guards the
    nested->flat rename and stops a regression where build_skills_catalog_filtered
    silently falls through to the full catalog."""
    offenders = []
    for w in load_workers():
        for s in w.get("skills", []):
            if "/" in s or not _folder_exists(s):
                offenders.append(f"{w['name']}: {s}")
    assert not offenders, "Unresolved/nested worker skills:\n" + "\n".join(offenders)
