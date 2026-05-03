#!/bin/sh
set -eu

CONFIG_PATH="${1:-evaluation/configs/eval_matrix_qwen35.yaml}"

LOG_DIR="/app/storage/eval_logs"
LOG_PATH="$LOG_DIR/eval_matrix_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval matrix with config=$CONFIG_PATH"

PYTHONUNBUFFERED=1 python cli.py eval \
  --config "$CONFIG_PATH"

echo "[$(date -Iseconds)] Finished eval matrix with config=$CONFIG_PATH"
