# Evaluation Guide

This document is the canonical evaluation guide for `my_rag`.

It is written for a research-plus-engineering audience and has two goals:

1. Explain how evaluation works in the current repo today.
2. Define the target "bulletproof" evaluation design we should use for serious claims.

This guide is intentionally explicit about what is already implemented versus what is still a design target. It should not be read as a promise that every recommended capability is already wired into the runtime.

## What "Bulletproof" Means Here

For this repo, "bulletproof" evaluation means:

- the judge is independent from the model being evaluated by default
- the dataset is traceable back to real chunks and real source metadata
- the run is reproducible from recorded config, model identity, and dataset version
- retrieval failures are separated from generation failures instead of being hidden behind a strong judge model
- latency is measured as a first-class output, not as an afterthought
- synthetic data is allowed as a bootstrap, but synthetic-only wins are not treated as final proof

It does not mean "one metric says we are done." A bulletproof eval stack is a collection of evidence, caveats, and artifacts that can survive reruns and scrutiny.

## Current State vs Target State

### Current State in This Repo

- `RAGAS` is the evaluation framework exposed by the current evaluator.
- The evaluator supports the metrics `faithfulness`, `answer_relevancy`, `context_precision`, and `context_recall`.
- The pipeline currently initializes the evaluator with `self.llm.client`, not with an independent judge configured from `config.evaluation`.
- `config.evaluation.eval_llm` and `config.evaluation.eval_embeddings` exist in YAML, but they are not fully wired through the runtime path yet.
- Synthetic QA generation exists, but the generated pairs do not yet carry a full provenance payload such as snapshot path, file path, page metadata, or chunk identifiers.
- Retrieval timing exists today in the `/debug/retrieve` path as `retrieval_time_ms`.
- General end-to-end query timing, generation timing, and time to first token (TTFT) are not yet formalized as stable evaluation outputs.
- There is no stable per-run evaluation bundle format yet.

### Target Bulletproof State

- the judge model is configurable and independent by default
- API-based judge mode is the primary documented path
- generation-under-test and judge configuration are separate concerns
- dataset entries include chunk and source provenance
- latency and TTFT are captured alongside RAGAS results
- evaluation writes a stable JSON report bundle for reproducibility
- failures are categorized with enough evidence to decide whether chunking, retrieval, reranking, or generation is the real problem

## What Counts as Evidence

- RAGAS metrics from a recorded dataset and recorded judge configuration
- retrieval traces showing what was actually retrieved before judging
- source and chunk provenance for each sample
- latency measurements:
  - `retrieval_time_ms`
  - `generation_time_ms`
  - `end_to_end_time_ms`
  - `ttft_ms`
  - `stream_completed`
- failure buckets with an explicit rationale
- stable model identities and dataset versions across comparison runs

## What Does Not Count as Proof

- synthetic-only wins with no reviewed benchmark subset
- self-judged evaluation with no caveat
- one-off anecdotal answers that "look good"
- metric changes after model or config drift without version tracking
- headline RAGAS claims made before retrieval quality is checked

## Supported Evaluation Modes

These are the evaluation modes this guide recognizes. They are not all equally trustworthy.

### 1. Local Generation + API Judge

This is the primary documented path.

Use this when:

- answer generation is still local, for example via Ollama or another OpenAI-compatible local server
- you want a stronger and more stable judge than the generation model under test

Why this is preferred:

- it separates the system under test from the judge
- it allows local generation experiments without forcing local judge quality to be trusted
- it is the most practical path for the repo's current proof-of-concept stage

### 2. API Generation + API Judge

Use this when:

- the model under test is also remote or hosted
- you want clean comparisons between API-served candidates using the same dataset and same judge

Important rule:

- keep the judge model fixed across comparison runs whenever possible

### 3. Local Generation + Local Judge

This is allowed as a fallback, but it is lower trust.

Use it when:

- budget, connectivity, or policy prevents an API judge
- the goal is internal iteration rather than strong external claims

Main caveat:

- the local judge should not be treated as equally strong evidence compared with a stable independent API judge

## Model Selection Guidance

### Generation Model Under Test

The generation model is the model whose answers you are trying to evaluate. It may be:

