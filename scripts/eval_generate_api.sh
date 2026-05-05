#!/bin/sh
set -eu

MODEL="${1:-}"
LABEL="${2:-}"
CONFIG_PATH="${3:-config_server.yaml}"
API_BASE_URL="${4:-http://127.0.0.1:8000}"
OUTPUT_PATH="${5:-}"

if [ -z "$MODEL" ]; then
  echo "Usage: sh /app/scripts/eval_generate_api.sh <model> [label] [config_path] [api_base_url]"
  echo "       sh /app/scripts/eval_generate_api.sh <model> [label] [config_path] [api_base_url] [output_path]"
  exit 1
fi

if [ -z "$LABEL" ]; then
  LABEL=$(printf '%s' "$MODEL" | tr ':/' '__')
fi

LOG_DIR="/app/storage/eval_logs"
LOG_PATH="$LOG_DIR/eval_generate_${LABEL}.log"

mkdir -p "$LOG_DIR"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval-generate for model=$MODEL label=$LABEL"
echo "Config: $CONFIG_PATH"
echo "API base URL: $API_BASE_URL"

PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
  --mode generate \
  --config "$CONFIG_PATH" \
  --api-base-url "$API_BASE_URL"

if [ -n "$OUTPUT_PATH" ]; then
  PYTHONUNBUFFERED=1 python cli.py eval-generate \
    --config "$CONFIG_PATH" \
    --api-base-url "$API_BASE_URL" \
    --model "$MODEL" \
    --label "$LABEL" \
    --output "$OUTPUT_PATH"
else
  PYTHONUNBUFFERED=1 python cli.py eval-generate \
    --config "$CONFIG_PATH" \
    --api-base-url "$API_BASE_URL" \
    --model "$MODEL" \
    --label "$LABEL"
fi

echo "[$(date -Iseconds)] Finished eval-generate for model=$MODEL label=$LABEL"
