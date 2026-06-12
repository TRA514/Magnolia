"""Portability gate - a dumb-fast denylist scan over runtime code.

Enforces the OS/shell portability seam ONLY: the WinError-193 crash class - direct
.sh/bash invocation, OS branches outside platform_lib, and start_new_session=. Scans
CODE only (.py/.js). ASCII-safe runtime output (em-dash and friends in generated text)
is handled as loop discipline, not by this gate.

The OS seam is scripts/platform_lib.py - it is allowlisted (it legitimately branches
on OS so the rest of the engine never has to). This gate file is allowlisted too,
since it necessarily contains the very patterns it hunts.
"""
import os, re, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEAM = os.path.join(ROOT, "scripts", "platform_lib.py")
GATE = os.path.join(ROOT, "scripts", "portability_gate.py")

# Matches the bare-script and list-invocation shapes (["bash", ...], run("x.sh"),
# f-strings ending in .sh) - the shapes the observed WinError-193 leaks took.
# Script-with-args inside one string (run("x.sh foo")) is intentionally out of
# scope to stay false-positive-free.
# (pattern, label) - each flags one leak class.
RULES = [
    (re.compile(r"\bstart_new_session\s*="),       "start_new_session= (use platform_lib.process_group_kwargs())"),
    (re.compile(r"os\.name\s*==\s*['\"]nt['\"]"),  "os.name=='nt' platform branch (route through platform_lib)"),
    (re.compile(r"sys\.platform"),                 "sys.platform branch (route through platform_lib.os_kind())"),
    (re.compile(r"""\[\s*["']bash["']"""),         "direct bash invocation of a shell script (call Python via sys.executable)"),
    (re.compile(r"""["'][^"']*\.sh["']"""),        "invoking a .sh shell script (port to Python; .sh is non-portable)"),
]


def _targets():
    return sorted(
        f for f in (
            glob.glob(os.path.join(ROOT, "scripts", "**", "*.py"), recursive=True) +
            glob.glob(os.path.join(ROOT, "ui", "task-board", "js", "**", "*.js"), recursive=True)
        )
        if os.path.abspath(f) not in (os.path.abspath(SEAM), os.path.abspath(GATE))
        and "__pycache__" not in f
        and os.path.sep + "tests" + os.path.sep not in f
    )


def scan(paths):
    offenders = []
    for f in paths:
        try:
            text = open(f, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for rx, label in RULES:
            if rx.search(text):
                offenders.append(f"{os.path.relpath(f, ROOT)}: {label}")
    return offenders


def validate():
    return scan(_targets())


if __name__ == "__main__":
    import sys
    errs = validate()
    if errs:
        print("\n".join(errs)); sys.exit(1)
    print("portability OK")
