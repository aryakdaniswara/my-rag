# Evaluation Configs

This folder is the source of truth for reusable evaluation configs.

## Files

- `eval_base_api_judge.yaml`
  - Canonical baseline for local generation under test with an API judge.
- `eval_matrix_qwen35.yaml`
  - Runs one dataset across `qwen3.5:2b`, `qwen3.5:4b`, and `qwen3.5:9b`.
- `eval_example_local_judge.yaml`
  - Example for local-only evaluation where the judge reuses the same local backend.
- `eval_example_gemini_api_judge.yaml`
  - Example for Gemini API judging with reasoning disabled.

## Reasoning Toggle

- Generation reasoning:
  - set `generation.reasoning_effort` to `none`, `low`, `medium`, or `high`
- Judge reasoning:
  - set `evaluation.eval_reasoning_effort`
  - for Gemini OpenAI-compatible judging, `none` disables reasoning in the current repo path
  - keep `evaluation.eval_include_thoughts: false` unless you explicitly want judge thoughts back

## Common Runs

Single model eval:

```sh
python cli.py eval --config evaluation/configs/eval_base_api_judge.yaml
```

Matrix eval for `qwen3.5:2b`, `qwen3.5:4b`, `qwen3.5:9b`:

```sh
python cli.py eval --config evaluation/configs/eval_matrix_qwen35.yaml
```

Generate predictions through the live API, then score later:

```sh
python cli.py eval-generate --config evaluation/configs/eval_base_api_judge.yaml --model qwen3.5:4b --label qwen35_4b
python cli.py eval-score --config evaluation/configs/eval_example_gemini_api_judge.yaml --predictions storage/eval_predictions/eval_predictions_qwen35_4b_<timestamp>.json
```

## Output Folders

- Scored reports: `evaluation.report_dir` default `storage/eval_results`
- Saved predictions: `evaluation.prediction_dir` default `storage/eval_predictions`

Scored reports include the generation model in the filename, for example:

- `storage/eval_results/eval_report_qwen3.5_4b_20260503_...json`
- `storage/eval_results/eval_score_qwen3.5_4b_20260503_...json`
