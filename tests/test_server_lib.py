import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import server_lib


def test_url_uses_port(monkeypatch):
    monkeypatch.setattr(server_lib.profile_lib, "server_port", lambda root=None: 8755)
    assert server_lib.url() == "http://localhost:8755"


def test_free_port_returns_unused():
    p = server_lib.free_port()
    # we can bind it → it was free
    s = socket.socket()
    s.bind(("127.0.0.1", p))
    s.close()


def test_is_running_true_when_api_serves():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"[]")
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        assert server_lib.is_running(port=port) is True
    finally:
        srv.shutdown()


def test_is_running_false_when_nothing_listens():
    assert server_lib.is_running(port=59997) is False


import sys as _sys


def test_start_polls_until_serving(tmp_path):
    # a tiny server script that serves /api/tasks 200 on argv[1]
    script = tmp_path / "tiny.py"
    script.write_text(
        "import sys\n"
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200); self.end_headers(); self.wfile.write(b'[]')\n"
        "    def log_message(self,*a): pass\n"
        "HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n"
    )
    p = server_lib.free_port()
    proc = server_lib.start(port=p, cmd=[_sys.executable, str(script), str(p)], timeout=5.0)
    try:
        assert server_lib.is_running(port=p) is True
    finally:
        proc.terminate()


def test_start_raises_if_never_serves():
    p = server_lib.free_port()
    import pytest
    with pytest.raises(TimeoutError):
        # 'true' exits immediately, never serves
        server_lib.start(port=p, cmd=["true"], timeout=1.5)
