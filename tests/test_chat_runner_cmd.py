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


def test_task_context_block_has_volatile_fields_and_gates_optional():
    # Required fields always present; optional fields only when truthy.
    block = cr._task_context_block(
        {"id": "T-1", "title": "Do it", "status": "in_progress",
         "priority": "high", "queue": "agent", "project": "retention"}
    )
    assert "## Task context" in block
    assert "- id: T-1" in block
    assert "- status: in_progress" in block
    assert "- priority: high" in block
    assert "- queue: agent" in block
    assert "- project: retention" in block      # optional, present
    assert "domain" not in block                 # optional, absent -> omitted
    # Description (or body) is included by default.
    with_desc = cr._task_context_block({"id": "T-2", "body": "the long body"})
    assert "- description: the long body" in with_desc
    # ...and omitted when include_description=False.
    no_desc = cr._task_context_block({"id": "T-2", "body": "the long body"},
                                     include_description=False)
    assert "the long body" not in no_desc


def test_build_resume_prompt_injects_current_state_without_persona_preamble(monkeypatch):
    monkeypatch.setattr(cr.profile_lib, "display_name", lambda *a, **k: "Dana Cole")
    task = {"id": "T-9", "title": "Draft the thing", "status": "in_progress",
            "priority": "high", "queue": "agent", "body": "a very long body here"}
    p = cr.build_resume_prompt(task, "what's left?")
    assert "## Current task state" in p          # fresh-state heading
    assert "- status: in_progress" in p          # volatile field re-injected
    assert "what's left?" in p                    # the operator's message
    assert "Dana Cole" in p                       # de-personalized via profile
    assert "Jay" not in p
    # Resume does NOT replay the persona framing (session already has it)...
    assert "task execution assistant" not in p
    # ...and does NOT re-send the long body (it's in session history already).
    assert "a very long body here" not in p
