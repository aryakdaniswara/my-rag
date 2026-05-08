#!/bin/sh
set -eu

GENERATE_CONFIG_PATH="${1:-evaluation/configs/eval_matrix_8models_rerank8.yaml}"
JUDGE_CONFIG_PATH="${2:-$GENERATE_CONFIG_PATH}"
API_BASE_URL="${3:-http://127.0.0.1:8000}"
RUN_NAME="${RUN_NAME:-eval_generate_and_score_matrix_$(date +%Y%m%d_%H%M%S)}"
RUN_ROOT="${RUN_ROOT:-/app/storage/eval_runs/$RUN_NAME}"
GENERATE_RUN_DIR="${GENERATE_RUN_DIR:-$RUN_ROOT/generate}"
SCORE_RUN_DIR="${SCORE_RUN_DIR:-$RUN_ROOT/score}"

mkdir -p "$RUN_ROOT"

derive_eval_labels() {
  LABELS=""
  for MODEL_SPEC in ${EVAL_MODELS:-}; do
    BASE_LABEL="${MODEL_SPEC#*=}"
    if [ -n "$LABELS" ]; then
      LABELS="$LABELS $BASE_LABEL"
    else
      LABELS="$BASE_LABEL"
    fi
  done
  printf '%s\n' "$LABELS"
}

if [ -n "${EVAL_MODELS:-}" ]; then
  EVAL_LABELS="$(derive_eval_labels)"
else
  EVAL_LABELS="${EVAL_LABELS:-$(python /app/scripts/eval_preflight.py --mode generate --config "$GENERATE_CONFIG_PATH" --emit-labels)}"
fi

echo "[$(date -Iseconds)] Starting chained generate->score matrix run"
echo "Generate config: $GENERATE_CONFIG_PATH"
echo "Judge config: $JUDGE_CONFIG_PATH"
echo "API base URL: $API_BASE_URL"
echo "Run root: $RUN_ROOT"
echo "Generate run dir: $GENERATE_RUN_DIR"
echo "Score run dir: $SCORE_RUN_DIR"

RUN_DIR="$GENERATE_RUN_DIR" \
  sh /app/scripts/eval_generate_matrix.sh "$GENERATE_CONFIG_PATH" "$API_BASE_URL"

EVAL_LABELS="$EVAL_LABELS" \
RUN_DIR="$SCORE_RUN_DIR" \
  sh /app/scripts/eval_score_matrix.sh "$JUDGE_CONFIG_PATH"

echo "[$(date -Iseconds)] Finished chained generate->score matrix run"
