import chat_runner as cr


def test_resume_cmd_uses_resume_not_session_id():
    cmd = cr.build_chat_cmd(session_id="S1", message="hi", model="m", new_session=False)
    assert cmd[0] == "claude"
    assert cmd[1] == "hi"                      # prompt first positional (variadic --allowedTools gotcha)
    assert "--resume" in cmd and cmd[cmd.index("--resume")+1] == "S1"
    assert "--session-id" not in cmd
    assert "--output-format" in cmd and cmd[cmd.index("--output-format")+1] == "stream-json"
    assert "--verbose" in cmd


def test_new_session_cmd_uses_session_id():
    cmd = cr.build_chat_cmd(session_id="S2", message="hi", model="m", new_session=True)
    assert "--session-id" in cmd and cmd[cmd.index("--session-id")+1] == "S2"
    assert "--resume" not in cmd


def test_system_prompt_is_depersonalized(monkeypatch):
    monkeypatch.setattr(cr.profile_lib, "display_name", lambda *a, **k: "Dana Cole")
    monkeypatch.setattr(cr.profile_lib, "company", lambda *a, **k: "Acme")
    task = {"id": "TASK-9", "title": "Draft the thing", "queue": "agent",
            "status": "open", "priority": "high"}
    p = cr.build_context_prompt(task, "do the thing")
    assert "Jay" not in p                       # no identity literal
    assert "Dana Cole" in p                      # pulled from profile
    assert "Draft the thing" in p                # task context present
    assert "do the thing" in p                   # user message present
