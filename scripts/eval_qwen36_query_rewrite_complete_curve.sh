#!/bin/sh
set -eu

API_BASE_URL="${1:-http://127.0.0.1:8000}"
RUN_NAME="${RUN_NAME:-eval_qwen36_query_rewrite_complete_curve_$(date +%Y%m%d_%H%M%S)}"
RUN_ROOT="${RUN_ROOT:-/app/storage/eval_runs/$RUN_NAME}"
EVAL_SHOW_ANSWERS="${EVAL_SHOW_ANSWERS:-false}"
EVAL_GENERATE_STREAM="${EVAL_GENERATE_STREAM:-true}"

NORMAL_GENERATION_CONFIG="/app/evaluation/configs/profiles/generation.yaml"
NORMAL_RETRIEVAL_CONFIG="/app/evaluation/configs/profiles/retrieval.yaml"
TC_GENERATION_CONFIG="/app/evaluation/configs/profiles/generation_tc_rag_v5.yaml"
TC_RETRIEVAL_CONFIG="/app/evaluation/configs/profiles/retrieval_tc_rag_v5.yaml"

NORMAL_QWEN36_SPECS="qwen3.6:27b|normal_qwen36_27b_rerank3|3 qwen3.6:27b|normal_qwen36_27b_rerank8|8 qwen3.6:27b|normal_qwen36_27b_rerank10|10"
NORMAL_QWEN36_LABELS="normal_qwen36_27b_rerank3 normal_qwen36_27b_rerank8 normal_qwen36_27b_rerank10"

TC_QWEN36_SPECS="qwen3.6:27b|tc_qwen36_27b_rerank3|3 qwen3.6:27b|tc_qwen36_27b_rerank5|5 qwen3.6:27b|tc_qwen36_27b_rerank8|8 qwen3.6:27b|tc_qwen36_27b_rerank10|10"
TC_QWEN36_LABELS="tc_qwen36_27b_rerank3 tc_qwen36_27b_rerank5 tc_qwen36_27b_rerank8 tc_qwen36_27b_rerank10"

TC_QWEN35_SPECS="qwen3.5:9b|tc_qwen35_9b_rerank3|3 qwen3.5:9b|tc_qwen35_9b_rerank5|5 qwen3.5:9b|tc_qwen35_9b_rerank8|8 qwen3.5:9b|tc_qwen35_9b_rerank10|10"
TC_QWEN35_LABELS="tc_qwen35_9b_rerank3 tc_qwen35_9b_rerank5 tc_qwen35_9b_rerank8 tc_qwen35_9b_rerank10"

ALL_NORMAL_LABELS="$NORMAL_QWEN36_LABELS"
ALL_TC_LABELS="$TC_QWEN36_LABELS $TC_QWEN35_LABELS"

echo "[$(date -Iseconds)] Starting qwen complete rerank curve for normal v5 and TC query-rewrite v5"
echo "API base URL: $API_BASE_URL"
echo "Run root: $RUN_ROOT"
echo "Stream generation: $EVAL_GENERATE_STREAM"
echo "Normal v5 qwen3.6:27b rerank 5 is intentionally not regenerated; use the existing qwen36_27b_rerank5 baseline."
echo "Generation happens first for every planned run, then generation scoring, then retrieval scoring."

echo "[$(date -Iseconds)] Step 1/6: generate normal ui_main_v5 qwen3.6:27b rerank 3 8 10"
EVAL_MODELS="$NORMAL_QWEN36_SPECS" \
RUN_DIR="$RUN_ROOT/01_generate_normal_qwen36_curve" \
EVAL_SHOW_ANSWERS="$EVAL_SHOW_ANSWERS" \
EVAL_GENERATE_STREAM="$EVAL_GENERATE_STREAM" \
sh /app/scripts/eval_generate_matrix.sh "$NORMAL_GENERATION_CONFIG" "$API_BASE_URL"

echo "[$(date -Iseconds)] Step 2/6: generate TC query-rewrite qwen3.6:27b rerank 3 5 8 10"
EVAL_MODELS="$TC_QWEN36_SPECS" \
RUN_DIR="$RUN_ROOT/02_generate_tc_qwen36_curve" \
EVAL_SHOW_ANSWERS="$EVAL_SHOW_ANSWERS" \
EVAL_GENERATE_STREAM="$EVAL_GENERATE_STREAM" \
sh /app/scripts/eval_generate_matrix.sh "$TC_GENERATION_CONFIG" "$API_BASE_URL"

echo "[$(date -Iseconds)] Step 3/6: generate TC query-rewrite qwen3.5:9b rerank 3 5 8 10"
EVAL_MODELS="$TC_QWEN35_SPECS" \
RUN_DIR="$RUN_ROOT/03_generate_tc_qwen35_9b_curve" \
EVAL_SHOW_ANSWERS="$EVAL_SHOW_ANSWERS" \
EVAL_GENERATE_STREAM="$EVAL_GENERATE_STREAM" \
sh /app/scripts/eval_generate_matrix.sh "$TC_GENERATION_CONFIG" "$API_BASE_URL"

echo "[$(date -Iseconds)] Step 4/6: score generation quality for normal ui_main_v5 qwen3.6:27b curve"
EVAL_LABELS="$ALL_NORMAL_LABELS" \
RUN_DIR="$RUN_ROOT/04_score_normal_qwen36_generation" \
sh /app/scripts/eval_score_matrix.sh "$NORMAL_GENERATION_CONFIG"

echo "[$(date -Iseconds)] Step 5/6: score generation quality for TC query-rewrite curves"
EVAL_LABELS="$ALL_TC_LABELS" \
RUN_DIR="$RUN_ROOT/05_score_tc_generation" \
sh /app/scripts/eval_score_matrix.sh "$TC_GENERATION_CONFIG"

echo "[$(date -Iseconds)] Step 6/6: score retrieval quality for all generated curves"
EVAL_LABELS="$ALL_NORMAL_LABELS" \
RUN_DIR="$RUN_ROOT/06_score_normal_qwen36_retrieval" \
sh /app/scripts/eval_score_matrix.sh "$NORMAL_RETRIEVAL_CONFIG"

EVAL_LABELS="$ALL_TC_LABELS" \
RUN_DIR="$RUN_ROOT/07_score_tc_retrieval" \
sh /app/scripts/eval_score_matrix.sh "$TC_RETRIEVAL_CONFIG"

echo "[$(date -Iseconds)] Finished qwen complete rerank curve"
echo "Run root: $RUN_ROOT"
echo "Existing baseline to compare: ui_main_v5 qwen36_27b_rerank5"
