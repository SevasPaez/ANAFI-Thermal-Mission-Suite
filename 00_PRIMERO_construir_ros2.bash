#!/usr/bin/env bash
set -eo pipefail

cd "$(dirname "$0")"

set +u
export AMENT_TRACE_SETUP_FILES=""
source /opt/ros/humble/setup.bash
set +u

cd ros2_ws
colcon build
