#!/usr/bin/env bash
set -eo pipefail
bash "$(cd "$(dirname "$0")" && pwd)/scripts/start_mission_manager.sh"
