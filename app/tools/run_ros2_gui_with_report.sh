\

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

TS="$(date +"%Y-%m-%d_%H-%M-%S")"
LOG_FILE="$LOG_DIR/sesion_${TS}.log"
REPORT_FILE="$LOG_DIR/reporte_errores_${TS}.txt"

ROS_SETUP=""
WS_SETUP=""
LAUNCH_CMD=""
APP_CMD=""

while [[ $
  case "$1" in
    --ros)    ROS_SETUP="${2:-}"; shift 2;;
    --ws)     WS_SETUP="${2:-}"; shift 2;;
    --launch) LAUNCH_CMD="${2:-}"; shift 2;;
    --cmd)    APP_CMD="${2:-}"; shift 2;;
    -h|--help) sed -n '1,100p' "$0"; exit 0;;
    *) echo "[run] Argumento desconocido: $1"; echo "      Usa --help"; exit 2;;
  esac
done

if [[ -z "$APP_CMD" ]]; then
  if [[ -f "$PROJECT_DIR/main.py" ]]; then
    APP_CMD="python3 main.py"
  else
    APP_CMD="python3 -m interfaz.app_shell"
  fi
fi

echo "[run] Proyecto    : $PROJECT_DIR"
echo "[run] Log completo: $LOG_FILE"
echo "[run] Reporte     : $REPORT_FILE"
echo "[run] App cmd     : $APP_CMD"
if [[ -n "$LAUNCH_CMD" ]]; then
  echo "[run] ROS2 launch : $LAUNCH_CMD"
fi
echo

(
  cd "$PROJECT_DIR"

  if [[ -n "$ROS_SETUP" ]]; then
    if [[ -f "$ROS_SETUP" ]]; then

      source "$ROS_SETUP"
      echo "[run] source ROS: $ROS_SETUP"
    else
      echo "[run][WARN] No existe ROS setup: $ROS_SETUP"
    fi
  fi

  if [[ -n "$WS_SETUP" ]]; then
    if [[ -f "$WS_SETUP" ]]; then

      source "$WS_SETUP"
      echo "[run] source WS : $WS_SETUP"
    else
      echo "[run][WARN] No existe WS setup: $WS_SETUP"
    fi
  fi

  ROS_PID=""
  cleanup() {
    if [[ -n "${ROS_PID:-}" ]]; then
      echo "[run] Deteniendo ros2 launch (pid=$ROS_PID)..."
      kill "$ROS_PID" 2>/dev/null || true
      wait "$ROS_PID" 2>/dev/null || true
    fi
  }
  trap cleanup EXIT INT TERM

  if [[ -n "$LAUNCH_CMD" ]]; then
    echo "[run] Iniciando ros2 launch..."
    eval "$LAUNCH_CMD" &
    ROS_PID=$!
    echo "[run] ros2 launch pid=$ROS_PID"
    sleep 1
  fi

  echo "[run] Iniciando GUI..."
  eval "$APP_CMD"
) 2>&1 | tee "$LOG_FILE"

RC=${PIPESTATUS[0]}

{
  echo "REPORTE DE ERRORES (terminal)"
  echo "============================================================"
  echo "Fecha: $TS"
  echo "Log  : $LOG_FILE"
  echo "Exit : $RC"
  echo
  echo "Coincidencias (ERROR/FATAL/Traceback/OpenCV error):"
  echo "------------------------------------------------------------"
  grep -nE "ERROR|FATAL|Traceback|Exception|OpenCV\\([0-9.]+\\).*(error|Error)" "$LOG_FILE" || true
} > "$REPORT_FILE"

echo
echo "[run] Listo."
echo "      Log    : $LOG_FILE"
echo "      Reporte: $REPORT_FILE"
exit "$RC"
