#!/bin/sh
set -eu

LABEL="${1:-}"
CONFIG_PATH="${2:-config_server.yaml}"

if [ -z "$LABEL" ]; then
  echo "Usage: sh /app/scripts/eval_score_latest.sh <label> [config_path]"
  exit 1
fi

LATEST_PATH=$(
  ls -1t "/app/storage/eval_reports"/eval_predictions_"$LABEL"_*.json 2>/dev/null | head -n 1
)

if [ -z "${LATEST_PATH:-}" ]; then
  echo "No prediction artifact found for label: $LABEL"
  exit 1
fi

exec sh /app/scripts/eval_score.sh "$LATEST_PATH" "$LABEL" "$CONFIG_PATH"
