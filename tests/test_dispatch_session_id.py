import re
import task_dispatch as td


def test_build_claude_cmd_includes_session_id():
    cmd, sid = td.build_claude_cmd(prompt="x", model="m", tools_str="Read(*)", max_turns="30")
    assert "--session-id" in cmd
    assert cmd[cmd.index("--session-id") + 1] == sid
    assert re.match(r"[0-9a-f-]{36}", sid)


def test_build_claude_cmd_prompt_is_first_positional():
    # GOTCHA: --allowedTools is variadic and will swallow a trailing prompt.
    # The prompt MUST be the first positional arg (right after "claude").
    cmd, _ = td.build_claude_cmd(prompt="my prompt", model="m", tools_str="Read(*)", max_turns="30")
    assert cmd[0] == "claude"
    assert cmd[1] == "my prompt"


def test_build_claude_cmd_accepts_explicit_session_id():
    cmd, sid = td.build_claude_cmd(prompt="x", model="m", tools_str="Read(*)", max_turns="30", session_id="FIXED-SID")
    assert sid == "FIXED-SID"
    assert cmd[cmd.index("--session-id") + 1] == "FIXED-SID"
