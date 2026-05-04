#!/bin/sh
set -eu

CONFIG_PATH="${1:-config_server.yaml}"
EVAL_LABELS="${EVAL_LABELS:-qwen35_2b qwen35_4b qwen35_9b}"
RERANK_TOP_K_VALUES="${RERANK_TOP_K_VALUES:-}"

LOG_DIR="/app/storage/eval_logs"
LOG_PATH="$LOG_DIR/eval_score_matrix_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval-score matrix with config=$CONFIG_PATH"

resolve_latest_prediction() {
  LABEL="$1"
  ls -1t "/app/storage/eval_predictions"/eval_predictions_"$LABEL"_*.json 2>/dev/null | head -n 1
}

preflight_label() {
  LABEL="$1"
  PREDICTIONS_PATH=$(resolve_latest_prediction "$LABEL")
  if [ -z "${PREDICTIONS_PATH:-}" ]; then
    echo "[FAIL] No prediction artifact found for label: $LABEL" >&2
    exit 1
  fi

  echo "[$(date -Iseconds)] Preflight scoring inputs for label=$LABEL predictions=$PREDICTIONS_PATH"
  PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
    --mode score \
    --config "$CONFIG_PATH" \
    --predictions "$PREDICTIONS_PATH"
}

run_label() {
  LABEL="$1"

  echo "[$(date -Iseconds)] Scoring latest predictions for label=$LABEL"
  PYTHONUNBUFFERED=1 sh /app/scripts/eval_score.sh --latest "$LABEL" "$CONFIG_PATH"
  echo "[$(date -Iseconds)] Finished scoring latest predictions for label=$LABEL"
}

for BASE_LABEL in $EVAL_LABELS; do
  if [ -n "$RERANK_TOP_K_VALUES" ]; then
    for RERANK_TOP_K in $RERANK_TOP_K_VALUES; do
      LABEL="${BASE_LABEL}_rerank${RERANK_TOP_K}"
      preflight_label "$LABEL"
      run_label "$LABEL"
    done
  else
    preflight_label "$BASE_LABEL"
    run_label "$BASE_LABEL"
  fi
done

echo "[$(date -Iseconds)] Finished eval-score matrix with config=$CONFIG_PATH"
