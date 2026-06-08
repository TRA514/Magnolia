import chat_runner as cr


def test_chat_tools_exclude_external_writes():
    tools = cr.CHAT_ALLOWED_TOOLS
    assert isinstance(tools, (list, tuple))
    joined = ",".join(tools)
    # read/search/draft on local artifacts are allowed
    assert any("Read" in t for t in tools)
    # external-write tool names must NOT appear anywhere in the allowlist
    for banned in ("createIssue", "sendMessage", "createEvent", "publish", "send_message", "create_issue"):
        assert banned not in joined
    # the broad mcp__* wildcard must NOT be present (it would grant external sends)
    assert "mcp__*" not in tools
    assert not any(t.strip() == "mcp__*" or t.strip().startswith("mcp__*") for t in tools)


def test_build_chat_cmd_uses_locked_allowlist_by_default():
    cmd = cr.build_chat_cmd(session_id="S", message="hi", model="m", new_session=False)
    # --allowedTools value is the joined locked allowlist, not the old placeholder
    i = cmd.index("--allowedTools")
    tools_arg = cmd[i + 1]
    assert "mcp__*" not in tools_arg
    for banned in ("createIssue", "sendMessage", "createEvent"):
        assert banned not in tools_arg


def test_chat_tools_allow_local_task_cli_but_not_broad_bash():
    """task.sh is a thin wrapper over task_cli.py — purely local task-file ops
    (add/list/show/update/done/agent:*/inbox) with NO external-write surface
    (no http/requests/adapters/publish). So the chat may run it directly. But
    the broad Bash escape hatch must stay closed: a chat that could run any
    shell command could `curl`/`gh`/`mail` an external send (invariant #5)."""
    tools = cr.CHAT_ALLOWED_TOOLS
    assert any("task.sh" in t for t in tools), "chat should be allowed to run the local task CLI"
    # plain Bash / Bash(*) must NOT be present — Bash stays narrowly scoped.
    assert "Bash" not in tools
    assert "Bash(*)" not in tools
    assert not any(t.strip() == "Bash(:*)" for t in tools)
