#!/bin/sh
set -eu

API_BASE_URL="${1:-http://127.0.0.1:8000}"
RUN_NAME="${RUN_NAME:-eval_subset_rerank5_$(date +%Y%m%d_%H%M%S)}"
RUN_ROOT="${RUN_ROOT:-/app/storage/eval_runs/$RUN_NAME}"
EVAL_SHOW_ANSWERS="${EVAL_SHOW_ANSWERS:-false}"

GEMMA_CONFIG="/app/evaluation/configs/matrices/generation_rerank5_gemma4_26b.yaml"
REST_CONFIG="/app/evaluation/configs/matrices/generation_rerank5_rest.yaml"
SUBSET4_CONFIG="/app/evaluation/configs/matrices/generation_rerank5_subset4.yaml"
GEMMA_RETRIEVAL_CONFIG="/app/evaluation/configs/singles/retrieval_gemma4_26b_rerank5.yaml"

echo "[$(date -Iseconds)] Starting staged subset eval plan"
echo "API base URL: $API_BASE_URL"
echo "Run root: $RUN_ROOT"
echo "Gemma config: $GEMMA_CONFIG"
echo "Rest config: $REST_CONFIG"
echo "Subset-4 config: $SUBSET4_CONFIG"
echo "Gemma retrieval config: $GEMMA_RETRIEVAL_CONFIG"

echo "[$(date -Iseconds)] Step 1/5: generate answers for gemma4_26b_rerank5"
RUN_DIR="$RUN_ROOT/01_generate_gemma" \
EVAL_SHOW_ANSWERS="$EVAL_SHOW_ANSWERS" \
sh /app/scripts/eval_generate_matrix.sh "$GEMMA_CONFIG" "$API_BASE_URL"

echo "[$(date -Iseconds)] Step 2/5: score generation quality for gemma4_26b_rerank5"
RUN_DIR="$RUN_ROOT/02_score_gemma_generation" \
sh /app/scripts/eval_score_matrix.sh "$GEMMA_CONFIG"

echo "[$(date -Iseconds)] Step 3/5: score retrieval quality for gemma4_26b_rerank5"
RUN_DIR="$RUN_ROOT/03_score_gemma_retrieval" \
sh /app/scripts/eval_score.sh --latest "gemma4_26b_rerank5" "$GEMMA_RETRIEVAL_CONFIG"

echo "[$(date -Iseconds)] Step 4/5: generate answers for the remaining rerank5 models"
RUN_DIR="$RUN_ROOT/04_generate_rest" \
EVAL_SHOW_ANSWERS="$EVAL_SHOW_ANSWERS" \
sh /app/scripts/eval_generate_matrix.sh "$REST_CONFIG" "$API_BASE_URL"

echo "[$(date -Iseconds)] Step 5/5: score generation quality for the remaining rerank5 models"
RUN_DIR="$RUN_ROOT/05_score_rest_generation" \
sh /app/scripts/eval_score_matrix.sh "$REST_CONFIG"

echo "[$(date -Iseconds)] Finished staged subset eval plan"
echo "Run root: $RUN_ROOT"
