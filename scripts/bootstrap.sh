#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo "This locked setup requires macOS Apple Silicon. See docs/换机开发指南.md for other platforms." >&2
  exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "Install uv first (on macOS: brew install uv)." >&2
  exit 1
fi
# UV may download a standalone Python if no compatible interpreter is available.
if [ ! -x .venv/bin/python ]; then
  uv venv --python 3.12 .venv
fi
uv pip sync --python .venv/bin/python requirements-macos-arm64.lock.txt
uv pip install --python .venv/bin/python --no-deps -e .
.venv/bin/catmeal prepare
.venv/bin/catmeal doctor --out outputs/environment.json
.venv/bin/python -m pytest -q
