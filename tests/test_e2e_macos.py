import os
import shutil
import sys

import pytest

import platform_lib
import doctor
import server_lib

pytestmark = pytest.mark.skipif(platform_lib.os_kind() != "darwin",
                                reason="e2e is run-validated on macOS only")


def test_detect_then_serve(tmp_path):
    # build a real profile from the example template
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shutil.copytree(os.path.join(repo, "profile.example"), tmp_path / "profile")
    (tmp_path / "profile" / "integrations.yaml").write_text("transcript:\n  provider: none\n")

    caps = doctor.detect(root=str(tmp_path))
    assert caps["platform"] == "darwin"
    assert "server" in caps["capabilities"]

    # start a trivial server on a free port and confirm the lifecycle primitives work
    p = server_lib.free_port()
    script = tmp_path / "tiny.py"
    script.write_text(
        "import sys\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b'[]')\n"
        "    def log_message(self,*a): pass\n"
        "HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n"
    )
    proc = server_lib.start(port=p, cmd=[sys.executable, str(script), str(p)], timeout=5.0)
    try:
        assert server_lib.is_running(port=p)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except Exception:
            proc.kill()
