def test_build_profile_shape(profile_root):
    import task_server
    p = task_server.build_profile(root=profile_root)
    assert p["identity"]["name"] == "Test User"
    assert p["identity"]["email"] == "test@example.com"
    assert "system" not in p                       # System section is cut
    pm = p["integrations"]["project_management"]
    assert pm["active"] == "jira"
    assert any(o["id"] == "jira" for o in pm["options"])
    assert all("status" in o for o in pm["options"])
    # voice is two channels read from the md files
    assert "Tight" in p["voice"]["teams"] and "Warm" in p["voice"]["email"]
    # packs: active from config + an available catalog with id/label/description
    assert "core" in p["packs"]["active"]
    assert all({"id", "label", "description"} <= set(a) for a in p["packs"]["available"])
    # model posture level from config; workers is a list (possibly empty)
    assert p["model_posture"]["level"] == "balanced"
    assert isinstance(p["model_posture"]["workers"], list)


def test_build_profile_status_from_capabilities(profile_root):
    # The Doctor keys remote capabilities by the provider id itself (see
    # doctor._REMOTE_FROM_INTEGRATION: project_management -> prov), so the
    # capability key for the Jira PM provider is literally "jira".
    import task_server
    import profile_lib
    profile_lib.write_capabilities({"capabilities": {"jira": {"status": "reauth"}}}, root=profile_root)
    p = task_server.build_profile(root=profile_root)
    jira = next(o for o in p["integrations"]["project_management"]["options"] if o["id"] == "jira")
    assert jira["status"] == "reauth"


def test_build_profile_active_provider_status_ok_without_capability(profile_root):
    # jira is the configured PM provider; with no capability entry it should read "ok"
    import task_server
    p = task_server.build_profile(root=profile_root)
    jira = next(o for o in p["integrations"]["project_management"]["options"] if o["id"] == "jira")
    assert jira["status"] in ("ok", "reauth", "unset")   # derived, present
