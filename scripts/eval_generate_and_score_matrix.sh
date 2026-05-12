#!/bin/sh
set -eu

GENERATE_CONFIG_PATH="${1:-evaluation/configs/matrices/generation_rerank8.yaml}"
JUDGE_CONFIG_PATH="${2:-$GENERATE_CONFIG_PATH}"
API_BASE_URL="${3:-http://127.0.0.1:8000}"
RETRIEVAL_CONFIG_PATH="${4:-evaluation/configs/profiles/retrieval.yaml}"
RETRIEVAL_LABEL="${5:-${RETRIEVAL_LABEL:-}}"
RUN_NAME="${RUN_NAME:-eval_generate_and_score_matrix_$(date +%Y%m%d_%H%M%S)}"
RUN_ROOT="${RUN_ROOT:-/app/storage/eval_runs/$RUN_NAME}"
GENERATE_RUN_DIR="${GENERATE_RUN_DIR:-$RUN_ROOT/generate}"
GENERATION_SCORE_RUN_DIR="${GENERATION_SCORE_RUN_DIR:-$RUN_ROOT/score_generation}"
RETRIEVAL_SCORE_RUN_DIR="${RETRIEVAL_SCORE_RUN_DIR:-$RUN_ROOT/score_retrieval}"

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
echo "Generation score config: $JUDGE_CONFIG_PATH"
echo "API base URL: $API_BASE_URL"
echo "Retrieval score config: $RETRIEVAL_CONFIG_PATH"
echo "Retrieval label: ${RETRIEVAL_LABEL:-<none>}"
echo "Run root: $RUN_ROOT"
echo "Generate run dir: $GENERATE_RUN_DIR"
echo "Generation score run dir: $GENERATION_SCORE_RUN_DIR"
echo "Retrieval score run dir: $RETRIEVAL_SCORE_RUN_DIR"

RUN_DIR="$GENERATE_RUN_DIR" \
  sh /app/scripts/eval_generate_matrix.sh "$GENERATE_CONFIG_PATH" "$API_BASE_URL"

EVAL_LABELS="$EVAL_LABELS" \
RUN_DIR="$GENERATION_SCORE_RUN_DIR" \
  sh /app/scripts/eval_score_matrix.sh "$JUDGE_CONFIG_PATH"

if [ -n "$RETRIEVAL_LABEL" ]; then
  EVAL_LABELS="$RETRIEVAL_LABEL" \
  RUN_DIR="$RETRIEVAL_SCORE_RUN_DIR" \
    sh /app/scripts/eval_score_matrix.sh "$RETRIEVAL_CONFIG_PATH"
else
  echo "[$(date -Iseconds)] Skipping retrieval score step because no retrieval label was provided"
fi

echo "[$(date -Iseconds)] Finished chained generate->score matrix run"
