import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import granola_sync


def _profile(tmp_path, provider="granola"):
    (tmp_path / "profile").mkdir(exist_ok=True)
    (tmp_path / "profile" / "integrations.yaml").write_text(
        f"transcript:\n  provider: {provider}\n  target: datasets/meetings/\n")
    (tmp_path / "profile" / "config.yaml").write_text("models: {}\n")


def test_main_writes_and_records(tmp_path, monkeypatch):
    _profile(tmp_path)
    monkeypatch.setattr(granola_sync.profile_lib, "PM_OS_DIR", str(tmp_path))
    monkeypatch.setattr(granola_sync, "_state_dir", lambda root=None: str(tmp_path / "st"))
    monkeypatch.setattr(granola_sync, "_fetch_new_meetings",
        lambda seen, root=None: [{"id": "uuid-9", "title": "Voice AI call",
            "created_at": "2026-06-08T10:00:00Z", "attendees": ["Ann"],
            "transcript": "Ann: hello world"}])
    fired = {}
    monkeypatch.setattr(granola_sync.transcript_post, "run_downstream",
        lambda txt, mid, state, log: fired.setdefault(mid, txt) or str(txt))
    granola_sync.main(root=str(tmp_path))
    state = json.load(open(tmp_path / "st" / "granola_downloaded.json"))
    assert "uuid-9" in state                      # recorded
    assert "uuid-9" in fired                       # downstream fired
    # second run: already seen -> no new fetch, no error
    monkeypatch.setattr(granola_sync, "_fetch_new_meetings", lambda seen, root=None: [])
    granola_sync.main(root=str(tmp_path))


def test_main_noop_when_provider_not_granola(tmp_path, monkeypatch):
    _profile(tmp_path, provider="otter")
    called = {"fetch": False}
    monkeypatch.setattr(granola_sync, "_fetch_new_meetings",
        lambda seen, root=None: called.__setitem__("fetch", True) or [])
    result = granola_sync.main(root=str(tmp_path))
    assert called["fetch"] is False               # provider gate: never fetched
    assert result["status"] == "skipped"


def test_parse_fetch_output_handles_wrapped_and_malformed():
    # wrapped {"result": "...json array..."}
    assert granola_sync._parse_fetch_output('{"result": "[{\\"id\\": \\"a\\"}]"}') == [{"id": "a"}]
    # bare array
    assert granola_sync._parse_fetch_output('[{"id": "b"}]') == [{"id": "b"}]
    # array embedded in prose
    assert granola_sync._parse_fetch_output('here you go: [{"id": "c"}] done') == [{"id": "c"}]
    # malformed -> None
    assert granola_sync._parse_fetch_output("not json at all") is None
    assert granola_sync._parse_fetch_output("") is None
    # non-string `result` must NOT crash (was AttributeError on .find) -> None
    assert granola_sync._parse_fetch_output('{"result": null}') is None
    assert granola_sync._parse_fetch_output('{"result": 42}') is None
    assert granola_sync._parse_fetch_output('{"result": {"x": 1}}') is None
    # result is already a list -> returned as-is
    assert granola_sync._parse_fetch_output('{"result": [{"id": "z"}]}') == [{"id": "z"}]


def test_basename_unique_per_meeting_id():
    # Same created_at + title, different ids -> different basenames.
    b1, _ = granola_sync._basename("2026-06-08T10:00:00Z", "Sync", "aaaaaaaa-1111")
    b2, _ = granola_sync._basename("2026-06-08T10:00:00Z", "Sync", "bbbbbbbb-2222")
    assert b1 != b2
    assert b1.endswith("_aaaaaaaa") and b2.endswith("_bbbbbbbb")
    # Missing/short id is tolerated (no suffix, no crash).
    b3, _ = granola_sync._basename("2026-06-08T10:00:00Z", "Sync", None)
    assert b3.endswith("_Sync")


def test_main_same_minute_title_different_ids_no_overwrite(tmp_path, monkeypatch):
    _profile(tmp_path)
    monkeypatch.setattr(granola_sync.profile_lib, "PM_OS_DIR", str(tmp_path))
    monkeypatch.setattr(granola_sync, "_state_dir", lambda root=None: str(tmp_path / "st"))
    monkeypatch.setattr(granola_sync, "_fetch_new_meetings",
        lambda state, root=None: [
            {"id": "id-aaaa1111", "title": "Standup", "created_at": "2026-06-08T10:00:00Z",
             "attendees": ["Ann"], "transcript": "a"},
            {"id": "id-bbbb2222", "title": "Standup", "created_at": "2026-06-08T10:00:00Z",
             "attendees": ["Bob"], "transcript": "b"},
        ])
    written = []
    monkeypatch.setattr(granola_sync.transcript_post, "run_downstream",
        lambda txt, mid, state, log: written.append(str(txt)) or str(txt))
    granola_sync.main(root=str(tmp_path))
    assert len(written) == 2
    assert len(set(written)) == 2                  # distinct file paths
    for p in written:
        assert os.path.exists(p)                   # both files actually exist


def test_prompt_ids_bounds_and_recency():
    # dict keyed by uuid -> most-recently-downloaded SEEN_IN_PROMPT ids
    state = {f"id-{i}": {"downloaded_at": f"2026-06-08T00:{i:02d}:00"} for i in range(50)}
    ids = granola_sync._prompt_ids(state)
    assert len(ids) == 50                          # under the cap -> all returned
    assert ids[0] == "id-49"                       # newest first

    big = {f"id-{i}": {"downloaded_at": f"2026-{(i % 12) + 1:02d}-01T00:00:00"}
           for i in range(500)}
    capped = granola_sync._prompt_ids(big)
    assert len(capped) == granola_sync.SEEN_IN_PROMPT  # capped at 200
    # a bare set is accepted too (no recency, just a slice)
    assert len(granola_sync._prompt_ids(set(f"x{i}" for i in range(500)))) == \
        granola_sync.SEEN_IN_PROMPT


