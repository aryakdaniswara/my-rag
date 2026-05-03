#!/bin/sh
set -eu

CONFIG_PATH="${1:-evaluation/configs/eval_base_api_judge.yaml}"

LOG_DIR="/app/storage/eval_logs"
LOG_PATH="$LOG_DIR/eval_score_matrix_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval-score matrix with config=$CONFIG_PATH"

run_label() {
  LABEL="$1"

  echo "[$(date -Iseconds)] Scoring latest predictions for label=$LABEL"
  PYTHONUNBUFFERED=1 sh /app/scripts/eval_score.sh --latest "$LABEL" "$CONFIG_PATH"
  echo "[$(date -Iseconds)] Finished scoring latest predictions for label=$LABEL"
}

run_label "qwen35_2b"
run_label "qwen35_4b"
run_label "qwen35_9b"

echo "[$(date -Iseconds)] Finished eval-score matrix with config=$CONFIG_PATH"
