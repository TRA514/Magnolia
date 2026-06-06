"""Idempotently seed Magnolia's in-box default cron jobs.

datasets/cron/jobs.json is gitignored (per-person), so defaults are created at
runtime by onboarding rather than committed. Re-running is safe.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cron_lib  # noqa: E402

DEFAULTS = [
    {
        "name": "Doctor self-heal",
        "cron_expr": "0 9 * * 1",  # Monday 09:00 (croniter: 1=Monday)
        "cron_human": "Every Monday at 9:00am",
        "task_template": {
            "title": "Weekly Doctor check {date}",
            "queue": "agent",
            "priority": "low",
            "domain": "onboarding",
            "description": (
                "Run `python3 scripts/doctor.py detect`. If any capability is missing, "
                "degraded, or needs re-auth, surface a recommendation to fix it "
                "(invoke the workflow-doctor skill). Observe-only otherwise."
            ),
        },
    },
]


def seed():
    """Create any default job not already present (matched by name). Returns count added."""
    existing = {j["name"] for j in cron_lib.list_jobs()}
    added = 0
    for d in DEFAULTS:
        if d["name"] in existing:
            continue
        cron_lib.create_job(
            name=d["name"],
            cron_expr=d["cron_expr"],
            cron_human=d["cron_human"],
            task_template=d["task_template"],
            auto_dispatch=True,
        )
        added += 1
    return added


if __name__ == "__main__":
    print(f"Seeded {seed()} default cron job(s).")