def test_prompt_ids_tolerates_legacy_string_ledger():
    # The on-disk ledger is {uuid: "filename.md"} (string values), not
    # {uuid: {"downloaded_at": ...}}. _prompt_ids must not crash on it.
    legacy = {
        "id-a": "2026-06-15_ops_elt_vantaca.md",
        "id-b": "2026-06-12_ops_t2_vantaca.md",
        "id-c": "2026-06-08_strategy_x_vantaca.md",
    }
    ids = granola_sync._prompt_ids(legacy)
    assert set(ids) == {"id-a", "id-b", "id-c"}     # all keys returned, no crash
    # date-prefixed filename strings sort newest-first, same intent as downloaded_at
    assert ids[0] == "id-a"

    # mixed legacy-string + new-dict values must also be tolerated
    mixed = {
        "id-old": "2026-06-01_ops_x_vantaca.md",
        "id-new": {"downloaded_at": "2026-06-20T00:00:00", "title": "New"},
    }
    mixed_ids = granola_sync._prompt_ids(mixed)
    assert set(mixed_ids) == {"id-old", "id-new"}
    assert mixed_ids[0] == "id-new"                 # newest by sort key first


def test_looks_like_placeholder():
    assert granola_sync._looks_like_placeholder("") is True
    assert granola_sync._looks_like_placeholder(None) is True
    assert granola_sync._looks_like_placeholder(
        "[Full transcript available - engineering capacity, Atlas blockers]") is True
    assert granola_sync._looks_like_placeholder("too short") is True
    real = "Me: Morning. Them: Morning, how are you? " * 20  # > 200 chars of dialogue
    assert granola_sync._looks_like_placeholder(real) is False


def test_fetch_one_transcript_writes_then_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(granola_sync.profile_lib, "PM_OS_DIR", str(tmp_path))
    def _fake_run(prompt, tools, root=None):
        # the model "writes" the transcript to the path named in the prompt
        import re
        m = re.search(r"file path: (\S+)", prompt)
        if m:
            from pathlib import Path as _P
            _P(m.group(1)).write_text("Me: hi. Them: hello. real content.", encoding="utf-8")
        return "DONE"
    monkeypatch.setattr(granola_sync, "_run_claude", _fake_run)
    assert granola_sync._fetch_one_transcript("id-1") == "Me: hi. Them: hello. real content."


def test_fetch_one_transcript_none_when_not_written(tmp_path, monkeypatch):
    monkeypatch.setattr(granola_sync.profile_lib, "PM_OS_DIR", str(tmp_path))
    monkeypatch.setattr(granola_sync, "_run_claude", lambda p, t, root=None: "NONE")
    assert granola_sync._fetch_one_transcript("id-2") is None


def test_list_new_meetings_filters_seen(monkeypatch):
    monkeypatch.setattr(granola_sync, "_run_claude",
        lambda prompt, tools, root=None: '[{"id":"a","title":"A","created_at":"2026-06-08T10:00:00Z","attendees":[]},'
                                         '{"id":"b","title":"B","created_at":"2026-06-09T10:00:00Z","attendees":[]}]')
    out = granola_sync._list_new_meetings({"a": "old.md"})  # 'a' already seen
    assert [m["id"] for m in out] == ["b"]




def test_fetch_new_meetings_skips_placeholder(monkeypatch):
    monkeypatch.setattr(granola_sync, "_list_new_meetings",
        lambda s, root=None: [
            {"id": "good", "title": "G", "created_at": "2026-06-08T10:00:00Z", "attendees": ["Ann"]},
            {"id": "stub", "title": "S", "created_at": "2026-06-09T10:00:00Z", "attendees": []},
        ])
    real = "Me: real discussion about the roadmap and next steps. " * 10
    def _one(mid, root=None):
        return real if mid == "good" else "[Full transcript available - topic keywords]"
    monkeypatch.setattr(granola_sync, "_fetch_one_transcript", _one)
    out = granola_sync._fetch_new_meetings(set())
    assert [m["id"] for m in out] == ["good"]            # placeholder meeting skipped
    assert out[0]["transcript"] == real
    assert out[0]["title"] == "G" and out[0]["attendees"] == ["Ann"]


def test_main_downstream_error_isolated(tmp_path, monkeypatch):
    _profile(tmp_path)
    monkeypatch.setattr(granola_sync.profile_lib, "PM_OS_DIR", str(tmp_path))
    monkeypatch.setattr(granola_sync, "_state_dir", lambda root=None: str(tmp_path / "st"))
    monkeypatch.setattr(granola_sync, "_fetch_new_meetings",
        lambda state, root=None: [
            {"id": "bad-1", "title": "Boom", "created_at": "2026-06-08T10:00:00Z",
             "transcript": "x"},
            {"id": "good-2", "title": "Fine", "created_at": "2026-06-08T11:00:00Z",
             "transcript": "y"},
        ])

    def _downstream(txt, mid, state, log):
        if mid == "bad-1":
            raise RuntimeError("downstream blew up")
        return str(txt)
    monkeypatch.setattr(granola_sync.transcript_post, "run_downstream", _downstream)
    result = granola_sync.main(root=str(tmp_path))
    # one bad meeting did not abort the loop; the good one still processed
    assert result["new"] == 1
    state = json.load(open(tmp_path / "st" / "granola_downloaded.json"))
    assert "bad-1" in state                        # bad meeting stays seen (won't retry endlessly)
    assert "good-2" in state and state["good-2"].get("final_path")
