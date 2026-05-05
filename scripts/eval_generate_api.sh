#!/bin/sh
set -eu

MODEL="${1:-}"
LABEL="${2:-}"
CONFIG_PATH="${3:-config_server.yaml}"
API_BASE_URL="${4:-http://127.0.0.1:8000}"
OUTPUT_PATH="${5:-}"
RUN_NAME="${RUN_NAME:-eval_generate_$(date +%Y%m%d_%H%M%S)}"
RUN_DIR="${RUN_DIR:-/app/storage/eval_runs/$RUN_NAME}"

if [ -z "$MODEL" ]; then
  echo "Usage: sh /app/scripts/eval_generate_api.sh <model> [label] [config_path] [api_base_url] [output_path]"
  exit 1
fi

if [ -z "$LABEL" ]; then
  LABEL=$(printf '%s' "$MODEL" | tr ':/' '__')
fi

mkdir -p "$RUN_DIR/logs"
LOG_PATH="$RUN_DIR/logs/eval-generate__${LABEL}.log"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval-generate model=$MODEL label=$LABEL"
echo "Config: $CONFIG_PATH"
echo "API base URL: $API_BASE_URL"
echo "Run dir: $RUN_DIR"

PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
  --mode generate \
  --config "$CONFIG_PATH" \
  --api-base-url "$API_BASE_URL" \
  --run-dir "$RUN_DIR"

if [ -n "$OUTPUT_PATH" ]; then
  PYTHONUNBUFFERED=1 python cli.py eval-generate \
    --config "$CONFIG_PATH" \
    --api-base-url "$API_BASE_URL" \
    --model "$MODEL" \
    --label "$LABEL" \
    --run-dir "$RUN_DIR" \
    --output "$OUTPUT_PATH"
else
  PYTHONUNBUFFERED=1 python cli.py eval-generate \
    --config "$CONFIG_PATH" \
    --api-base-url "$API_BASE_URL" \
    --model "$MODEL" \
    --label "$LABEL" \
    --run-dir "$RUN_DIR"
fi

echo "[$(date -Iseconds)] Finished eval-generate model=$MODEL label=$LABEL"
