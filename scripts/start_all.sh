#!/usr/bin/env bash
set -eo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/runtime/logs"
mkdir -p "$LOG_DIR"

TS="$(date +"%Y%m%d_%H%M%S")"
MM_LOG="$LOG_DIR/mission_manager_${TS}.log"

echo "[INFO] ROOT_DIR=$ROOT_DIR"
echo "[INFO] Abriendo Mission Manager en segundo plano..."
bash "$ROOT_DIR/01_iniciar_mission_manager.bash" > "$MM_LOG" 2>&1 &
MM_PID=$!

sleep 3

echo "[INFO] Mission Manager PID: $MM_PID"
echo "[INFO] Log Mission Manager: $MM_LOG"
echo "[INFO] Abriendo GUI..."
bash "$ROOT_DIR/02_iniciar_gui.bash"

echo "[INFO] La GUI terminó. Cerrando Mission Manager..."
kill "$MM_PID" 2>/dev/null || true
wait "$MM_PID" 2>/dev/null || true
