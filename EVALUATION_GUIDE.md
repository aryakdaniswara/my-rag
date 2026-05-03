# Evaluation Guide

This document describes the evaluation path that is actually wired in `my_rag` today.

## Runtime Truth Path

The current evaluation flow is:

1. `cli.py`
2. `RAGPipeline.evaluate()` or `RAGPipeline.score_eval_predictions()` in `pipeline.py`
3. `RAGASEvaluator` in `evaluation/evaluator.py`
4. installed `ragas` metric implementations in `.venv/Lib/site-packages/ragas/...`

Important source-of-truth files in this repo:

- `pipeline.py`
- `evaluation/evaluator.py`
- `config.py`
- `config_server.yaml`
- `evaluation/configs/`

## What Is Evaluated

The repo currently exposes four RAGAS metrics:

- `faithfulness`
- `answer_relevancy`
- `context_precision`
- `context_recall`

Configured metrics live under `evaluation.metrics`.

`context_recall` is skipped automatically when the dataset has no reference answer.

## Metric Semantics

### Faithfulness

What it measures:

- Whether the generated answer is supported by the retrieved context.

How it works:

- The judge breaks the answer into atomic statements.
- The judge then checks whether each statement is inferable from the retrieved context.
- The score is the fraction of supported statements.

Interpretation:

- High faithfulness means the answer is grounded.
- Low faithfulness usually means unsupported details, overclaiming, or hallucination.

Important caveat:

- A faithful answer can still be incomplete or fail to answer the user well.

### Answer Relevancy

What it measures:

- Whether the answer addresses the original question.

How it works:

- The judge generates a question that the answer appears to answer.
- That generated question is compared to the original question with embeddings.
- Noncommittal answers are penalized.

Interpretation:

- High answer relevancy means the answer stays on task.
- Low answer relevancy means drift, generic filler, or answering the wrong thing.

Important caveat:

- This is not a factuality metric. It mixes judge output and embedding similarity.

### Context Precision

What it measures:

- Whether useful retrieved chunks are ranked near the top.

How it works:

- The judge checks whether each retrieved context chunk was useful for producing the answer.
- Those binary judgments are converted into an average-precision-style ranking score.

Interpretation:

- High context precision means the ranking is front-loading useful evidence.
- Low context precision means relevant evidence may exist but is buried too low.

Important caveat:

- This metric is very sensitive to chunk boundaries and retrieval ordering.

### Context Recall

What it measures:

- Whether retrieval brought back enough evidence to support the reference answer.

How it works:

- The judge analyzes the reference answer statement by statement.
- The judge checks whether each statement is attributable to the retrieved context.
- The score is the fraction of supported reference statements.

Interpretation:

- High context recall means retrieval likely found enough evidence.
- Low context recall usually points to missing evidence in the retrieved set.

Important caveat:

- This metric depends heavily on reference-answer quality.

## Current Output Artifacts

The workspace is now split into two evaluation artifact folders:

- Scored reports: `storage/eval_results`
- Saved predictions: `storage/eval_predictions`

Why this split exists:

- `eval-generate` creates raw answer artifacts that are useful to score later.
- `eval` and `eval-score` create scored result bundles.
- Mixing those in one folder made the workspace noisy.

Current filename shape:

- scored eval run: `eval_report_<generation_model>_<timestamp>.json`
- scored saved predictions: `eval_score_<generation_model>_<timestamp>.json`
- raw predictions: `eval_predictions_<generation_model_or_label>_<timestamp>.json`
- matrix summary: `eval_matrix_summary_<timestamp>.json`

## What Is At The Top Of Each Scored Report

Every scored report now starts with a `summary` block before the detailed artifacts.

That summary contains:

- `question_count`
- `used_metrics`
- `metric_means`
- `overall_mean_score`
- timing averages
- total runtime
- failure count
- metric caveats
- top-level error if evaluation failed

This is the main block to compare runs quickly.

## Timing Fields

The current non-streaming evaluation path records:

- `retrieval_time_ms`
- `generation_time_ms`
- `end_to_end_time_ms`

The summary also records:

- average retrieval time
- average generation time
- average end-to-end time
- total runtime for the whole evaluation job

Current limitation:

- `ttft_ms` is still not captured in the non-streaming eval path.

## Supported Workflows

### 1. One-Step Eval

This reruns retrieval, generation, and scoring in one command.

```sh
python cli.py eval --config evaluation/configs/eval_base_api_judge.yaml
```

Use this when:

- you want one fresh end-to-end score for the current system under test

