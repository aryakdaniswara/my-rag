#!/bin/sh
set -eu

API_BASE_URL="${1:-http://127.0.0.1:8000}"
RUN_NAME="${RUN_NAME:-eval_remaining4_and_qwen35_rerank_sweep_$(date +%Y%m%d_%H%M%S)}"
RUN_ROOT="${RUN_ROOT:-/app/storage/eval_runs/$RUN_NAME}"
EVAL_SHOW_ANSWERS="${EVAL_SHOW_ANSWERS:-false}"

REMAINING4_CONFIG="/app/evaluation/configs/matrices/generation_rerank5_remaining4.yaml"
RERANK_SWEEP_CONFIG="/app/evaluation/configs/matrices/retrieval_qwen35_rerank_sweep.yaml"

echo "[$(date -Iseconds)] Starting remaining-model generation + qwen35 rerank sweep"
echo "API base URL: $API_BASE_URL"
echo "Run root: $RUN_ROOT"
echo "Remaining-model config: $REMAINING4_CONFIG"
echo "Qwen35 rerank sweep config: $RERANK_SWEEP_CONFIG"

echo "[$(date -Iseconds)] Step 1/3: generate answers for remaining rerank5 models"
RUN_DIR="$RUN_ROOT/01_generate_remaining4" \
EVAL_SHOW_ANSWERS="$EVAL_SHOW_ANSWERS" \
sh /app/scripts/eval_generate_matrix.sh "$REMAINING4_CONFIG" "$API_BASE_URL"

echo "[$(date -Iseconds)] Step 2/3: generate answers for qwen35 rerank sweep (3, 5, 8, 10)"
RUN_DIR="$RUN_ROOT/02_generate_qwen35_rerank_sweep" \
EVAL_SHOW_ANSWERS="$EVAL_SHOW_ANSWERS" \
sh /app/scripts/eval_generate_matrix.sh "$RERANK_SWEEP_CONFIG" "$API_BASE_URL"

echo "[$(date -Iseconds)] Step 3/3: score retrieval quality for qwen35 rerank sweep"
RUN_DIR="$RUN_ROOT/03_score_qwen35_rerank_sweep_retrieval" \
sh /app/scripts/eval_score_matrix.sh "$RERANK_SWEEP_CONFIG"

echo "[$(date -Iseconds)] Finished remaining-model generation + qwen35 rerank sweep"
echo "Run root: $RUN_ROOT"
