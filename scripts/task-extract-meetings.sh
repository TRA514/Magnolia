#!/usr/bin/env bash
# task-extract-meetings.sh — thin shim over task_extract_meetings.py.
# The real implementation is Python so the engine never shells Python->bash->python.
# This shim keeps the human CLI entrypoint and the docs working.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(command -v python3 || command -v python)"
if [ -z "$PYTHON" ]; then
  echo "task-extract-meetings.sh: no python3/python found on PATH" >&2
  exit 127
fi
exec "$PYTHON" "$SCRIPT_DIR/task_extract_meetings.py" "$@"