- local Ollama
- local OpenAI-compatible server
- hosted OpenAI-compatible API

This model should be documented in the report as the system under test.

### Judge Model

The judge model is the model used by `RAGAS` or surrounding evaluation logic to score or interpret outputs.

Recommended default:

- primary path uses an API judge
- keep the judge model stable while changing only the system under test

Do not assume:

- the best answer model is automatically the best judge
- the generation model should judge itself by default

### Evaluation Embeddings

Evaluation embeddings are separate from retrieval embeddings.

Why this matters:

- retrieval uses the repo's dense and sparse retrieval stack
- `RAGAS` may use a different embedding model for metrics like relevancy
- changing evaluation embeddings can move scores even when retrieval and generation are unchanged

Document evaluation embeddings separately from:

- `embedding.dense_model`
- `embedding.sparse_model`

## Bulletproof Workflow

## Phase 1: Build or Select the Dataset

Use a dataset strategy that starts from real repository artifacts instead of hand-wavy examples.

Recommended bootstrap path:

1. Start from ingestion snapshots and actual chunk metadata.
2. Generate synthetic QA from real chunked content.
3. Store provenance with each sample.
4. Review a subset manually and promote it into a benchmark set.

Each dataset entry should eventually carry:

- `question`
- `ground_truth_answer`
- `sample_label`
  - `synthetic_unreviewed`
  - `synthetic_reviewed`
  - `human_authored`
- `doc_id`
- `chunk_index` when available
- `source_path`
- `page_number` when available
- `snapshot_path` or rebuild bundle provenance
- `dataset_version`

Policy:

- synthetic-first is acceptable as the bootstrap path
- strong claims should be based on a reviewed benchmark subset, not synthetic-only results

### Current Gap

Today, synthetic QA generation exists, but it does not yet persist the full provenance payload described above.

## Phase 2: Run Retrieval-First Diagnostics

Do this before making headline RAGAS claims.

Recommended sequence:

1. Inspect chunk quality and source traceability.
2. Use chunk snapshots and debug endpoints to verify that the right evidence exists in the index.
3. Run retrieval-only checks on candidate questions.
4. Decide whether weak outcomes are caused by:
   - chunking
   - retrieval
   - reranking
   - generation

Why this matters:

- a strong judge can make a weak retrieval system look less obviously broken
- answer quality metrics alone do not tell you whether the right chunks were ever retrieved

Useful current repo evidence:

- ingestion snapshots under `storage/snapshots/`
- `/debug/retrieve`
- `/debug/rerank`
- retrieval-strength confidence already returned by the pipeline

## Phase 3: Run Answer-Quality Evaluation with an Independent Judge

Use `RAGAS` as the main framework.

Recommended default:

- evaluate local or API generation with an API-based judge

Required separation:

- system under test != judge model, unless you are explicitly running a lower-trust fallback mode

Document in every report:

- generation model identity
- judge model identity
- evaluation embedding identity
- prompt or config context if it materially affects evaluation

### Current Gap

The current runtime does not yet fully honor this separation. Although `config.evaluation.eval_llm` and `config.evaluation.eval_embeddings` exist, the pipeline currently initializes the evaluator from `self.llm.client`.

## Phase 4: Track Latency as a First-Class Output

Evaluation should include quality and latency together.

Track:

- `retrieval_time_ms`
- `generation_time_ms`
- `end_to_end_time_ms`
- `ttft_ms`
- `stream_completed`

Why TTFT matters:

- two systems can have similar final completion time but feel very different to users
- a streaming system with poor TTFT can still feel sluggish even if total completion time is acceptable

Recommended interpretation:

- `retrieval_time_ms` tells you how much time is spent before generation begins
- `generation_time_ms` shows answer completion cost after retrieval
- `end_to_end_time_ms` is the headline operational latency
- `ttft_ms` captures interactive responsiveness for streaming runs

### Current Gap

The current repo exposes retrieval timing in the debug retrieval path, but does not yet emit a stable eval artifact with all latency fields above.

## Phase 5: Produce a Stable Final Report

Each evaluation run should write one report bundle.

Minimum contents:

