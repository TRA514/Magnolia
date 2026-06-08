import chat_transcript as ct


def test_append_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "_transcript_path", lambda tid: tmp_path / f"{tid}.chat.jsonl")
    ct.append_event("TASK-0001", {"role": "user", "kind": "text", "text": "hi",
                                  "run_id": "r1", "origin": "chat", "post_run": True})
    ct.append_event("TASK-0001", {"role": "assistant", "kind": "text", "text": "hello", "run_id": "r1"})
    events = ct.read_events("TASK-0001")
    assert len(events) == 2
    assert events[0]["text"] == "hi" and events[0]["post_run"] is True
    assert "turn_id" in events[0] and "ts" in events[0]   # stamped on append


def test_read_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "_transcript_path", lambda tid: tmp_path / f"{tid}.chat.jsonl")
    assert ct.read_events("TASK-NOPE") == []
