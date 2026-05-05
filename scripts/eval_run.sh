#!/bin/sh
set -eu

CONFIG_PATH="${1:-evaluation/configs/eval_judge_local_qwen36.yaml}"
RUN_NAME="${RUN_NAME:-eval_run_$(date +%Y%m%d_%H%M%S)}"
RUN_DIR="${RUN_DIR:-/app/storage/eval_runs/$RUN_NAME}"

mkdir -p "$RUN_DIR/logs"
LOG_PATH="$RUN_DIR/logs/eval-run.log"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting full eval run config=$CONFIG_PATH"
echo "Run dir: $RUN_DIR"

PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
  --mode full \
  --config "$CONFIG_PATH" \
  --run-dir "$RUN_DIR"

PYTHONUNBUFFERED=1 python cli.py eval \
  --config "$CONFIG_PATH" \
  --run-dir "$RUN_DIR"

echo "[$(date -Iseconds)] Finished full eval run config=$CONFIG_PATH"
