# Evaluation Guide

This document describes the current supported evaluation path in `my_rag`.

## Runtime Path

The main score path is:

1. `cli.py`
2. `RAGPipeline.score_eval_predictions()` in `pipeline.py`
3. `RAGASEvaluator` in `evaluation/evaluator.py`
4. installed `ragas` metric implementations

Prediction generation should normally go through the live API using the helper
scripts so it reuses the running RAG service.

## Active Scripts

- `scripts/eval_generate_and_score_api.sh`: one-model generate then score
- `scripts/eval_generate_api.sh`: one-model generate only
- `scripts/eval_score.sh`: score saved predictions
- `scripts/eval_generate_matrix.sh`: matrix generate only
- `scripts/eval_score_matrix.sh`: matrix score only
- `scripts/eval_generate_and_score_matrix.sh`: matrix generate then score
- `scripts/eval_run.sh`: direct full `cli.py eval` wrapper
- `scripts/eval_preflight.py`: shared validation

## Active Configs

The active judge is `qwen3.6:27b`.

- `evaluation/configs/base/qwen36_judge.yaml`: all four metrics
- `evaluation/configs/profiles/generation.yaml`: `faithfulness`, `answer_relevancy`
- `evaluation/configs/profiles/retrieval.yaml`: `context_precision`, `context_recall`
- `evaluation/configs/singles/generation_v4_rerank8.yaml`: recommended one-model v4 check
- `evaluation/configs/matrices/generation_rerank8.yaml`: generation matrix at `rerank_top_k: 8`
- `evaluation/configs/matrices/retrieval_qwen35_rerank_sweep.yaml`: retrieval metric rerank sweep

## Recommended One-Model v4 Run

Restart the API after code changes because streamed eval needs `/query/stream`
to emit `context`:

```sh
docker compose restart rag-api
```

Run generation and scoring automatically:

```sh
sh /app/scripts/eval_generate_and_score_api.sh \
  qwen3.5:4b \
  qwen35_4b_v4_rerank8 \
  evaluation/configs/singles/generation_v4_rerank8.yaml \
  http://127.0.0.1:8000
```

Try another model by changing only the model and label:

```sh
sh /app/scripts/eval_generate_and_score_api.sh \
  qwen3.5:9b \
  qwen35_9b_v4_rerank8 \
  evaluation/configs/singles/generation_v4_rerank8.yaml \
  http://127.0.0.1:8000
```

## Matrix Run

Generate streamed predictions for the fixed rerank-8 generation matrix:

```sh
sh /app/scripts/eval_generate_matrix.sh \
  evaluation/configs/matrices/generation_rerank8.yaml \
  http://127.0.0.1:8000
```

Score those predictions:

```sh
sh /app/scripts/eval_score_matrix.sh \
  evaluation/configs/matrices/generation_rerank8.yaml
```

Or chain both phases:

```sh
sh /app/scripts/eval_generate_and_score_matrix.sh \
  evaluation/configs/matrices/generation_rerank8.yaml \
  evaluation/configs/matrices/generation_rerank8.yaml \
  http://127.0.0.1:8000
```

## Metrics

The repo supports the same four RAGAS metrics:

- `faithfulness`
- `answer_relevancy`
- `context_precision`
- `context_recall`

For model answer-quality comparison, use generation metrics only:

- `faithfulness`
- `answer_relevancy`

Use retrieval metrics separately when retrieval settings, corpus, chunking, or
dataset evidence changes.

## Artifacts

Eval artifacts are grouped under:

```text
storage/eval_runs/<run_name>/
  run_manifest.json
  predictions/
  scores/
  logs/
```

The manifest is the source of truth for artifact paths and latest prediction
lookup.

## Environment

```text
OPENAI_API_KEY
OLLAMA_LLM_ENDPOINT
EVAL_LLM_ENDPOINT
```
