import os
import profile_lib


def test_profile_dir_prefers_live_profile(profile_root):
    assert profile_lib.profile_dir(root=profile_root).endswith("/profile")


def test_profile_dir_falls_back_to_example(tmp_path):
    # No profile/ dir, but a profile.example/ exists
    (tmp_path / "profile.example").mkdir()
    assert profile_lib.profile_dir(root=str(tmp_path)).endswith("/profile.example")


def test_raw_loaders_return_dicts(profile_root):
    assert profile_lib.profile(root=profile_root)["display_name"] == "Test User"
    assert profile_lib.integrations(root=profile_root)["project_management"]["provider"] == "jira"
    assert profile_lib.config(root=profile_root)["models"]["judge"] == "claude-opus-4-8"


def test_missing_file_returns_empty_dict(tmp_path):
    (tmp_path / "profile").mkdir()
    assert profile_lib.profile(root=str(tmp_path)) == {}


def test_identity_accessors(profile_root):
    assert profile_lib.display_name(root=profile_root) == "Test User"
    assert profile_lib.email(root=profile_root) == "test@example.com"
    assert profile_lib.company(root=profile_root) == "Acme"
    assert profile_lib.persona(root=profile_root) == "pm"


def test_identity_fallbacks_when_absent(tmp_path):
    (tmp_path / "profile").mkdir()
    assert profile_lib.display_name(root=str(tmp_path)) == "Operator"
    assert profile_lib.persona(root=str(tmp_path)) == "pm"
