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
- `evaluation/configs/eval_judge_gemini_api.yaml` for Gemini API judging with `gemini-3.1-flash-lite-preview`

This keeps judge choice out of the main server config so scoring can switch judges cleanly.

## Supported Metrics

The repo still evaluates the same four RAGAS metrics:

- `faithfulness`
- `answer_relevancy`
- `context_precision`
- `context_recall`

This cleanup did not change metric logic or score semantics.

## Dataset Roles

The default headline benchmark is now `storage/eval_datasets/main/ui_main_v3.json`.
It contains 50 answerable, user-like questions manually reviewed against the
local `/data` corpus. The set intentionally mixes admission, SIMAK schedules,
program choices, tuition/registration fees, scholarships, and student/campus
facilities instead of only asking technical document-grounded questions. Each
row keeps a RAGAS reference answer plus source-path/evidence metadata, while
adding `benchmark_split: user_like_main`, `persona`, and `question_style`
fields.

`storage/eval_datasets/main/ui_main_v2.json` is still kept as the controlled
chunk-grounded benchmark for technical comparisons. Refusal and out-of-scope
checks remain outside the headline score in
`storage/eval_datasets/diagnostics/ui_refusal_v1.json`.

This layout follows the thesis evaluation framing: user-like information needs
for the main benchmark, chunk-grounded rows for technical diagnostics, and
separate refusal diagnostics so absent-answer behavior does not distort the
headline RAGAS mean.

Literature anchors for this design:

- Cranfield/TREC evaluation uses a fixed corpus, information needs/topics, and
  relevance judgments for repeatable IR comparison:
  https://www.nist.gov/publications/philosophy-information-retrieval-evaluation
- TREC ad hoc retrieval commonly used 50 natural-language topic statements,
  which supports `~50` as a practical first thesis benchmark size:
  https://pages.nist.gov/trec-browser/trec7/overview/
- Topic-set size affects retrieval experiment error, so results from this
  benchmark should be framed as controlled POC comparison rather than exhaustive
  user coverage:
  https://www.nist.gov/publications/effect-topic-set-size-retrieval-experiment-error
- RAGAS motivates multi-dimensional RAG evaluation across retrieval, grounding,
  and generation quality:
  https://huggingface.co/papers/2309.15217
- ARES supports hybrid RAG evaluation designs that combine synthetic data with a
  smaller reviewed/annotated set:
  https://aclanthology.org/2024.naacl-long.20/
- Recent RAG benchmark work such as mtRAG and UDA reinforces the value of
  realistic or expert-reviewed QA pairs:
  https://research.ibm.com/publications/mtrag-a-multi-turn-conversational-benchmark-for-evaluating-retrieval-augmented-generation-systems--1
  and https://huggingface.co/papers/2406.15187

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

Generate first and automatically score only if generation succeeds:

```sh
sh /app/scripts/eval_generate_and_score_matrix.sh
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

### Generate First, Then Score With Gemini Flash Lite

For only `qwen3.5:2b`, `qwen3.5:4b`, and `qwen3.5:9b` with `rerank_top_k` values `2`, `5`, `8`, and `10`, generate all predictions first:

```sh
EVAL_MODELS="qwen3.5:9b=qwen35_9b qwen3.5:4b=qwen35_4b qwen3.5:2b=qwen35_2b" \
RERANK_TOP_K_VALUES="2 5 8 10" \
sh /app/scripts/eval_generate_matrix.sh config_server.yaml http://127.0.0.1:8000
```

Then score those saved predictions with Gemini:

```sh
EVAL_LABELS="qwen35_9b qwen35_4b qwen35_2b" \
RERANK_TOP_K_VALUES="2 5 8 10" \
sh /app/scripts/eval_score_matrix.sh evaluation/configs/eval_judge_gemini_api.yaml
```

This reuses the saved predictions and avoids regenerating answers during judging.

If you want the same sweep to score automatically right after generation, use the chained wrapper:

```sh
EVAL_MODELS="qwen3.5:9b=qwen35_9b qwen3.5:4b=qwen35_4b qwen3.5:2b=qwen35_2b" \
RERANK_TOP_K_VALUES="2 5 8 10" \
sh /app/scripts/eval_generate_and_score_matrix.sh \
  config_server.yaml \
  evaluation/configs/eval_judge_gemini_api.yaml \
  http://127.0.0.1:8000
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