- configuration used
- runtime date/time
- generation model under test
- judge model
- evaluation embeddings
- dataset version
- sample counts by label
- RAGAS metrics
- latency summary
- failure analysis
- caveats
- confidence level of the conclusions

Recommended stable output shape:

- one JSON bundle per run
- optional human-readable Markdown summary derived from the JSON bundle

## Implementation Spec for the Target Design

This section defines the code changes needed to make the evaluation stack truly bulletproof. These are target design requirements, not a claim that they are already implemented.

### Required Config Surface

Add or formalize the following `evaluation` fields:

- `judge_mode`
  - recommended values: `api`, `local`, `reuse_generation`
- `eval_llm`
  - judge model identifier
- `eval_llm_endpoint`
  - OpenAI-compatible judge endpoint
- `eval_llm_api_key_env`
  - env var name containing the judge API key
- `eval_embeddings`
  - embedding model used by `RAGAS` eval
- `eval_embeddings_endpoint`
  - optional remote endpoint for evaluation embeddings
- `dataset_path`
  - path to the reviewed or synthetic evaluation dataset artifact
- `report_dir`
  - output directory for stable evaluation result bundles

### Required Runtime Changes

- evaluation config must support independent judge settings instead of silently reusing `self.llm.client`
- wire `evaluation.eval_llm` and `evaluation.eval_embeddings` through the actual runtime path
- support OpenAI-compatible API judge configuration explicitly
- keep generation-under-test and judge configuration separate
- add timing capture for:
  - retrieval
  - generation
  - end to end
  - TTFT for streaming paths
- persist evaluation artifacts with enough provenance to reproduce runs
- ensure synthetic QA generation records source chunk metadata from snapshots or chunk records
- define one stable JSON result bundle per evaluation run

### Explicit Current Gap

Today, the config suggests independent evaluation settings, but the runtime still initializes the evaluator from `self.llm.client` in `pipeline.py`.

## Validation Scenarios the Implementation Must Pass

- local Ollama generation with API judge is reproducible across reruns using the same dataset and config
- API generation with API judge records both model identities clearly
- retrieval misses are classified as retrieval failures rather than generation failures
- strong retrieval but weak answer is classified as generation failure
- synthetic dataset entries preserve source metadata and can be traced back to chunk or snapshot provenance
- `ttft_ms` is reported for streaming runs
- non-streaming runs omit `ttft_ms` or mark it not applicable explicitly
- evaluation fails loudly when judge config is missing instead of silently using the wrong judge
- documentation examples do not claim features that the current code path does not yet implement

## Practical Recommendations for This Repo Right Now

If you are operating `my_rag` today and want the safest path before full eval hardening lands:

1. Keep local generation under test if that matches the real deployment.
2. Prefer an API judge for serious evaluation runs.
3. Start from snapshot-grounded synthetic QA.
4. Manually review a benchmark subset before making strong claims.
5. Run retrieval diagnostics before celebrating RAGAS improvements.
6. Record config, model identities, and dataset version for every run.

## Current Repo Notes

The following behaviors are true today and should shape how you interpret evaluation results:

- the existing CLI `eval` path is minimal and should not yet be treated as the final bulletproof workflow
- the old README example using `python cli.py eval --config config_rag.yaml --synthetic --paths ...` overstates the current CLI surface
- synthetic QA generation is useful for bootstrapping, but it is not yet a fully provenance-rich benchmark builder
- the current documentation should point here for evaluation truth instead of duplicating methodology elsewhere

## Suggested Report Template

Use this structure for human-readable summaries derived from a future stable JSON eval bundle:

1. Evaluation goal
2. System under test
3. Judge and evaluation embeddings
4. Dataset version and sample composition
5. Retrieval diagnostics summary
6. RAGAS metrics
7. Latency and TTFT summary
8. Failure analysis
9. Caveats
10. Bottom-line confidence statement

## Bottom Line

For this repo, the best practical path is:

- local or API generation under test
- API judge as the default
- snapshot-grounded synthetic QA as the bootstrap dataset
- reviewed subset for strong claims
- retrieval-first diagnosis before headline RAGAS conclusions
- stable provenance and latency reporting as mandatory evaluation artifacts
