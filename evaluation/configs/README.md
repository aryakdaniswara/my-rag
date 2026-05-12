# Evaluation Configs

This folder contains the checked-in eval configs that are meant to load successfully today.

## Current Files

- `eval_judge_local_qwen36.yaml`
  - Extends `config_server.yaml`
  - Keeps retrieval and generation defaults from the live server config
  - Owns the eval judge settings for a fixed local OpenAI-compatible judge: `qwen3.6:27b`
  - Uses `EVAL_LLM_ENDPOINT` and `OPENAI_API_KEY`
  - Inherits the full metric list from `config_server.yaml`

- `eval_judge_local_qwen36_generation.yaml`
  - Extends `eval_judge_local_qwen36.yaml`
  - Scores generation quality only: `faithfulness`, `answer_relevancy`

- `eval_judge_local_qwen36_retrieval.yaml`
  - Extends `eval_judge_local_qwen36.yaml`
  - Scores retrieval quality only: `context_precision`, `context_recall`

- `eval_judge_gemini_api.yaml`
  - Extends `config_server.yaml`
  - Keeps retrieval and generation defaults from the live server config
  - Owns the eval judge settings for Gemini API judging with `gemini-3.1-flash-lite-preview`
  - Uses `GEMINI_API_KEY`

- `eval_matrix_qwen35.yaml`
  - Extends `eval_judge_local_qwen36.yaml`
  - Runs the standard eight-model generation comparison with one shared judge
  - Scores generation quality only

- `eval_matrix_8models_rerank8.yaml`
  - Extends `eval_judge_local_qwen36.yaml`
  - Runs the current eight-model generation comparison with fixed `rerank_top_k: 8`
  - Scores generation quality only

- `eval_matrix_qwen35_rerank_topk.yaml`
  - Extends `eval_judge_local_qwen36.yaml`
  - Sweeps `rerank_top_k` for one generation model
  - Scores retrieval quality only

## Recommended Flows

Full run:

```sh
sh /app/scripts/eval_run.sh evaluation/configs/eval_judge_local_qwen36.yaml
```

Generate predictions only through the live API:

```sh
sh /app/scripts/eval_generate_api.sh qwen3.5:4b qwen35_4b
```

The generate helper uses `/query/stream` by default and prints each final answer
to the run log while still saving the full prediction artifact. Disable that with:

```sh
EVAL_GENERATE_STREAM=false EVAL_SHOW_ANSWERS=false \
sh /app/scripts/eval_generate_api.sh qwen3.5:4b qwen35_4b
```

Score the latest saved predictions with all four metrics:

```sh
sh /app/scripts/eval_score.sh --latest qwen35_4b evaluation/configs/eval_judge_local_qwen36.yaml
```

Score helpers default to the metrics declared in the config. For generation
quality, use:

```sh
sh /app/scripts/eval_score.sh --latest qwen35_4b evaluation/configs/eval_judge_local_qwen36_generation.yaml
```

For retrieval quality, use:

```sh
sh /app/scripts/eval_score.sh --latest qwen35_4b evaluation/configs/eval_judge_local_qwen36_retrieval.yaml
```

`EVAL_METRIC_PROFILE` still exists for one-off overrides, but the preferred
workflow is to make the metric choice explicit in the eval config.

## Step-by-Step Eval Run

Use this flow when comparing multiple generation models. It keeps retrieval
quality separate from generation quality.

### 1. Restart the API after code changes

The streaming eval path requires `/query/stream` to emit `context`, so restart
the API container after pulling or editing this code:

```sh
docker compose restart rag-api
```

### 2. Generate streamed predictions for one model

This calls the live API, streams answers, prints each final answer to the run
log, and saves a prediction artifact under `storage/eval_runs/<run>/predictions/`.

```sh
sh /app/scripts/eval_generate_api.sh \
  qwen3.5:4b \
  qwen35_4b \
  config_server.yaml \
  http://127.0.0.1:8000
```

To watch the generated answers while the detached command is running, tail the
run log:

```sh
tail -f /app/storage/eval_runs/<run_name>/logs/eval-generate__qwen35_4b.log
```

### 3. Score generation quality for that model

This config scores generation-quality metrics:

```text
faithfulness, answer_relevancy
```

Run:

```sh
sh /app/scripts/eval_score.sh \
  --latest qwen35_4b \
  evaluation/configs/eval_judge_local_qwen36_generation.yaml
```

The score report is saved under `storage/eval_runs/<run>/scores/`.

### 4. Generate predictions for a model matrix

Use this when comparing several generation models with the same retrieval
settings:

```sh
sh /app/scripts/eval_generate_matrix.sh \
  evaluation/configs/eval_matrix_8models_rerank8.yaml \
  http://127.0.0.1:8000
```

The helper uses the model labels from `evaluation.model_matrix`.

### 5. Score generation quality for the matrix

This scores the latest prediction artifact for each matrix label. The config
declares generation-only metrics:

```sh
sh /app/scripts/eval_score_matrix.sh \
  evaluation/configs/eval_matrix_8models_rerank8.yaml
```

### 6. Score retrieval quality separately

Run this once per retrieval setting or dataset snapshot, not for every generation
model unless retrieval settings changed. Retrieval-only scoring uses:

```text
context_precision, context_recall
```

```sh
sh /app/scripts/eval_score.sh \
  --latest qwen35_4b \
  evaluation/configs/eval_judge_local_qwen36_retrieval.yaml
```

### 7. Find artifacts

Each run folder contains:

```text
storage/eval_runs/<run_name>/
  run_manifest.json
  predictions/
  scores/
  logs/
```

Use the manifest for the authoritative list of generated prediction and score
artifacts.

Full matrix run from the Python CLI:

```sh
python cli.py eval --config evaluation/configs/eval_matrix_8models_rerank8.yaml
```

Generate-only matrix:

```sh
sh /app/scripts/eval_generate_matrix.sh evaluation/configs/eval_matrix_8models_rerank8.yaml
```

Generate first and automatically score only if generation succeeds:

```sh
RUN_NAME=eval_v3_qwen36_judge_$(date +%Y%m%d_%H%M%S) \
sh /app/scripts/eval_generate_and_score_matrix.sh \
  evaluation/configs/eval_matrix_8models_rerank8.yaml \
  evaluation/configs/eval_matrix_8models_rerank8.yaml \
  http://127.0.0.1:8000
```

Score-only matrix:

```sh
sh /app/scripts/eval_score_matrix.sh evaluation/configs/eval_matrix_8models_rerank8.yaml
```

Matrix helpers now prefer `evaluation.model_matrix` from the config for model names,
labels, and per-model `rerank_top_k`. `EVAL_MODELS` and `EVAL_LABELS` still work
as ad hoc overrides.

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
Prediction and score filenames use this shorter pattern:

```text
predictions__<dataset>__gen_<label>__<timestamp>.json
score__<dataset>__gen_<label>__judge_<judge>__<timestamp>.json
```

## Environment

The actual env surface used by these configs is:

```text
OPENAI_API_KEY
OLLAMA_LLM_ENDPOINT
EVAL_LLM_ENDPOINT
GEMINI_API_KEY
```
