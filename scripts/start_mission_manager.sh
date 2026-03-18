#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"
source_ros

cd "$ROOT_DIR"
echo "[INFO] Iniciando Mission Manager..."
ros2 launch anafi_mission_manager mission_manager.launch.py
