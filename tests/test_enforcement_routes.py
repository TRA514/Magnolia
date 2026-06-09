"""Task 9 — enforcement server routes: autonomy flag GET/POST + the kill-switch
demote. Mirrors test_send_message_route's fake-handler + state-isolation pattern:
the handlers read profile_lib/ladder_lib with repo defaults, so we monkeypatch
those helpers to inject root=profile_root / a temp ladder path. The test must NOT
mutate the real repo profile.yaml or ladder.json."""
import json

import pytest


@pytest.fixture
def srv(profile_root, tmp_path, monkeypatch):
    """task_server with profile_lib autonomy helpers pinned to profile_root and
    ladder_lib helpers pinned to a temp ladder.json, so route handlers (which call
    these with NO root/path arg) operate on the temp tree, never the real repo."""
    import task_server, profile_lib, ladder_lib

    ladder_path = str(tmp_path / "ladder.json")

    def _wrap_root(orig):
        def wrapper(*a, **k):
            if "root" not in k:
                k = {**k, "root": profile_root}
            return orig(*a, **k)
        return wrapper

    def _wrap_path(orig):
        def wrapper(*a, **k):
            if "path" not in k:
                k = {**k, "path": ladder_path}
            return orig(*a, **k)
        return wrapper

    for fn in ("autonomy_enforcement", "set_autonomy_enforcement"):
        monkeypatch.setattr(profile_lib, fn, _wrap_root(getattr(profile_lib, fn)))
    for fn in ("set_tier", "tier_of", "kill_to_supervised", "note_demotion_signal"):
        monkeypatch.setattr(ladder_lib, fn, _wrap_path(getattr(ladder_lib, fn)))

    return task_server, profile_lib, ladder_lib, ladder_path


class _FakeHandler:
    def __init__(self, body=None):
        self.status = None
        self._chunks = []
        self._body = b"" if body is None else json.dumps(body).encode("utf-8")
        self.headers = {"Content-Length": str(len(self._body))}
        self.rfile = self  # _read_request_body reads handler.rfile.read(n)
    def read(self, n): return self._body[:n]
    def send_response(self, s): self.status = s
    def send_header(self, *a): pass
    def end_headers(self): pass
    @property
    def wfile(self): return self
    def write(self, b): self._chunks.append(b)
    def json(self): return json.loads(b"".join(self._chunks).decode("utf-8"))


# ── autonomy flag GET ─────────────────────────────────────────────────────────

def test_get_autonomy_reflects_flag(srv):
    task_server, profile_lib, _, _ = srv
    profile_lib.set_autonomy_enforcement(False)  # wrapper injects root=profile_root
    h = _FakeHandler()
    task_server.handle_get_autonomy(h)
    assert h.status == 200 and h.json() == {"enabled": False}

    profile_lib.set_autonomy_enforcement(True)
    h = _FakeHandler()
    task_server.handle_get_autonomy(h)
    assert h.json() == {"enabled": True}


# ── autonomy flag POST ────────────────────────────────────────────────────────

def test_set_autonomy_flips_flag(srv):
    task_server, profile_lib, _, _ = srv
    profile_lib.set_autonomy_enforcement(False)

    h = _FakeHandler({"enabled": True})
    task_server.handle_set_autonomy(h)
    assert h.status == 200 and h.json() == {"ok": True, "enabled": True}
    assert profile_lib.autonomy_enforcement() is True

    h = _FakeHandler({"enabled": False})
    task_server.handle_set_autonomy(h)
    assert h.json() == {"ok": True, "enabled": False}
    assert profile_lib.autonomy_enforcement() is False


def test_set_autonomy_bad_body_is_400(srv):
    task_server, _, _, _ = srv
    h = _FakeHandler()
    # malformed JSON body
    h._body = b"{not json"
    h.headers = {"Content-Length": str(len(h._body))}
    task_server.handle_set_autonomy(h)
    assert h.status == 400


def test_set_autonomy_missing_enabled_is_400(srv):
    task_server, _, _, _ = srv
    # no 'enabled' key — must not silently coerce to disabled
    h = _FakeHandler({})
    task_server.handle_set_autonomy(h)
    assert h.status == 400


def test_set_autonomy_non_bool_enabled_is_400(srv):
    task_server, _, _, _ = srv
    # truthy-string 'enabled' is not a bool — reject rather than coerce
    h = _FakeHandler({"enabled": "yes"})
    task_server.handle_set_autonomy(h)
    assert h.status == 400


# ── kill-switch demote ──────────────────────────────────────────────────────

def test_demote_kills_to_supervised(srv):
    task_server, _, ladder_lib, _ = srv
    ladder_lib.set_tier("send-message", "autonomous")  # wrapper injects path=ladder_path
    h = _FakeHandler()
    task_server.handle_demote(h, "send-message")
    assert h.status == 200
    assert h.json() == {"ok": True, "task_type": "send-message", "tier": "supervised"}
    assert ladder_lib.tier_of("send-message") == "supervised"


def test_demote_missing_task_type_is_400(srv):
    task_server, _, _, _ = srv
    h = _FakeHandler()
    task_server.handle_demote(h, "")
    assert h.status == 400
