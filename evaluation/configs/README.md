# Evaluation Configs

This folder is intentionally small. The active judge is always `qwen3.6:27b`;
configs differ only by metric profile or model matrix.

## Layout

```text
evaluation/configs/
  base/
    qwen36_judge.yaml
  profiles/
    generation.yaml
    retrieval.yaml
  matrices/
    generation_rerank8.yaml
    retrieval_qwen35_rerank_sweep.yaml
```

## Configs

- `base/qwen36_judge.yaml`
  - Uses `qwen3.6:27b` as the RAGAS judge through `EVAL_LLM_ENDPOINT`.
  - Uses all four metrics: `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`.
  - Use this only when you intentionally want one combined full-metric run.

- `profiles/generation.yaml`
  - Uses the same `qwen3.6:27b` judge.
  - Scores generation quality only: `faithfulness`, `answer_relevancy`.
  - Use this for single-model answer-quality scoring.

- `profiles/retrieval.yaml`
  - Uses the same `qwen3.6:27b` judge.
  - Scores retrieval quality only: `context_precision`, `context_recall`.
  - Use this when retrieval settings, corpus, chunking, or dataset evidence changes.

- `matrices/generation_rerank8.yaml`
  - Uses generation metrics only.
  - Fixes `retrieval.rerank_top_k: 8`.
  - Compares the configured generation models with the same retrieval setting.

- `matrices/retrieval_qwen35_rerank_sweep.yaml`
  - Uses retrieval metrics only.
  - Sweeps `rerank_top_k` for `qwen3.5:4b` labels.

## Recommended Run

Restart the API after code changes because streamed eval needs `/query/stream`
to emit `context`:

```sh
docker compose restart rag-api
```

Generate streamed predictions for the fixed rerank-8 generation matrix:

```sh
sh /app/scripts/eval_generate_matrix.sh \
  evaluation/configs/matrices/generation_rerank8.yaml \
  http://127.0.0.1:8000
```

Score those predictions with generation metrics:

```sh
sh /app/scripts/eval_score_matrix.sh \
  evaluation/configs/matrices/generation_rerank8.yaml
```

For a single model:

```sh
sh /app/scripts/eval_generate_api.sh \
  qwen3.5:4b \
  qwen35_4b_rerank8 \
  evaluation/configs/profiles/generation.yaml \
  http://127.0.0.1:8000

sh /app/scripts/eval_score.sh \
  --latest qwen35_4b_rerank8 \
  evaluation/configs/profiles/generation.yaml
```

Run retrieval scoring separately when needed:

```sh
sh /app/scripts/eval_score.sh \
  --latest qwen35_4b_rerank8 \
  evaluation/configs/profiles/retrieval.yaml
```

## Artifacts

Eval artifacts are grouped by run:

```text
storage/eval_runs/<run_name>/
  run_manifest.json
  predictions/
  scores/
  logs/
```

The manifest is the canonical lookup source for latest prediction and score
artifacts.

## Environment

```text
OPENAI_API_KEY
OLLAMA_LLM_ENDPOINT
EVAL_LLM_ENDPOINT
```
