import json
import chat_runner as cr


def _load_fixture():
    with open("tests/fixtures/stream_json_sample.jsonl") as f:
        return [json.loads(l) for l in f if l.strip()]


def test_normalize_maps_event_kinds_from_real_fixture():
    raw = _load_fixture()
    events = [e for r in raw for e in cr.normalize(r)]
    kinds = {e["kind"] for e in events}
    assert "text" in kinds          # assistant prose
    assert "tool_step" in kinds     # a tool_use mapped
    assert "think" in kinds         # a thinking block mapped
    # result carries usage + cost so we can measure cold-open cost
    result = [e for e in events if e["kind"] == "result"]
    assert result and "usage" in result[0] and "cost" in result[0]


def test_tool_step_has_verb_and_target():
    raw = _load_fixture()
    steps = [e for r in raw for e in cr.normalize(r) if e.get("kind") == "tool_step"]
    assert steps, "expected at least one tool_step from the fixture"
    s = steps[0]
    assert s["verb"]                 # e.g. "Read"
    assert "target" in s             # may be a path/pattern/etc.


def test_system_and_tool_result_events_yield_nothing():
    assert cr.normalize({"type": "system", "subtype": "init", "session_id": "x"}) == []
    assert cr.normalize({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "content": "out"}]}}) == []


def test_missing_content_does_not_raise():
    assert cr.normalize({"type": "assistant"}) == []
    assert cr.normalize({"type": "assistant", "message": {}}) == []
