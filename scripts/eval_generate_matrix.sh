#!/bin/sh
set -eu

CONFIG_PATH="${1:-config_server.yaml}"
API_BASE_URL="${2:-http://127.0.0.1:8000}"
EVAL_MODELS="${EVAL_MODELS:-qwen3.6:27b=qwen36_27b gemma4:31b=gemma4_31b gemma4:26b=gemma4_26b deepseek-r1:32b=deepseek_r1_32b mistral-small=mistral_small qwen3.5:9b=qwen35_9b qwen3.5:4b=qwen35_4b qwen3.5:2b=qwen35_2b}"
RERANK_TOP_K_VALUES="${RERANK_TOP_K_VALUES:-}"

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
  RERANK_TOP_K="${3:-}"

  if [ -n "$RERANK_TOP_K" ]; then
    echo "[$(date -Iseconds)] Generating predictions for model=$MODEL label=$LABEL rerank_top_k=$RERANK_TOP_K"
    PYTHONUNBUFFERED=1 python cli.py eval-generate \
      --config "$CONFIG_PATH" \
      --api-base-url "$API_BASE_URL" \
      --model "$MODEL" \
      --label "$LABEL" \
      --rerank-top-k "$RERANK_TOP_K"
  else
    echo "[$(date -Iseconds)] Generating predictions for model=$MODEL label=$LABEL"
    PYTHONUNBUFFERED=1 python cli.py eval-generate \
      --config "$CONFIG_PATH" \
      --api-base-url "$API_BASE_URL" \
      --model "$MODEL" \
      --label "$LABEL"
  fi
  echo "[$(date -Iseconds)] Finished predictions for model=$MODEL label=$LABEL"
}

for MODEL_SPEC in $EVAL_MODELS; do
  MODEL="${MODEL_SPEC%%=*}"
  BASE_LABEL="${MODEL_SPEC#*=}"

  if [ -n "$RERANK_TOP_K_VALUES" ]; then
    for RERANK_TOP_K in $RERANK_TOP_K_VALUES; do
      run_model "$MODEL" "${BASE_LABEL}_rerank${RERANK_TOP_K}" "$RERANK_TOP_K"
    done
  else
    run_model "$MODEL" "$BASE_LABEL"
  fi
done

echo "[$(date -Iseconds)] Finished eval-generate matrix with config=$CONFIG_PATH api_base_url=$API_BASE_URL"
