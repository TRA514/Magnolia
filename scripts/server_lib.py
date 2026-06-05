"""Server lifecycle primitives for the task board. Port-aware via profile config."""
import os
import socket
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_lib  # noqa: E402

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PM_OS_DIR = os.path.dirname(SCRIPT_DIR)


def port(root=None):
    return profile_lib.server_port(root)


def url(root=None):
    return f"http://localhost:{port(root)}"


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def is_running(port=None, root=None):
    p = port if port is not None else profile_lib.server_port(root)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{p}/api/tasks", timeout=1.0) as r:
            return r.status == 200
    except Exception:
        return False
