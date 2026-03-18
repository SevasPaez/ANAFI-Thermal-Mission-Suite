#!/usr/bin/env bash
set -eo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ANAFI_SUITE_ROOT="$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/app:$ROOT_DIR/ros2_ws/src/anafi_suite_core:${PYTHONPATH:-}"
mkdir -p "$ROOT_DIR/runtime/logs"

source_ros() {
  if [[ ! -f "/opt/ros/humble/setup.bash" ]]; then
    echo "[ERROR] No encontré /opt/ros/humble/setup.bash"
    echo "        Instala ROS2 Humble o ajusta el script si usas otra distro."
    exit 1
  fi

  set +u
  export AMENT_TRACE_SETUP_FILES=""
  source /opt/ros/humble/setup.bash

  if [[ -f "$ROOT_DIR/ros2_ws/install/setup.bash" ]]; then
    source "$ROOT_DIR/ros2_ws/install/setup.bash"
  fi
}
