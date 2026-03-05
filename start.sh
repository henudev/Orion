#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${ORION_PORT:-16926}"
HOST="${ORION_HOST:-0.0.0.0}"
export ORION_HOME="${ORION_HOME:-$ROOT_DIR/.orion}"

if [[ -x "$ROOT_DIR/.venv311/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv311/bin/python"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  echo "未找到可用虚拟环境，请先创建 .venv311 或 .venv 并安装依赖。"
  exit 1
fi

if command -v lsof >/dev/null 2>&1; then
  EXISTING_PID="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN | head -n 1 || true)"
  if [[ -n "$EXISTING_PID" ]]; then
    echo "端口 $PORT 已被占用（PID: $EXISTING_PID），请先停止占用进程后重试。"
    exit 1
  fi
fi

cd "$ROOT_DIR"
echo "Orion 启动中..."
echo "ROOT_DIR=$ROOT_DIR"
echo "ORION_HOME=$ORION_HOME"
echo "URL=http://127.0.0.1:$PORT"

exec "$PYTHON_BIN" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
