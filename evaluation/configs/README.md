# Evaluation Configs

This folder contains the checked-in eval configs that are meant to load successfully today.

## Current Files

- `eval_judge_local_qwen36.yaml`
  - Extends `config_server.yaml`
  - Keeps retrieval and generation defaults from the live server config
  - Owns the eval judge settings for a fixed local OpenAI-compatible judge: `qwen3.6:27b`
  - Uses `EVAL_LLM_ENDPOINT` and `OPENAI_API_KEY`

- `eval_judge_gemini_api.yaml`
  - Extends `config_server.yaml`
  - Keeps retrieval and generation defaults from the live server config
  - Owns the eval judge settings for Gemini API judging with `gemini-3.1-flash-lite-preview`
  - Uses `GEMINI_API_KEY`

- `eval_matrix_qwen35.yaml`
  - Extends `eval_judge_local_qwen36.yaml`
  - Runs the standard eight-model generation comparison with one shared judge

- `eval_matrix_qwen35_rerank_topk.yaml`
  - Extends `eval_judge_local_qwen36.yaml`
  - Sweeps `rerank_top_k` for one generation model

## Recommended Flows

Full run:

```sh
sh /app/scripts/eval_run.sh evaluation/configs/eval_judge_local_qwen36.yaml
```

Generate predictions only through the live API:

```sh
sh /app/scripts/eval_generate_api.sh qwen3.5:4b qwen35_4b
```

Score the latest saved predictions for a label:

```sh
sh /app/scripts/eval_score.sh --latest qwen35_4b evaluation/configs/eval_judge_local_qwen36.yaml
```

Full matrix run from the Python CLI:

```sh
python cli.py eval --config evaluation/configs/eval_matrix_qwen35.yaml
```

Generate-only matrix:

```sh
sh /app/scripts/eval_generate_matrix.sh
```

Generate first and automatically score only if generation succeeds:

```sh
sh /app/scripts/eval_generate_and_score_matrix.sh
```

Score-only matrix:

```sh
sh /app/scripts/eval_score_matrix.sh evaluation/configs/eval_judge_local_qwen36.yaml
```

Generate only the qwen3.5 `2b`, `4b`, and `9b` set at `rerank_top_k` values `2`, `5`, `8`, and `10`, then score with Gemini:

```sh
EVAL_MODELS="qwen3.5:9b=qwen35_9b qwen3.5:4b=qwen35_4b qwen3.5:2b=qwen35_2b" \
RERANK_TOP_K_VALUES="2 5 8 10" \
sh /app/scripts/eval_generate_matrix.sh config_server.yaml http://127.0.0.1:8000

EVAL_LABELS="qwen35_9b qwen35_4b qwen35_2b" \
RERANK_TOP_K_VALUES="2 5 8 10" \
sh /app/scripts/eval_score_matrix.sh evaluation/configs/eval_judge_gemini_api.yaml
```

Or chain both phases so scoring starts automatically after a successful generate pass:

```sh
EVAL_MODELS="qwen3.5:9b=qwen35_9b qwen3.5:4b=qwen35_4b qwen3.5:2b=qwen35_2b" \
RERANK_TOP_K_VALUES="2 5 8 10" \
sh /app/scripts/eval_generate_and_score_matrix.sh \
  config_server.yaml \
  evaluation/configs/eval_judge_gemini_api.yaml \
  http://127.0.0.1:8000
```

## Run Layout

Eval artifacts now group under one run folder:

```text
storage/eval_runs/<run_name>/
```

Each run folder contains:

- `run_manifest.json`
- `predictions/`
- `scores/`
- `logs/`

Rich filenames help when files are copied elsewhere, but the manifest is the canonical lookup source for "latest" resolution.

## Environment

The actual env surface used by these configs is:

```text
OPENAI_API_KEY
OLLAMA_LLM_ENDPOINT
EVAL_LLM_ENDPOINT
GEMINI_API_KEY
```
