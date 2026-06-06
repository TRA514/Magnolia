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


def test_integration_and_provider(profile_root):
    assert profile_lib.provider("transcript", root=profile_root) == "granola"
    assert profile_lib.provider("calendar", root=profile_root) == "m365"
    assert profile_lib.provider("nonexistent", root=profile_root) == "none"


def test_jira_config_when_jira(profile_root):
    jc = profile_lib.jira_config(root=profile_root)
    assert jc["cloud_id"] == "acme.atlassian.net"
    assert jc["project_key"] == "ACM"
    assert jc["default_assignee"] == "acct-123"


def test_jira_config_empty_when_not_jira(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text(
        "project_management:\n  provider: asana\n"
    )
    assert profile_lib.jira_config(root=str(tmp_path)) == {}


def test_model_accessor(profile_root):
    assert profile_lib.model("judge", root=profile_root) == "claude-opus-4-8"
    assert profile_lib.model("missing", default="x", root=profile_root) == "x"


def test_voice_text_concatenates_channels(profile_root):
    txt = profile_lib.voice_text(root=profile_root)
    assert "Teams voice" in txt
    assert "Email voice" in txt


def test_voice_text_single_channel(profile_root):
    assert "Teams voice" in profile_lib.voice_text("teams", root=profile_root)
    assert "Email voice" not in profile_lib.voice_text("teams", root=profile_root)


def test_voice_text_falls_back_to_example(tmp_path):
    # Only profile.example/ exists (no live profile/) -> voice still resolves.
    ex = tmp_path / "profile.example" / "voice"
    ex.mkdir(parents=True)
    (ex / "teams.md").write_text("# Example teams voice\n")
    (ex / "email.md").write_text("# Example email voice\n")
    txt = profile_lib.voice_text(root=str(tmp_path))
    assert "Example teams voice" in txt
    assert "Example email voice" in txt


def test_loader_handles_comments_only_file(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "profile.yaml").write_text("# only a comment, no keys\n")
    assert profile_lib.profile(root=str(tmp_path)) == {}
    assert profile_lib.display_name(root=str(tmp_path)) == "Operator"


def test_provider_handles_null_value(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("project_management:\n")
    assert profile_lib.provider("project_management", root=str(tmp_path)) == "none"
    assert profile_lib.jira_config(root=str(tmp_path)) == {}


def test_server_port_default(tmp_path):
    (tmp_path / "profile").mkdir()
    assert profile_lib.server_port(root=str(tmp_path)) == 8742


def test_server_port_from_config(profile_root):
    # profile_root fixture defines a server block with port 8755
    assert profile_lib.server_port(root=profile_root) == 8755


def test_transcript_config_defaults(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: otter\n")
    tc = profile_lib.transcript_config(root=str(tmp_path))
    assert tc["provider"] == "otter"
    assert tc["target"] == "datasets/meetings/"  # default applied


def test_transcript_dir_under_profile(tmp_path):
    (tmp_path / "profile").mkdir()
    d = profile_lib.transcript_state_dir(root=str(tmp_path))
    assert d.endswith("/profile/transcript")


def test_doc_sync_config_from_integrations(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "integrations.yaml").write_text(
        "doc_sync:\n"
        "  onedrive_root: \"~/Library/CloudStorage/OneDrive-Acme\"\n"
        "  sharepoint_site: \"PM-OS\"\n"
        "  enabled: true\n"
    )
    dc = profile_lib.doc_sync_config(root=str(tmp_path))
    assert dc["sharepoint_site"] == "PM-OS"
    assert dc["enabled"] is True


def test_doc_sync_config_defaults_disabled(tmp_path):
    (tmp_path / "profile").mkdir()
    assert profile_lib.doc_sync_config(root=str(tmp_path))["enabled"] is False


def test_pendo_config_reads_from_profile(profile_root):
    import profile_lib
    p = os.path.join(profile_root, "profile", "integrations.yaml")
    with open(p, "a") as f:
        f.write("analytics:\n  pendo:\n    provider: pendo\n"
                "    subscription_id: '123'\n    app_ids: {web: 'a1'}\n")
    cfg = profile_lib.pendo_config(root=profile_root)
    assert cfg["subscription_id"] == "123"
    assert cfg["app_ids"]["web"] == "a1"


def test_databricks_config_defaults_empty(profile_root):
    import profile_lib
    cfg = profile_lib.databricks_config(root=profile_root)
    assert cfg["catalog"] == ""
    assert cfg["sources"] == {}
