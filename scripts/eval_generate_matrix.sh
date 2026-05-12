#!/bin/sh
set -eu

CONFIG_PATH="${1:-evaluation/configs/matrices/generation_rerank8.yaml}"
API_BASE_URL="${2:-http://127.0.0.1:8000}"
RERANK_TOP_K_VALUES="${RERANK_TOP_K_VALUES:-}"
RUN_NAME="${RUN_NAME:-eval_generate_matrix_$(date +%Y%m%d_%H%M%S)}"
RUN_DIR="${RUN_DIR:-/app/storage/eval_runs/$RUN_NAME}"
EVAL_GENERATE_STREAM="${EVAL_GENERATE_STREAM:-true}"
EVAL_SHOW_ANSWERS="${EVAL_SHOW_ANSWERS:-true}"

if [ -n "${EVAL_MODELS:-}" ]; then
  EVAL_MODEL_SPECS="$EVAL_MODELS"
else
  EVAL_MODEL_SPECS=$(
    python /app/scripts/eval_preflight.py \
      --mode generate \
      --config "$CONFIG_PATH" \
      --emit-model-specs
  )
fi

mkdir -p "$RUN_DIR/logs"
LOG_PATH="$RUN_DIR/logs/eval-generate-matrix.log"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval-generate matrix config=$CONFIG_PATH api_base_url=$API_BASE_URL"
echo "Run dir: $RUN_DIR"
echo "Stream generation: $EVAL_GENERATE_STREAM"
echo "Show answers: $EVAL_SHOW_ANSWERS"

PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
  --mode generate \
  --config "$CONFIG_PATH" \
  --api-base-url "$API_BASE_URL" \
  --model-specs "$EVAL_MODEL_SPECS" \
  --run-dir "$RUN_DIR"

run_model() {
  MODEL="$1"
  LABEL="$2"
  RERANK_TOP_K="${3:-}"
  EXTRA_ARGS=""
  if [ "$EVAL_GENERATE_STREAM" = "true" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --stream"
  fi
  if [ "$EVAL_SHOW_ANSWERS" = "true" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --show-answers"
  fi

  if [ -n "$RERANK_TOP_K" ]; then
    echo "[$(date -Iseconds)] Generating predictions model=$MODEL label=$LABEL rerank_top_k=$RERANK_TOP_K"
    # shellcheck disable=SC2086
    PYTHONUNBUFFERED=1 python cli.py eval-generate \
      --config "$CONFIG_PATH" \
      --api-base-url "$API_BASE_URL" \
      --model "$MODEL" \
      --label "$LABEL" \
      --rerank-top-k "$RERANK_TOP_K" \
      --run-dir "$RUN_DIR" \
      $EXTRA_ARGS
  else
    echo "[$(date -Iseconds)] Generating predictions model=$MODEL label=$LABEL"
    # shellcheck disable=SC2086
    PYTHONUNBUFFERED=1 python cli.py eval-generate \
      --config "$CONFIG_PATH" \
      --api-base-url "$API_BASE_URL" \
      --model "$MODEL" \
      --label "$LABEL" \
      --run-dir "$RUN_DIR" \
      $EXTRA_ARGS
  fi
  echo "[$(date -Iseconds)] Finished predictions model=$MODEL label=$LABEL"
}

for MODEL_SPEC in $EVAL_MODEL_SPECS; do
  SPEC_RERANK_TOP_K=""
  case "$MODEL_SPEC" in
    *"|"*)
      MODEL="${MODEL_SPEC%%|*}"
      REST="${MODEL_SPEC#*|}"
      BASE_LABEL="${REST%%|*}"
      SPEC_RERANK_TOP_K="${REST#*|}"
      if [ "$SPEC_RERANK_TOP_K" = "-" ]; then
        SPEC_RERANK_TOP_K=""
      fi
      ;;
    *=*)
      MODEL="${MODEL_SPEC%%=*}"
      BASE_LABEL="${MODEL_SPEC#*=}"
      ;;
    *)
      MODEL="$MODEL_SPEC"
      BASE_LABEL="$MODEL_SPEC"
      ;;
  esac

  if [ -n "$RERANK_TOP_K_VALUES" ]; then
    for RERANK_TOP_K in $RERANK_TOP_K_VALUES; do
      run_model "$MODEL" "${BASE_LABEL}_rerank${RERANK_TOP_K}" "$RERANK_TOP_K"
    done
  elif [ -n "$SPEC_RERANK_TOP_K" ]; then
    run_model "$MODEL" "$BASE_LABEL" "$SPEC_RERANK_TOP_K"
  else
    run_model "$MODEL" "$BASE_LABEL"
  fi
done

echo "[$(date -Iseconds)] Finished eval-generate matrix config=$CONFIG_PATH api_base_url=$API_BASE_URL"
