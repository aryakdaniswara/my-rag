#!/bin/sh
set -eu

MODE="${1:-}"
VALUE="${2:-}"
CONFIG_PATH="${3:-evaluation/configs/eval_judge_local_qwen36.yaml}"
OUTPUT_PATH="${4:-}"
RUN_NAME="${RUN_NAME:-eval_score_$(date +%Y%m%d_%H%M%S)}"
RUN_DIR="${RUN_DIR:-/app/storage/eval_runs/$RUN_NAME}"
EVAL_METRIC_PROFILE="${EVAL_METRIC_PROFILE:-generation}"

usage() {
  echo "Usage:"
  echo "  sh /app/scripts/eval_score.sh --predictions <predictions_path> [config_path] [output_path]"
  echo "  sh /app/scripts/eval_score.sh --latest <label> [config_path] [output_path]"
  exit 1
}

if [ -z "$MODE" ] || [ -z "$VALUE" ]; then
  usage
fi

mkdir -p "$RUN_DIR/logs"

case "$MODE" in
  --predictions)
    PREDICTIONS_PATH="$VALUE"
    LABEL=$(basename "$PREDICTIONS_PATH" .json)
    ;;
  --latest)
    LABEL="$VALUE"
    PREDICTIONS_PATH=$(
      python cli.py eval-find-latest --config "$CONFIG_PATH" --label "$LABEL"
    )
    ;;
  *)
    usage
    ;;
esac

if [ ! -f "$PREDICTIONS_PATH" ]; then
  echo "Predictions file not found: $PREDICTIONS_PATH"
  exit 1
fi

LOG_PATH="$RUN_DIR/logs/eval-score__${LABEL}.log"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval-score predictions=$PREDICTIONS_PATH label=$LABEL"
echo "Config: $CONFIG_PATH"
echo "Run dir: $RUN_DIR"
echo "Metric profile: $EVAL_METRIC_PROFILE"

PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
  --mode score \
  --config "$CONFIG_PATH" \
  --predictions "$PREDICTIONS_PATH" \
  --run-dir "$RUN_DIR"

if [ -n "$OUTPUT_PATH" ]; then
  PYTHONUNBUFFERED=1 python cli.py eval-score \
    --config "$CONFIG_PATH" \
    --predictions "$PREDICTIONS_PATH" \
    --run-dir "$RUN_DIR" \
    --metric-profile "$EVAL_METRIC_PROFILE" \
    --output "$OUTPUT_PATH"
else
  PYTHONUNBUFFERED=1 python cli.py eval-score \
    --config "$CONFIG_PATH" \
    --predictions "$PREDICTIONS_PATH" \
    --run-dir "$RUN_DIR" \
    --metric-profile "$EVAL_METRIC_PROFILE"
fi

echo "[$(date -Iseconds)] Finished eval-score predictions=$PREDICTIONS_PATH label=$LABEL"
