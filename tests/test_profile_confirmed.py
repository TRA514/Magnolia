import profile_lib


def test_set_confirmed_false_creates_flag_and_preserves_siblings(profile_root):
    profile_lib.set_integration_confirmed("project_management", False, provider="jira", root=profile_root)
    block = profile_lib.integration("project_management", root=profile_root)["jira"]
    assert block["confirmed"] is False
    assert block["project_key"] == "ACM"          # sibling preserved


def test_set_confirmed_true_roundtrips(profile_root):
    profile_lib.set_integration_confirmed("project_management", True, provider="jira", root=profile_root)
    block = profile_lib.integration("project_management", root=profile_root)["jira"]
    assert block["confirmed"] is True


def test_set_confirmed_creates_provider_block_when_absent(profile_root):
    # 'linear' has no sub-block in the fixture — setter must create it.
    profile_lib.set_integration_confirmed("project_management", False, provider="linear", root=profile_root)
    block = profile_lib.integration("project_management", root=profile_root)
    assert block["linear"]["confirmed"] is False
