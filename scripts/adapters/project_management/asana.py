"""Asana adapter — documented drop-in stub.

The seam is wired: select provider "asana" in integrations.yaml and the loader
finds this module. To make it real, implement publish() against the Asana MCP
(mirror jira.py: read profile_lib config, push a draft, return (id, url)) and
flip is_configured() to check the profile. Until then it degrades gracefully.
"""
from adapters.project_management._contract import NotConfigured


def is_configured(root=None) -> bool:
    return False


def publish(draft, root=None):
    raise NotConfigured(
        "Asana adapter is a stub — implement publish() against the Asana MCP")
