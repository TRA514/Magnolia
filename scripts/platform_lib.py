"""The single OS-abstraction seam for Magnolia.

Everything platform-specific (package managers, persistence mechanisms, opening
a URL) funnels through here so the rest of the engine stays platform-blind.

macOS is run-validated on the dev machine. Windows branches are written and
unit-tested against a mocked os_kind() but are DESIGN-VALIDATED, NOT
RUN-VALIDATED (no Windows box available).
"""
import os
import platform
import shutil
import signal
import subprocess


def os_kind():
    sysname = platform.system().lower()
    if sysname.startswith("darwin"):
        return "darwin"
    if sysname.startswith("windows"):
        return "windows"
    return "linux"


def open_url_cmd(url):
    kind = os_kind()
    if kind == "darwin":
        return ["open", url]
    if kind == "windows":
        # empty "" is the title arg for start; required when URL is quoted
        return ["cmd", "/c", "start", "", url]
    return ["xdg-open", url]


def open_url(url):
    subprocess.Popen(open_url_cmd(url))


# winget IDs differ from brew names; map the ones the Doctor installs.
_WINGET_IDS = {
    "pandoc": "pandoc",
    "qmd": "qmd",            # placeholder — verify real winget id during impl
    "fswatch": "",           # no winget equivalent; "" → package_install_cmd returns None
}


def package_install_cmd(name):
    kind = os_kind()
    if kind == "windows":
        wid = _WINGET_IDS.get(name, name)
        if not wid:
            # documented no-equivalent case (e.g. fswatch): signal "unsupported on
            # this OS" the same way launch_agents_dir() returns None, rather than
            # emitting a broken `winget install --id "" -e` command.
            return None
        return ["winget", "install", "--id", wid, "-e"]
    # darwin/linux both use brew in this engine's supported setups
    return ["brew", "install", name]


def launch_agents_dir():
    if os_kind() == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
    return None  # Windows uses Task Scheduler (no directory); Linux unsupported for persistence v1


# POSIX install locations to prefer ahead of the inherited PATH.
_CLAUDE_PREPEND_DIRS = [
    os.path.join(os.path.expanduser("~"), ".local", "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
]


def headless_claude_env(base=None):
    """Env for a headless `claude` subprocess, cross-platform.

    Strips CLAUDE*/CMUX_CLAUDE* (avoid nested-session detection). On POSIX,
    prepends common claude install dirs that actually exist. On Windows the
    inherited PATH is kept verbatim (claude resolves via shutil.which/PATHEXT) —
    never inject unix dirs or ':'-join onto a ';'-separated PATH.
    """
    src = os.environ if base is None else base
    env = {k: v for k, v in src.items()
           if not k.startswith(("CLAUDE", "CMUX_CLAUDE"))}
    cur = env.get("PATH", os.defpath)
    if os_kind() != "windows":
        prepend = [d for d in _CLAUDE_PREPEND_DIRS if os.path.isdir(d)]
        if prepend:
            env["PATH"] = os.pathsep.join(prepend + [cur])
    return env


def resolve_claude(path=None):
    """Absolute path to the claude CLI, or the bare name as a last resort.

    shutil.which honors PATHEXT on Windows (finds claude.exe / claude.cmd).
    """
    found = shutil.which("claude", path=path)
    if found:
        return found
    for d in _CLAUDE_PREPEND_DIRS:
        cand = os.path.join(d, "claude")
        if os.path.isfile(cand):
            return cand
    return "claude"


def process_group_kwargs():
    """Popen kwargs giving the child its own killable process group."""
    if os_kind() == "windows":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)}
    return {"start_new_session": True}


def kill_process_group(proc):
    """Best-effort kill of a child and its group, cross-platform."""
    try:
        if os_kind() == "windows":
            proc.terminate()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
