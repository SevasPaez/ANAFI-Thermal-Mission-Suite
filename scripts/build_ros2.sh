#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_common.sh"
source_ros

cd "$ROOT_DIR/ros2_ws"
echo "[INFO] Construyendo workspace ROS2 en: $PWD"
colcon build
