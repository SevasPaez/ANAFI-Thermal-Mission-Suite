#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"
source_ros

cd "$ROOT_DIR/app"
echo "[INFO] Iniciando GUI desde: $PWD"
python3 main.py
