#!/bin/zsh
set -euo pipefail

REPO_ROOT="/Users/occ/work/mesimulation"
PYTHON_BIN="/usr/bin/python3"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd "$REPO_ROOT"
mkdir -p "$REPO_ROOT/data/logs"

exec "$PYTHON_BIN" -m http.server 8080 --bind 127.0.0.1 --directory "$REPO_ROOT/docs"
