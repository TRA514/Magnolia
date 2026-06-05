"""Reboot-persistence for the task server.

macOS: per-user LaunchAgent (RunAtLoad + KeepAlive) — RUN-VALIDATED.
Windows: Task Scheduler at logon — DESIGN-VALIDATED ONLY (no Windows box).
Same install()/remove()/is_installed() API on both via platform_lib.
"""
import os
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_lib  # noqa: E402

LABEL = "com.pm-os.task-server"


def render_launchagent(label, program, working_dir, log_path):
    args = "\n".join(f"        <string>{escape(a)}</string>" for a in program)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{escape(label)}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>WorkingDirectory</key>
    <string>{escape(working_dir)}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{escape(log_path)}</string>
    <key>StandardErrorPath</key>
    <string>{escape(log_path)}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
"""


def render_scheduled_task(name, program, args, working_dir):
    """Return a PowerShell snippet registering a per-user at-logon task.

    DESIGN-VALIDATED ONLY — not executed/verified on Windows.
    Per-user (no -RunLevel Highest) so it needs no admin/UAC and runs in the
    user's context (can read their files/creds).
    """
    return (
        f'$action = New-ScheduledTaskAction -Execute "{program}" '
        f'-Argument "{args}" -WorkingDirectory "{working_dir}"\n'
        f'$trigger = New-ScheduledTaskTrigger -AtLogOn\n'
        f'$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)\n'
        f'Register-ScheduledTask -TaskName "{name}" -Action $action '
        f'-Trigger $trigger -Settings $settings -Force\n'
    )
