#!/bin/sh
set -eu

CONFIG_PATH="${1:-evaluation/configs/eval_base_api_judge.yaml}"
API_BASE_URL="${2:-http://127.0.0.1:8000}"

LOG_DIR="/app/storage/eval_logs"
LOG_PATH="$LOG_DIR/eval_generate_matrix_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval-generate matrix with config=$CONFIG_PATH api_base_url=$API_BASE_URL"

PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
  --mode generate \
  --config "$CONFIG_PATH" \
  --api-base-url "$API_BASE_URL"

run_model() {
  MODEL="$1"
  LABEL="$2"

  echo "[$(date -Iseconds)] Generating predictions for model=$MODEL label=$LABEL"
  PYTHONUNBUFFERED=1 python cli.py eval-generate \
    --config "$CONFIG_PATH" \
    --api-base-url "$API_BASE_URL" \
    --model "$MODEL" \
    --label "$LABEL"
  echo "[$(date -Iseconds)] Finished predictions for model=$MODEL label=$LABEL"
}

run_model "qwen3.5:2b" "qwen35_2b"
run_model "qwen3.5:4b" "qwen35_4b"
run_model "qwen3.5:9b" "qwen35_9b"

echo "[$(date -Iseconds)] Finished eval-generate matrix with config=$CONFIG_PATH api_base_url=$API_BASE_URL"
