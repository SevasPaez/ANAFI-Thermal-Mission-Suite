#!/usr/bin/env bash
set -eo pipefail
bash "$(cd "$(dirname "$0")" && pwd)/scripts/start_gui.sh"
