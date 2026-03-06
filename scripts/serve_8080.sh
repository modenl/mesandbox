#!/bin/zsh
set -euo pipefail

REPO_ROOT="/Users/occ/work/mesimulation"
PYTHON_BIN="/usr/bin/python3"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd "$REPO_ROOT"
mkdir -p "$REPO_ROOT/data/logs"

exec "$PYTHON_BIN" -m war_sandbox.cli serve --port 8080
