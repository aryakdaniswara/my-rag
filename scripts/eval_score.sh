#!/bin/sh
set -eu

MODE="${1:-}"
VALUE="${2:-}"
CONFIG_PATH="${3:-config_server.yaml}"
OUTPUT_PATH="${4:-}"

usage() {
  echo "Usage:"
  echo "  sh /app/scripts/eval_score.sh --predictions <predictions_path> [config_path] [output_path]"
  echo "  sh /app/scripts/eval_score.sh --latest <label> [config_path] [output_path]"
  exit 1
}

if [ -z "$MODE" ] || [ -z "$VALUE" ]; then
  usage
fi

case "$MODE" in
  --predictions)
    PREDICTIONS_PATH="$VALUE"
    ;;
  --latest)
    LABEL="$VALUE"
    PREDICTIONS_PATH=$(
      ls -1t "/app/storage/eval_predictions"/eval_predictions_"$LABEL"_*.json 2>/dev/null | head -n 1
    )
    if [ -z "${PREDICTIONS_PATH:-}" ]; then
      echo "No prediction artifact found for label: $LABEL"
      exit 1
    fi
    ;;
  *)
    usage
    ;;
esac

if [ ! -f "$PREDICTIONS_PATH" ]; then
  echo "Predictions file not found: $PREDICTIONS_PATH"
  exit 1
fi

LABEL=$(basename "$PREDICTIONS_PATH" .json)
LOG_DIR="/app/storage/eval_logs"
LOG_PATH="$LOG_DIR/eval_score_${LABEL}.log"

mkdir -p "$LOG_DIR"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval-score for predictions=$PREDICTIONS_PATH label=$LABEL"
echo "Config: $CONFIG_PATH"

PYTHONUNBUFFERED=1 python /app/scripts/eval_preflight.py \
  --mode score \
  --config "$CONFIG_PATH" \
  --predictions "$PREDICTIONS_PATH"

if [ -n "$OUTPUT_PATH" ]; then
  PYTHONUNBUFFERED=1 python cli.py eval-score \
    --config "$CONFIG_PATH" \
    --predictions "$PREDICTIONS_PATH" \
    --output "$OUTPUT_PATH"
else
  PYTHONUNBUFFERED=1 python cli.py eval-score \
    --config "$CONFIG_PATH" \
    --predictions "$PREDICTIONS_PATH"
fi

echo "[$(date -Iseconds)] Finished eval-score for predictions=$PREDICTIONS_PATH label=$LABEL"
