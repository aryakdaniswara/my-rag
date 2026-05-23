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
    generation_tc_rag_v5.yaml
    retrieval_tc_rag_v5.yaml
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

- `profiles/generation_tc_rag_v5.yaml`
  - Uses generation metrics only.
  - Uses the query-rewritten paired dataset `storage/eval_datasets/query_rewrite/tc-rag-v5.json`.
  - Use this to compare whether query rewriting improves final answer quality.

- `profiles/retrieval_tc_rag_v5.yaml`
  - Uses retrieval metrics only.
  - Uses the query-rewritten paired dataset `storage/eval_datasets/query_rewrite/tc-rag-v5.json`.
  - Use this to compare whether query rewriting improves retrieved context quality.

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

## Qwen 27B Query-Rewrite Complete Curve

Use this additive runner when you want the complete rerank curve for the best
quality model and the practical qwen 9B comparison without changing existing
matrix scripts or baseline artifacts.

Planned experiment grid:

```text
normal ui_main_v5 + qwen3.6:27b:
  rerank_top_k = 3, 8, 10
  rerank_top_k = 5 is not regenerated because the existing baseline is qwen36_27b_rerank5

query rewrite tc-rag-v5 + qwen3.6:27b:
  rerank_top_k = 3, 5, 8, 10

query rewrite tc-rag-v5 + qwen3.5:9b:
  rerank_top_k = 3, 5, 8, 10
```

The runner generates all predictions first, then scores generation quality, then
scores retrieval quality:

```sh
sh /app/scripts/eval_qwen36_query_rewrite_complete_curve.sh \
  http://127.0.0.1:8000
```

For a detached server run:

```sh
docker exec -d my-rag-api sh -lc \
  'cd /app && sh /app/scripts/eval_qwen36_query_rewrite_complete_curve.sh http://127.0.0.1:8000'
```

Target metrics:

- Generation quality: `faithfulness`, `answer_relevancy`, generation overall, generation failure count, non-finite/error count.
- Retrieval quality: `context_precision`, `context_recall`, retrieval overall, retrieval failure count.
- Runtime: retrieval time, generation time, end-to-end time, and TTFT when stream mode is enabled.

The new runner defaults to streamed prediction generation and the streaming API
now emits a `context` event before tokens, so generated prediction artifacts keep
`retrieved_contexts` available for context-based scoring.

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
