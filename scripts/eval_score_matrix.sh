#!/bin/sh
set -eu

CONFIG_PATH="${1:-evaluation/configs/eval_matrix_8models_rerank8.yaml}"
RERANK_TOP_K_VALUES="${RERANK_TOP_K_VALUES:-}"
RUN_NAME="${RUN_NAME:-eval_score_matrix_$(date +%Y%m%d_%H%M%S)}"
RUN_DIR="${RUN_DIR:-/app/storage/eval_runs/$RUN_NAME}"
EVAL_METRIC_PROFILE="${EVAL_METRIC_PROFILE:-generation}"

if [ -n "${EVAL_LABELS:-}" ]; then
  EVAL_SCORE_LABELS="$EVAL_LABELS"
else
  EVAL_SCORE_LABELS=$(
    python /app/scripts/eval_preflight.py \
      --mode score \
      --config "$CONFIG_PATH" \
      --emit-labels
  )
fi

mkdir -p "$RUN_DIR/logs"
LOG_PATH="$RUN_DIR/logs/eval-score-matrix.log"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval-score matrix config=$CONFIG_PATH"
echo "Run dir: $RUN_DIR"
echo "Metric profile: $EVAL_METRIC_PROFILE"

resolve_latest_prediction() {
  LABEL="$1"
  python cli.py eval-find-latest --config "$CONFIG_PATH" --label "$LABEL"
}

preflight_label() {
  LABEL="$1"
  PREDICTIONS_PATH=$(resolve_latest_prediction "$LABEL")
  if [ ! -f "$PREDICTIONS_PATH" ]; then
    echo "[FAIL] No prediction artifact found for label: $LABEL" >&2
    exit 1
  fi

  echo "[$(date -Iseconds)] Preflight score label=$LABEL predictions=$PREDICTIONS_PATH"
  PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
    --mode score \
    --config "$CONFIG_PATH" \
    --predictions "$PREDICTIONS_PATH" \
    --run-dir "$RUN_DIR"
}

for BASE_LABEL in $EVAL_SCORE_LABELS; do
  if [ -n "$RERANK_TOP_K_VALUES" ]; then
    for RERANK_TOP_K in $RERANK_TOP_K_VALUES; do
      LABEL="${BASE_LABEL}_rerank${RERANK_TOP_K}"
      preflight_label "$LABEL"
      echo "[$(date -Iseconds)] Scoring latest predictions label=$LABEL"
      RUN_DIR="$RUN_DIR" EVAL_METRIC_PROFILE="$EVAL_METRIC_PROFILE" PYTHONUNBUFFERED=1 sh /app/scripts/eval_score.sh --latest "$LABEL" "$CONFIG_PATH"
      echo "[$(date -Iseconds)] Finished scoring latest predictions label=$LABEL"
    done
  else
    preflight_label "$BASE_LABEL"
    echo "[$(date -Iseconds)] Scoring latest predictions label=$BASE_LABEL"
    RUN_DIR="$RUN_DIR" EVAL_METRIC_PROFILE="$EVAL_METRIC_PROFILE" PYTHONUNBUFFERED=1 sh /app/scripts/eval_score.sh --latest "$BASE_LABEL" "$CONFIG_PATH"
    echo "[$(date -Iseconds)] Finished scoring latest predictions label=$BASE_LABEL"
  fi
done

echo "[$(date -Iseconds)] Finished eval-score matrix config=$CONFIG_PATH"
