#!/bin/sh
set -eu

API_BASE_URL="${1:-http://127.0.0.1:8000}"
RUN_NAME="${RUN_NAME:-eval_qwen35_9b_rerank_sweep_then_gptoss_rerank8_$(date +%Y%m%d_%H%M%S)}"
RUN_ROOT="${RUN_ROOT:-/app/storage/eval_runs/$RUN_NAME}"
EVAL_SHOW_ANSWERS="${EVAL_SHOW_ANSWERS:-false}"

GENERATION_CONFIG="/app/evaluation/configs/profiles/generation.yaml"
RETRIEVAL_CONFIG="/app/evaluation/configs/profiles/retrieval.yaml"

QWEN_SWEEP_SPECS="qwen3.5:9b|qwen35_9b_rerank3|3 qwen3.5:9b|qwen35_9b_rerank5|5 qwen3.5:9b|qwen35_9b_rerank8|8 qwen3.5:9b|qwen35_9b_rerank10|10"
QWEN_SWEEP_LABELS="qwen35_9b_rerank3 qwen35_9b_rerank5 qwen35_9b_rerank8 qwen35_9b_rerank10"

GPT_OSS_SPEC="gpt-oss:20b|gpt_oss_20b_rerank8|8"
GPT_OSS_LABEL="gpt_oss_20b_rerank8"

echo "[$(date -Iseconds)] Starting qwen3.5:9b rerank sweep then gpt-oss rerank8 generation run"
echo "API base URL: $API_BASE_URL"
echo "Run root: $RUN_ROOT"
echo "Generation config: $GENERATION_CONFIG"
echo "Retrieval config: $RETRIEVAL_CONFIG"
echo "Qwen sweep labels: $QWEN_SWEEP_LABELS"
echo "GPT OSS label: $GPT_OSS_LABEL"

echo "[$(date -Iseconds)] Step 1/5: generate qwen3.5:9b predictions for rerank 3 5 8 10"
EVAL_MODELS="$QWEN_SWEEP_SPECS" \
RUN_DIR="$RUN_ROOT/01_generate_qwen35_9b_rerank_sweep" \
EVAL_SHOW_ANSWERS="$EVAL_SHOW_ANSWERS" \
sh /app/scripts/eval_generate_matrix.sh "$GENERATION_CONFIG" "$API_BASE_URL"

echo "[$(date -Iseconds)] Step 2/5: score generation quality for qwen3.5:9b rerank sweep"
EVAL_LABELS="$QWEN_SWEEP_LABELS" \
RUN_DIR="$RUN_ROOT/02_score_qwen35_9b_generation" \
sh /app/scripts/eval_score_matrix.sh "$GENERATION_CONFIG"

echo "[$(date -Iseconds)] Step 3/5: score retrieval quality for qwen3.5:9b rerank sweep"
EVAL_LABELS="$QWEN_SWEEP_LABELS" \
RUN_DIR="$RUN_ROOT/03_score_qwen35_9b_retrieval" \
sh /app/scripts/eval_score_matrix.sh "$RETRIEVAL_CONFIG"

echo "[$(date -Iseconds)] Step 4/5: generate gpt-oss:20b predictions for rerank 8"
EVAL_MODELS="$GPT_OSS_SPEC" \
RUN_DIR="$RUN_ROOT/04_generate_gpt_oss_rerank8" \
EVAL_SHOW_ANSWERS="$EVAL_SHOW_ANSWERS" \
sh /app/scripts/eval_generate_matrix.sh "$GENERATION_CONFIG" "$API_BASE_URL"

echo "[$(date -Iseconds)] Step 5/5: score generation quality for gpt-oss:20b rerank 8"
EVAL_LABELS="$GPT_OSS_LABEL" \
RUN_DIR="$RUN_ROOT/05_score_gpt_oss_generation" \
sh /app/scripts/eval_score_matrix.sh "$GENERATION_CONFIG"

echo "[$(date -Iseconds)] Finished qwen3.5:9b rerank sweep then gpt-oss rerank8 generation run"
echo "Run root: $RUN_ROOT"
