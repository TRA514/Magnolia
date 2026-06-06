import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Tenant-specific literals that must never ship in the blank template.
# These are genuinely operator-specific facts (a particular Pendo tenant's
# subscription id, a particular Databricks catalog name) — NOT generic
# instructional words like "catalog", "zendesk", or "subId", which legitimately
# appear in prose describing how to read the value from the active profile.
BANNED = [
    "4818486697721856",  # Vantaca Pendo subscription id
    "is_prod",           # Vantaca Databricks catalog name
]


def test_no_hardcoded_tenant_ids_in_skills_or_workers():
    hits = []
    paths = glob.glob(os.path.join(ROOT, ".claude/skills/**/*.md"), recursive=True)
    paths += glob.glob(os.path.join(ROOT, "scripts/workers/*.md"))
    for path in paths:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for token in BANNED:
            if token in text:
                hits.append(f"{os.path.relpath(path, ROOT)}: '{token}'")
    assert hits == [], f"hardcoded tenant facts: {hits}"
