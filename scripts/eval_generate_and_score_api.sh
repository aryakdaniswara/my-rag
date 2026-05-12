#!/bin/sh
set -eu

MODEL="${1:-}"
LABEL="${2:-}"
CONFIG_PATH="${3:-evaluation/configs/singles/generation_v4_rerank8.yaml}"
API_BASE_URL="${4:-http://127.0.0.1:8000}"
RUN_NAME="${RUN_NAME:-eval_generate_and_score_$(date +%Y%m%d_%H%M%S)}"
RUN_ROOT="${RUN_ROOT:-/app/storage/eval_runs/$RUN_NAME}"
GENERATE_RUN_DIR="${GENERATE_RUN_DIR:-$RUN_ROOT/generate}"
SCORE_RUN_DIR="${SCORE_RUN_DIR:-$RUN_ROOT/score}"

if [ -z "$MODEL" ]; then
  echo "Usage: sh /app/scripts/eval_generate_and_score_api.sh <model> [label] [config_path] [api_base_url]"
  exit 1
fi

if [ -z "$LABEL" ]; then
  LABEL=$(printf '%s' "$MODEL" | tr ':/' '__')
fi

mkdir -p "$RUN_ROOT"

echo "[$(date -Iseconds)] Starting chained generate->score run"
echo "Model: $MODEL"
echo "Label: $LABEL"
echo "Config: $CONFIG_PATH"
echo "API base URL: $API_BASE_URL"
echo "Run root: $RUN_ROOT"
echo "Generate run dir: $GENERATE_RUN_DIR"
echo "Score run dir: $SCORE_RUN_DIR"

RUN_DIR="$GENERATE_RUN_DIR" \
  sh /app/scripts/eval_generate_api.sh "$MODEL" "$LABEL" "$CONFIG_PATH" "$API_BASE_URL"

RUN_DIR="$SCORE_RUN_DIR" \
  sh /app/scripts/eval_score.sh --latest "$LABEL" "$CONFIG_PATH"

echo "[$(date -Iseconds)] Finished chained generate->score run"
