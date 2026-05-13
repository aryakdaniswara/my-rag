# Evaluation Configs

The active judge is always `qwen3.6:27b`; configs differ by metric profile,
single-model use case, or model matrix.

## Layout

```text
evaluation/configs/
  base/
    qwen36_judge.yaml
  profiles/
    generation.yaml
    retrieval.yaml
  singles/
    generation_v4_rerank8.yaml
  matrices/
    generation_rerank5.yaml
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

- `singles/generation_v4_rerank8.yaml`
  - Uses generation metrics only.
  - Uses `storage/eval_datasets/main/ui_main_v4.json`.
  - Fixes `retrieval.rerank_top_k: 8`.
  - Use this for a quick one-model check against the expanded v4 dataset.

- `matrices/generation_rerank5.yaml`
  - Uses generation metrics only.
  - Fixes `retrieval.rerank_top_k: 5`.
  - Compares the configured generation models with the same retrieval setting.

- `matrices/retrieval_qwen35_rerank_sweep.yaml`
  - Uses retrieval metrics only.
  - Sweeps `rerank_top_k` for `qwen3.5:4b` labels.

## One-Model v4 Check

Run generation and scoring automatically in one command:

```sh
sh /app/scripts/eval_generate_and_score_api.sh \
  qwen3.5:4b \
  qwen35_4b_v4_rerank8 \
  evaluation/configs/singles/generation_v4_rerank8.yaml \
  http://127.0.0.1:8000
```

To try another model, change only the model and label:

```sh
sh /app/scripts/eval_generate_and_score_api.sh \
  qwen3.5:9b \
  qwen35_9b_v4_rerank8 \
  evaluation/configs/singles/generation_v4_rerank8.yaml \
  http://127.0.0.1:8000
```

## Manual Split

Generate only:

```sh
sh /app/scripts/eval_generate_api.sh \
  qwen3.5:4b \
  qwen35_4b_v4_rerank8 \
  evaluation/configs/singles/generation_v4_rerank8.yaml \
  http://127.0.0.1:8000
```

Score latest generated predictions:

```sh
sh /app/scripts/eval_score.sh \
  --latest qwen35_4b_v4_rerank8 \
  evaluation/configs/singles/generation_v4_rerank8.yaml
```

## Matrix Run

Generate streamed predictions for the recommended generation matrix with `retrieval.rerank_top_k: 5`:

```sh
sh /app/scripts/eval_generate_matrix.sh \
  evaluation/configs/matrices/generation_rerank5.yaml \
  http://127.0.0.1:8000
```

Score those predictions with generation metrics:

```sh
sh /app/scripts/eval_score_matrix.sh \
  evaluation/configs/matrices/generation_rerank5.yaml
```

Generate and score the matrix automatically:

```sh
sh /app/scripts/eval_generate_and_score_matrix.sh \
  evaluation/configs/matrices/generation_rerank5.yaml \
  evaluation/configs/matrices/generation_rerank5.yaml \
  http://127.0.0.1:8000
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

## Timing Fields

- Generation artifacts store per-question retrieval, generation, and end-to-end timings in milliseconds.
- Score-only artifacts reuse those per-question timings and measure only total scoring runtime for the whole scoring job.
- Total runtime is available in both `summary.timings` and `timings.summary` as `total_runtime_ms` and `total_runtime_seconds`.

## Environment

```text
OPENAI_API_KEY
OLLAMA_LLM_ENDPOINT
EVAL_LLM_ENDPOINT
```
