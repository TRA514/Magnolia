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


# build_profile owns the /api/profile contract the frontend consumes. The
# Doctor writes capability statuses from a richer vocabulary
# (ok/missing/degraded/running/down/not_expected/needs_reauth/unknown), but
# the Profile room frontend only understands {ok, reauth, available, unset}.
# build_profile MUST normalize Doctor statuses into the frontend vocabulary.
_FRONTEND_STATUS_VOCAB = {"ok", "reauth", "available", "unset"}


def test_build_profile_status_from_capabilities(profile_root):
    # The Doctor keys remote capabilities by the provider id itself (see
    # doctor._REMOTE_FROM_INTEGRATION: project_management -> prov), so the
    # capability key for the Jira PM provider is literally "jira".
    # A Doctor "needs_reauth" status must normalize to the frontend "reauth".
    import task_server
    import profile_lib
    profile_lib.write_capabilities({"capabilities": {"jira": {"status": "needs_reauth"}}}, root=profile_root)
    p = task_server.build_profile(root=profile_root)
    jira = next(o for o in p["integrations"]["project_management"]["options"] if o["id"] == "jira")
    assert jira["status"] == "reauth"           # normalized, NOT "needs_reauth"
    assert jira["status"] in _FRONTEND_STATUS_VOCAB


def test_build_profile_status_missing_normalizes_to_unset(profile_root):
    import task_server
    import profile_lib
    profile_lib.write_capabilities({"capabilities": {"jira": {"status": "missing"}}}, root=profile_root)
    p = task_server.build_profile(root=profile_root)
    jira = next(o for o in p["integrations"]["project_management"]["options"] if o["id"] == "jira")
    assert jira["status"] == "unset"
    assert jira["status"] in _FRONTEND_STATUS_VOCAB


def test_build_profile_status_ok_normalizes_to_ok(profile_root):
    import task_server
    import profile_lib
    profile_lib.write_capabilities({"capabilities": {"jira": {"status": "ok"}}}, root=profile_root)
    p = task_server.build_profile(root=profile_root)
    jira = next(o for o in p["integrations"]["project_management"]["options"] if o["id"] == "jira")
    assert jira["status"] == "ok"
    assert jira["status"] in _FRONTEND_STATUS_VOCAB


def test_build_profile_transcript_status_from_category_capability(profile_root):
    # The Doctor keys the transcripts capability by CATEGORY ("transcript"), not provider id.
    import task_server, profile_lib
    # profile_root's integrations.yaml has transcript provider = granola (active)
    profile_lib.write_capabilities({"capabilities": {"transcript": {"status": "needs_reauth",
                                                                      "detail": "session expired"}}},
                                    root=profile_root)
    p = task_server.build_profile(root=profile_root)
    opts = p["integrations"]["transcripts"]["options"]
    active = next(o for o in opts if o["id"] == p["integrations"]["transcripts"]["active"])
    assert active["status"] == "reauth"          # normalized from needs_reauth via the category key
    assert "session expired" in (active.get("detail") or "")


def test_build_profile_active_provider_status_ok_without_capability(profile_root):
    # With no capability entry: the active provider (jira) reads "ok" and a
    # non-active known adapter (asana) reads "available".
    import task_server
    p = task_server.build_profile(root=profile_root)
    pm = p["integrations"]["project_management"]
    jira = next(o for o in pm["options"] if o["id"] == "jira")
    assert jira["status"] == "ok"
    assert jira["status"] in _FRONTEND_STATUS_VOCAB
    asana = next((o for o in pm["options"] if o["id"] == "asana"), None)
    if asana is not None:
        assert asana["status"] == "available"
        assert asana["status"] in _FRONTEND_STATUS_VOCAB