### 2. Generate Now, Score Later

This is useful when generation is expensive and you want to rescore with another judge later.

Generate predictions:

```sh
python cli.py eval-generate \
  --config evaluation/configs/eval_base_api_judge.yaml \
  --model qwen3.5:4b \
  --label qwen35_4b
```

Score the saved predictions:

```sh
python cli.py eval-score \
  --config evaluation/configs/eval_example_gemini_api_judge.yaml \
  --predictions storage/eval_predictions/eval_predictions_qwen35_4b_<timestamp>.json
```

### 3. Matrix Eval Across Multiple Models

The repo includes a shared matrix config for:

- `qwen3.5:2b`
- `qwen3.5:4b`
- `qwen3.5:9b`

Run it with:

```sh
python cli.py eval --config evaluation/configs/eval_matrix_qwen35.yaml
```

Or use the helper script:

```sh
sh /app/scripts/eval_matrix.sh
```

The matrix output writes:

- one scored report per model
- one matrix summary file with leaderboards

## Config Examples

Reusable examples now live in `evaluation/configs/`.

Recommended files:

- `eval_base_api_judge.yaml`
  - canonical baseline for model comparisons
- `eval_example_local_judge.yaml`
  - local-only judging example
- `eval_example_gemini_api_judge.yaml`
  - Gemini API judging example with reasoning disabled
- `eval_matrix_qwen35.yaml`
  - shared multi-model comparison config

## Reasoning Control

There are two separate reasoning knobs.

### Generation Reasoning

This controls the model under test:

- config field: `generation.reasoning_effort`
- CLI override for `eval-generate`: `--reasoning-effort`

Example values:

- `none`
- `low`
- `medium`
- `high`

For local Ollama-style generation in this repo, use `none` when you want reasoning off.

### Judge Reasoning

This controls the RAGAS judge path:

- config field: `evaluation.eval_reasoning_effort`
- CLI override for `eval-score`: `--judge-reasoning-effort`

Related flag:

- `evaluation.eval_include_thoughts`
- CLI: `--judge-include-thoughts`

Current Gemini API behavior in this repo:

- If the judge endpoint is the Google OpenAI-compatible endpoint and the judge model name starts with `gemini`, then:
  - `eval_reasoning_effort: none` sends `reasoning_effort: "none"`
  - other values use the Google `thinking_config` path
- Keep `eval_include_thoughts: false` unless you explicitly want thoughts back

For non-Gemini OpenAI-compatible judges, `eval_reasoning_effort` is forwarded as `reasoning_effort`.

## Local Judge vs Gemini Judge

### Local Judge Example

Use `evaluation/configs/eval_example_local_judge.yaml`.

Characteristics:

- `judge_mode: reuse_generation`
- judge uses the same local backend path
- useful for cheap iteration
- weaker for serious comparison claims because judge independence is lower

### Gemini API Judge Example

Use `evaluation/configs/eval_example_gemini_api_judge.yaml`.

Characteristics:

- `judge_mode: api`
- judge model is remote
- generation can stay local
- better for stable model-to-model comparisons

## Live Prompt Provenance

The repo-local `generation/prompts.py` is not the live RAGAS metric prompt source.

The active metric prompts come from the installed `ragas` package.

For the current metrics, the main prompt classes are:

- `.venv/Lib/site-packages/ragas/metrics/_faithfulness.py`
- `.venv/Lib/site-packages/ragas/metrics/_answer_relevance.py`
- `.venv/Lib/site-packages/ragas/metrics/_context_precision.py`
- `.venv/Lib/site-packages/ragas/metrics/_context_recall.py`

That matters because metric behavior should be explained from the installed runtime source, not from placeholder text in this repo.

## Practical Interpretation Rules

When reading results:

- low `context_recall` usually points to retrieval missing evidence
- low `context_precision` usually points to ranking quality
- low `faithfulness` usually points to unsupported answer content
- low `answer_relevancy` usually points to answer drift or weak response targeting

Avoid these mistakes:

- do not treat one metric as a universal quality score
- do not compare runs if you changed both the system under test and the judge at the same time
- do not present synthetic-only results as final proof
- do not ignore latency when two models have similar quality

## Recommendation For This Repo

For current comparison work in this repo:

1. Keep the dataset fixed.
2. Keep the judge fixed.
3. Change only the generation model across `qwen3.5:2b`, `4b`, and `9b`.
4. Compare the top `summary.metric_means` and total runtime first.
5. Open the detailed samples only after the top-line numbers suggest a real difference.
