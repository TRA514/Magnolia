"""Adapter loader: maps a profile integration family to its provider module.

Each family lives under scripts/adapters/<family>/ with one module per provider
(<provider>.py) conforming to that family's _contract.py Protocol. The loader is
the ONLY place that knows provider-name -> module; adding a provider = drop a
module in and select it in the profile. Calendar/doc_sync generalize to the same
shape when their turn comes.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402


def get(family, root=None):
    """Return the adapter module for the family's active provider, or None."""
    provider = profile_lib.provider(family, root)
    if provider == "none":
        return None
    try:
        return importlib.import_module(f"adapters.{family}.{provider}")
    except ModuleNotFoundError:
        return None
