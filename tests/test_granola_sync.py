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
