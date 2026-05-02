#!/bin/sh
set -eu

PREDICTIONS_PATH="${1:-}"
LABEL="${2:-}"
CONFIG_PATH="${3:-config_server.yaml}"

if [ -z "$PREDICTIONS_PATH" ]; then
  echo "Usage: sh /app/scripts/eval_score.sh <predictions_path> [label] [config_path]"
  exit 1
fi

if [ ! -f "$PREDICTIONS_PATH" ]; then
  echo "Predictions file not found: $PREDICTIONS_PATH"
  exit 1
fi

if [ -z "$LABEL" ]; then
  LABEL=$(basename "$PREDICTIONS_PATH" .json)
fi

LOG_DIR="/app/storage/eval_logs"
LOG_PATH="$LOG_DIR/eval_score_${LABEL}.log"

mkdir -p "$LOG_DIR"
exec >>"$LOG_PATH" 2>&1

echo "[$(date -Iseconds)] Starting eval-score for predictions=$PREDICTIONS_PATH label=$LABEL"
echo "Config: $CONFIG_PATH"

PYTHONUNBUFFERED=1 python cli.py eval-score \
  --config "$CONFIG_PATH" \
  --predictions "$PREDICTIONS_PATH"

echo "[$(date -Iseconds)] Finished eval-score for predictions=$PREDICTIONS_PATH label=$LABEL"
