# Evaluation Guide

This document describes the evaluation path that is actually wired in `my_rag` now.

## Runtime Truth Path

The current evaluation flow is:

1. `cli.py`
2. `RAGPipeline.evaluate()` or `RAGPipeline.score_eval_predictions()` in `pipeline.py`
3. `RAGASEvaluator` in `evaluation/evaluator.py`
4. installed `ragas` metric implementations in `.venv/Lib/site-packages/ragas/...`

Important repo files for the checked-in eval workflow:

- `config_server.yaml`
- `evaluation/configs/`
- `cli.py`
- `pipeline.py`
- `scripts/eval_run.sh`
- `scripts/eval_generate_api.sh`
- `scripts/eval_score.sh`

## Config Ownership

`config_server.yaml` remains the live RAG runtime baseline for:

- retrieval defaults
- generation defaults
- dataset path
- eval run root

Judge ownership now lives in eval-side configs under `evaluation/configs/`.

Use:

- `evaluation/configs/eval_judge_local_qwen36.yaml` for a fixed local OpenAI-compatible judge
- `evaluation/configs/eval_judge_gemini_api.yaml` for Gemini API judging

This keeps judge choice out of the main server config so scoring can switch judges cleanly.

## Supported Metrics

The repo still evaluates the same four RAGAS metrics:

- `faithfulness`
- `answer_relevancy`
- `context_precision`
- `context_recall`

This cleanup did not change metric logic or score semantics.

## Main Workflows

### Full Run

Recommended wrapper:

```sh
sh /app/scripts/eval_run.sh evaluation/configs/eval_judge_local_qwen36.yaml
```

This is the main supported full-run entrypoint.

You can also call the CLI directly:

```sh
python cli.py eval --config evaluation/configs/eval_judge_local_qwen36.yaml
```

If the config contains `evaluation.model_matrix`, the same command runs the matrix.

### Generate Only

Generate saved predictions through the live API:

```sh
sh /app/scripts/eval_generate_api.sh qwen3.5:4b qwen35_4b
```

Direct CLI:

```sh
python cli.py eval-generate \
  --config config_server.yaml \
  --api-base-url http://127.0.0.1:8000 \
  --model qwen3.5:4b \
  --label qwen35_4b
```

### Score Only

Score a specific saved prediction artifact:

```sh
sh /app/scripts/eval_score.sh \
  --predictions /app/storage/eval_runs/<run_name>/predictions/<file>.json \
  evaluation/configs/eval_judge_local_qwen36.yaml
```

Or resolve the latest saved predictions for a label from run manifests:

```sh
sh /app/scripts/eval_score.sh --latest qwen35_4b evaluation/configs/eval_judge_local_qwen36.yaml
```

Direct CLI:

```sh
python cli.py eval-score \
  --config evaluation/configs/eval_judge_gemini_api.yaml \
  --predictions storage/eval_runs/<run_name>/predictions/<file>.json
```

## Run Layout

The structured eval workspace now groups artifacts under:

```text
storage/eval_runs/<run_name>/
```

Each run folder contains:

- `run_manifest.json`
- `predictions/`
- `scores/`
- `logs/`

The manifest is the source of truth for:

- run metadata
- dataset info
- generation info
- judge info
- artifact paths
- latest prediction lookup

Rich filenames are still used so copied files remain readable outside the manifest.

## Matrix Workflows

Standard eight-model full matrix:

```sh
python cli.py eval --config evaluation/configs/eval_matrix_qwen35.yaml
```

Generate-only matrix:

```sh
sh /app/scripts/eval_generate_matrix.sh
```

Score-only matrix against the latest saved predictions:

```sh
sh /app/scripts/eval_score_matrix.sh evaluation/configs/eval_judge_local_qwen36.yaml
```

Rerank sweep generation:

```sh
RERANK_TOP_K_VALUES="3 5 8 10" sh /app/scripts/eval_generate_matrix.sh
```

Rerank sweep scoring:

```sh
RERANK_TOP_K_VALUES="3 5 8 10" sh /app/scripts/eval_score_matrix.sh evaluation/configs/eval_judge_local_qwen36.yaml
```

## Environment

The actual env surface for runtime plus eval is:

```text
OPENAI_API_KEY
OLLAMA_LLM_ENDPOINT
EVAL_LLM_ENDPOINT
GEMINI_API_KEY
```

Notes:

- local OpenAI-compatible judge configs use `EVAL_LLM_ENDPOINT`
- Gemini judge configs use `GEMINI_API_KEY`
- local OpenAI-compatible endpoints can fall back to `OPENAI_API_KEY=dummy`

## Output Provenance

Every prediction or scored artifact still includes `runtime_settings`.

Scored outputs also preserve:

- generation model
- judge model
- dataset path
- timing summary

## Current Limits

- `ttft_ms` is still not captured in the non-streaming eval path
- the exact evaluation prompt text still comes from the installed `ragas` package, not from a repo-local prompt file
