"""Jira project-management adapter. Wraps the existing jira_publish helpers."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import profile_lib  # noqa: E402
import jira_publish  # noqa: E402
from adapters.project_management._contract import NotConfigured  # noqa: E402


def is_configured(root=None) -> bool:
    cfg = profile_lib.jira_config(root)
    return bool(cfg.get("cloud_id") and cfg.get("project_key"))


def publish(draft, root=None):
    if not is_configured(root):
        raise NotConfigured("Jira is not configured in this profile")
    return jira_publish.publish_to_jira(draft)
