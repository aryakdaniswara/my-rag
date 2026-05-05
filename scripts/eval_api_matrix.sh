#!/bin/sh
set -eu

CONFIG_PATH="${1:-config_server.yaml}"
API_BASE_URL="${2:-http://127.0.0.1:8000}"
EVAL_MODELS="${EVAL_MODELS:-qwen3.6:27b=qwen36_27b gemma4:31b=gemma4_31b gemma4:26b=gemma4_26b deepseek-r1:32b=deepseek_r1_32b mistral-small=mistral_small qwen3.5:9b=qwen35_9b qwen3.5:4b=qwen35_4b qwen3.5:2b=qwen35_2b}"
RERANK_TOP_K_VALUES="${RERANK_TOP_K_VALUES:-}"
RUN_NAME="${RUN_NAME:-eval_api_matrix_$(date +%Y%m%d_%H%M%S)}"

LOG_DIR="/app/storage/eval_logs"
PREDICTION_RUN_DIR="/app/storage/eval_predictions/$RUN_NAME"
RESULT_RUN_DIR="/app/storage/eval_results/$RUN_NAME"
LOG_PATH="$LOG_DIR/${RUN_NAME}.log"

mkdir -p "$LOG_DIR" "$PREDICTION_RUN_DIR" "$RESULT_RUN_DIR"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting API eval matrix run_name=$RUN_NAME config=$CONFIG_PATH api_base_url=$API_BASE_URL"
echo "Prediction dir: $PREDICTION_RUN_DIR"
echo "Result dir: $RESULT_RUN_DIR"

PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
  --mode generate \
  --config "$CONFIG_PATH" \
  --api-base-url "$API_BASE_URL"

run_model() {
  MODEL="$1"
  LABEL="$2"
  RERANK_TOP_K="${3:-}"
  PREDICTION_PATH="$PREDICTION_RUN_DIR/eval_prediction_${LABEL}.json"
  SCORE_PATH="$RESULT_RUN_DIR/eval_score_${LABEL}.json"

  if [ -n "$RERANK_TOP_K" ]; then
    echo "[$(date -Iseconds)] Generating and scoring model=$MODEL label=$LABEL rerank_top_k=$RERANK_TOP_K"
    PYTHONUNBUFFERED=1 python cli.py eval-generate \
      --config "$CONFIG_PATH" \
      --api-base-url "$API_BASE_URL" \
      --model "$MODEL" \
      --label "$LABEL" \
      --rerank-top-k "$RERANK_TOP_K" \
      --output "$PREDICTION_PATH"
  else
    echo "[$(date -Iseconds)] Generating and scoring model=$MODEL label=$LABEL"
    PYTHONUNBUFFERED=1 python cli.py eval-generate \
      --config "$CONFIG_PATH" \
      --api-base-url "$API_BASE_URL" \
      --model "$MODEL" \
      --label "$LABEL" \
      --output "$PREDICTION_PATH"
  fi

  PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
    --mode score \
    --config "$CONFIG_PATH" \
    --predictions "$PREDICTION_PATH"

  PYTHONUNBUFFERED=1 python cli.py eval-score \
    --config "$CONFIG_PATH" \
    --predictions "$PREDICTION_PATH" \
    --output "$SCORE_PATH"

  echo "[$(date -Iseconds)] Finished model=$MODEL label=$LABEL predictions=$PREDICTION_PATH score=$SCORE_PATH"
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

echo "[$(date -Iseconds)] Finished API eval matrix run_name=$RUN_NAME"
