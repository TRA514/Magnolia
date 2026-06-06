"""Hermetic tests for doc_sync.py's profile/legacy config overlay (Task 20 follow-up).

These tests never touch a real profile or a real sync_config.yaml. They:
  - monkeypatch ``doc_sync._profile_doc_sync`` so no real profile is read, and
  - monkeypatch ``doc_sync.CONFIG_PATH`` so no real sync_config.yaml is read.

Covered cases:
  1. disabled  -> legacy values unchanged (overlay does not fire)
  2. enabled   -> profile's onedrive_root/sharepoint_site win; legacy-only keys
                  (tenant url, doc root, sync_paths) still come from the YAML
  3. enabled + absent config + empty onedrive_root -> clean SystemExit (guard)
  4. enabled + absent config + populated onedrive_root -> minimal config built
"""
import os
import textwrap
from pathlib import Path

import pytest

import doc_sync


LEGACY_YAML = textwrap.dedent("""\
    onedrive_root: "/tmp/legacy-od"
    sharepoint_site: "Legacy-Site"
    sharepoint_tenant_url: "https://legacy.sharepoint.com"
    sharepoint_doc_root: "/personal/legacy/Documents"
    sync_enabled: true
    sync_paths:
      - datasets/product/**/*.md
    sync_exclude:
      - datasets/product/drafts/*.md
""")


def _write_config(tmp_path, text=LEGACY_YAML):
    cfg = tmp_path / "sync_config.yaml"
    cfg.write_text(text)
    return cfg


def test_disabled_legacy_unchanged(tmp_path, monkeypatch):
    """Profile doc_sync disabled -> overlay does not fire; legacy values stand."""
    monkeypatch.setattr(doc_sync, "_profile_doc_sync", lambda: {})
    cfg = _write_config(tmp_path)
    monkeypatch.setattr(doc_sync, "CONFIG_PATH", cfg)

    config = doc_sync.load_config()

    assert config["onedrive_root"] == os.path.expanduser("/tmp/legacy-od")
    assert config["sharepoint_site"] == "Legacy-Site"
    assert config["sharepoint_tenant_url"] == "https://legacy.sharepoint.com"
    assert config["sharepoint_doc_root"] == "/personal/legacy/Documents"
    assert config["sync_paths"] == ["datasets/product/**/*.md"]


def test_enabled_overlay_wins(tmp_path, monkeypatch):
    """Profile enabled -> profile onedrive_root/sharepoint_site override the YAML,
    while legacy-only keys still come from the YAML."""
    monkeypatch.setattr(
        doc_sync,
        "_profile_doc_sync",
        lambda: {
            "onedrive_root": "/tmp/od-acme",
            "sharepoint_site": "PM-OS",
            "enabled": True,
        },
    )
    cfg = _write_config(tmp_path)
    monkeypatch.setattr(doc_sync, "CONFIG_PATH", cfg)

    config = doc_sync.load_config()

    # Overlay won for the fields the profile carries.
    assert config["onedrive_root"] == os.path.expanduser("/tmp/od-acme")
    assert config["sharepoint_site"] == "PM-OS"
    # Legacy-only keys still come from the YAML.
    assert config["sharepoint_tenant_url"] == "https://legacy.sharepoint.com"
    assert config["sharepoint_doc_root"] == "/personal/legacy/Documents"
    assert config["sync_paths"] == ["datasets/product/**/*.md"]
    assert config["sync_exclude"] == ["datasets/product/drafts/*.md"]


def test_enabled_absent_config_empty_root_exits(tmp_path, monkeypatch):
    """Profile enabled, no sync_config.yaml, onedrive_root still empty (fresh
    install before Doctor) -> fail loud with SystemExit, not a relative path."""
    monkeypatch.setattr(
        doc_sync,
        "_profile_doc_sync",
        lambda: {"onedrive_root": "", "sharepoint_site": "PM-OS", "enabled": True},
    )
    missing = tmp_path / "does-not-exist" / "sync_config.yaml"
    assert not missing.exists()
    monkeypatch.setattr(doc_sync, "CONFIG_PATH", missing)

    with pytest.raises(SystemExit):
        doc_sync.load_config()


def test_enabled_absent_config_populated_root_minimal(tmp_path, monkeypatch):
    """Profile enabled, no sync_config.yaml, onedrive_root populated -> build a
    minimal config from the profile (no crash)."""
    monkeypatch.setattr(
        doc_sync,
        "_profile_doc_sync",
        lambda: {
            "onedrive_root": "/tmp/od-acme",
            "sharepoint_site": "PM-OS",
            "enabled": True,
        },
    )
    missing = tmp_path / "does-not-exist" / "sync_config.yaml"
    assert not missing.exists()
    monkeypatch.setattr(doc_sync, "CONFIG_PATH", missing)

    config = doc_sync.load_config()

    assert config["onedrive_root"] == os.path.expanduser("/tmp/od-acme")
    assert config["sharepoint_site"] == "PM-OS"
    assert config["sync_enabled"] is True
    # onedrive_dir composes onedrive_root / sharepoint_site without crashing.
    assert doc_sync.onedrive_dir(config) == Path("/tmp/od-acme") / "PM-OS"
