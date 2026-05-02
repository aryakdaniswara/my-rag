# Evaluation Guide

This document is the canonical evaluation guide for `my_rag`.

It is written for a research-plus-engineering audience and has two goals:

1. Explain how evaluation works in the current repo today.
2. Define the target "bulletproof" evaluation design we should use for serious claims.

This guide is intentionally explicit about what is already implemented versus what is still a design target. It should not be read as a promise that every recommended capability is already wired into the runtime.

Current practical default in this repo:

- evaluation is configured local-first for now
- the judge model defaults to the same local model family as generation
- the evaluation embedding defaults to the same local dense embedding model used by retrieval

That default is pragmatic for early iteration, but it is weaker than the ideal independent API-judge setup described later in this guide.

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
- The pipeline now builds the evaluator from `config.evaluation` rather than silently reusing `self.llm.client`.
- The current config defaults are local-first, so independence is a policy and configuration choice, not an automatic guarantee.
- A bootstrap synthetic dataset now exists at `storage/eval_datasets/snapshot_chunk_synthetic_qa.json`, generated from `snapshot-chunk.json`.
- The current default evaluation dataset is the broader mixed seed `storage/eval_datasets/ui_mixed_seed.json`, and the CLI now loads `evaluation.dataset_path` automatically when `--questions` is omitted.
- The evaluation path now records per-sample `retrieval_time_ms`, `generation_time_ms`, and `end_to_end_time_ms`.
- Evaluation runs now write one JSON bundle per run under `evaluation.report_dir`.
- `ttft_ms` is still not captured in the current non-streaming evaluation path.
- `stream_completed` is documented but not yet populated by the current non-streaming evaluation path.
- `context_recall` is skipped automatically when no ground-truth/reference answers are available.

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

## What Is Fair for This System

For this repo, a fair evaluation setup is not just "more questions." It should reflect the real user job the system is trying to do.

That means:

- broad mixed-document synthetic QA is useful as a bootstrap smoke test
- task-focused benchmarks are better for judging whether the system is actually good at a concrete UI support job

Right now, a more fair short-term benchmark is a mixed seed built from multiple use-case slices such as:

- UKT lookup and tariff interpretation
- rector-decision or policy lookup
- official link or source discovery

Why this is better:

- the questions are closer to how users actually ask
- retrieval quality is tested on the exact chunk shapes that matter
- answer evaluation is less diluted by unrelated document genres
- failures become easier to attribute to chunking, retrieval, table flattening, or answer synthesis

Current repo recommendation:

- keep the broad snapshot-grounded dataset as a bootstrap artifact
- use a mixed seed dataset as the default benchmark for iteration
- keep narrower sub-benchmarks for specific diagnostics like UKT-only or policy-only checks

The current default seed dataset in config is:

- `storage/eval_datasets/ui_mixed_seed.json`

The broader bootstrap artifact remains:

- `storage/eval_datasets/snapshot_chunk_synthetic_qa.json`

## How To Make Synthetic QA Fair

Synthetic QA is useful here, but it becomes misleading if every question is too clean, too literal, or too close to one chunk.

For this system, a fair synthetic benchmark slice should include a mix of:

- direct lookup questions
- paraphrased user-style questions
- source-discovery questions asking where the answer comes from
- boundary questions where the correct answer is "not listed" or "not found in this document"
- comparison questions only if the live product is expected to answer them

It should avoid:

- only copy-paste phrasings from the chunk text
- only single-sentence answers with no ambiguity
- only positive cases where the answer definitely exists
- mixing too many unrelated document types into one tiny dataset and then reporting one headline score
- generic prompts that rely on referents such as `ini`, `itu`, `dokumen ini`, or `lampiran ini`
- questions that omit the concrete entity, program studi, jalur, or tahun akademik needed for retrieval

Practical benchmark design for this repo:

- `UKT / tariff lookup`
  - best for table flattening, retrieval, and exact-answer grounding
- `Rector / policy lookup`
  - best for decree references, legal basis, and citation-style source grounding
- `Official source discovery`
  - best for checking whether the system can point users to the right page or document

Recommended short-term path:

1. Keep `storage/eval_datasets/ui_mixed_seed.json` as the main iteration slice.
2. Keep narrower sub-benchmarks such as `storage/eval_datasets/ukt_fasilkom_seed.json` for targeted regression checks.
3. Review the mixed seed manually before using it for serious claims.

## How RAGAS Actually Works

In this repo, `RAGAS` is not a single magic score. It is a bundle of metric-specific judge workflows.

For the four metrics currently configured here, the judge logic is broadly:

- `faithfulness`
  - decompose the answer into simpler factual statements
  - judge each statement against the retrieved context
  - score = supported statements / total statements
- `answer_relevancy`
  - generate one or more questions that the answer appears to answer
  - embed those generated questions and compare them to the original user question
  - penalize clearly noncommittal answers
- `context_precision`
  - inspect each retrieved chunk and ask whether it was useful for arriving at the answer
  - compute an average-precision-style score so relevant chunks ranked earlier help more
- `context_recall`
  - inspect the reference answer statement by statement
  - judge whether the retrieved context contains support for each statement
  - score = supported reference statements / total reference statements

This is why RAGAS can be powerful but also why it must be explained carefully:

- some metrics are LLM-judge heavy
- some metrics depend on embeddings
- some metrics assume your reference answer is high quality
- some metrics are sensitive to chunk granularity and ranking order

## What the Scores Mean

All four configured metrics are continuous scores from `0.0` to `1.0`, where higher is better, but they do not mean the same thing.

### Faithfulness

Meaning:

- how much of the generated answer is supported by the retrieved context

High score means:

- the answer mostly stays grounded in retrieved evidence

Low score means:

- the answer contains unsupported claims, hallucinated details, or claims that the judge could not infer from context

Important caveat:

- a faithful answer can still be incomplete, unhelpful, or evasive

### Answer Relevancy

Meaning:

- how well the answer actually addresses the user's question

High score means:

- the answer is aligned with the question

Low score means:

- the answer drifts, is generic, or effectively answers another question

Important caveat:

- this metric uses generated reverse-questions plus embedding similarity, so it is not a pure factuality score

### Context Precision

Meaning:

- how well the retrieved ranking places useful chunks near the top

High score means:

- the chunks that actually mattered were ranked early

Low score means:

- useful evidence may exist in the retrieved set, but the ranking is noisy or front-loaded with irrelevant chunks

Important caveat:

- this is very sensitive to chunk granularity and the candidate ordering that reaches the judge

### Context Recall

Meaning:

- whether the retrieved context contains the information needed to support the reference answer

High score means:

- the retrieval stage likely brought back enough supporting evidence

Low score means:

- the system probably missed key evidence, even if the answer sounded plausible

Important caveat:

- this depends heavily on the quality and scope of the reference answer or ground truth

## Upsides and Downsides of RAGAS

### Upsides

- it gives stage-aware signals instead of one monolithic pass/fail judgment
- it can separate retrieval weakness from generation weakness better than answer-only scoring
- it can be run repeatedly across model candidates and config changes
- it can work with synthetic bootstrap datasets before a large human benchmark exists
- it produces richer evidence than anecdotal spot checks

### Downsides

- it is still judge-dependent, so model choice matters
- some metrics are prompt-sensitive
- some metrics are embedding-sensitive
- poor ground truth will poison the evaluation
- synthetic-only datasets can overestimate real-world readiness
- scores can look precise even when the underlying dataset or retrieval setup is weak

## Actual Prompt Sources

This section matters because prompt provenance changes how confidently we can explain the scores.

### What Is the Live Prompt Source

The active prompt logic comes from the installed `ragas` package.

Local runtime snapshot verified in this repo:

- installed `ragas` version: `0.4.3`

For the currently configured metrics in this repo, the live prompt classes are in these package files:

- `.venv/Lib/site-packages/ragas/metrics/_faithfulness.py`
  - `StatementGeneratorPrompt`
  - `NLIStatementPrompt`
- `.venv/Lib/site-packages/ragas/metrics/_answer_relevance.py`
  - `ResponseRelevancePrompt`
- `.venv/Lib/site-packages/ragas/metrics/_context_precision.py`
  - `ContextPrecisionPrompt`
- `.venv/Lib/site-packages/ragas/metrics/_context_recall.py`
  - `ContextRecallClassificationPrompt`

These prompt classes are implemented as structured `PydanticPrompt` objects with:

- an instruction
- typed input schema
- typed output schema
- built-in examples

That is the real prompt source the evaluator should be explained from.

### What The Installed Prompts Actually Ask The Judge To Do

For this repo's current installed `ragas` source, the active prompt behavior is:

- `Faithfulness`
  - `StatementGeneratorPrompt`
  - asks the judge to break the answer into fully understandable statements
  - explicitly tells the judge to avoid pronouns in those statements
  - output is structured JSON statements
- `Faithfulness`
  - `NLIStatementPrompt`
  - asks the judge to decide whether each statement can be directly inferred from the retrieved context
  - output is a per-statement `0` or `1` verdict plus a reason
- `Answer Relevancy`
  - `ResponseRelevancePrompt`
  - asks the judge to generate a question that the answer appears to answer
  - also asks whether the answer is noncommittal, evasive, vague, or ambiguous
  - the metric then combines that output with embedding similarity
- `Context Precision`
  - `ContextPrecisionPrompt`
  - asks the judge whether a given retrieved context was useful in arriving at the answer
  - output is a binary useful/not-useful verdict with a reason
  - the metric then turns those verdicts into an average-precision-style ranking score
- `Context Recall`
  - `ContextRecallClassificationPrompt`
  - asks the judge to analyze each sentence in the reference answer and classify whether it is attributable to the retrieved context
  - output is a per-statement binary attribution with a reason
  - the metric score is the fraction of answer statements supported by retrieval

This is the practical guide to the live prompt flow:

1. `Faithfulness` runs in two prompt stages: statement generation first, then context inference checking.
2. `Answer Relevancy` uses one judge prompt plus embeddings, so it is not a pure LLM-only metric.
3. `Context Precision` and `Context Recall` both rely on binary classification prompts, but they answer different questions:
   - precision asks whether retrieved chunks were useful
   - recall asks whether the reference answer is supported by the retrieved context

If you want to verify the exact prompt wording again later, reopen these installed files directly rather than assuming the upstream docs and your local package are perfectly identical.

### Exact Render Format Used At Runtime

The local `ragas 0.4.3` install does not send only the short `instruction` string.

For these metrics, the prompt is rendered through:

- `.venv/Lib/site-packages/ragas/prompt/pydantic_prompt.py`
- `PydanticPrompt.to_string(data)`

The verified render shape is:

```text
{instruction}
Please return the output in a JSON format that complies with the following schema as specified in JSON Schema:
{output_json_schema}Do not use single quotes in your response but double quotes,properly escaped with a backslash.

--------EXAMPLES-----------
{few_shot_examples}

-----------------------------

Now perform the same with the following input
input: {current_input_json}
Output:
```

That means the exact prompt the judge sees is made of:

- the metric instruction
- the output JSON schema generated from the metric output model
- the built-in few-shot examples from the prompt class
- the current metric input serialized as JSON
- the trailing `Output:` marker

### How To Reproduce The Exact Rendered Prompt Locally

Use the installed prompt classes directly and call `to_string(...)`.

Example pattern:

```python
from ragas.metrics._answer_relevance import ResponseRelevancePrompt, ResponseRelevanceInput

prompt = ResponseRelevancePrompt().to_string(
    ResponseRelevanceInput(
        response="Peraturan Rektor Universitas Indonesia Nomor 2 Tahun 2025 mengatur tentang Biaya Pendidikan."
    )
)
print(prompt)
```

For the currently configured metrics in this repo, the exact render entrypoints are:

- `Faithfulness` statement decomposition
  - `StatementGeneratorPrompt().to_string(StatementGeneratorInput(...))`
- `Faithfulness` statement grounding
  - `NLIStatementPrompt().to_string(NLIStatementInput(...))`
- `Answer Relevancy`
  - `ResponseRelevancePrompt().to_string(ResponseRelevanceInput(...))`
- `Context Precision`
  - `ContextPrecisionPrompt().to_string(QAC(...))`
- `Context Recall`
  - `ContextRecallClassificationPrompt().to_string(QCA(...))`

### Exact Rendered Sample Prompt Verified In This Repo

The following is a full rendered sample prompt captured from the local `ragas 0.4.3` install for `Answer Relevancy`.

Sample input used:

- response: `Peraturan Rektor Universitas Indonesia Nomor 2 Tahun 2025 mengatur tentang Biaya Pendidikan.`

Exact rendered prompt:

```text
Generate a question for the given answer and Identify if answer is noncommittal. Give noncommittal as 1 if the answer is noncommittal and 0 if the answer is committal. A noncommittal answer is one that is evasive, vague, or ambiguous. For example, "I don't know" or "I'm not sure" are noncommittal answers
Please return the output in a JSON format that complies with the following schema as specified in JSON Schema:
{"properties": {"question": {"title": "Question", "type": "string"}, "noncommittal": {"title": "Noncommittal", "type": "integer"}}, "required": ["question", "noncommittal"], "title": "ResponseRelevanceOutput", "type": "object"}Do not use single quotes in your response but double quotes,properly escaped with a backslash.

--------EXAMPLES-----------
Example 1
Input: {
    "response": "Albert Einstein was born in Germany."
}
Output: {
    "question": "Where was Albert Einstein born?",
    "noncommittal": 0
}

Example 2
Input: {
    "response": "I don't know about the  groundbreaking feature of the smartphone invented in 2023 as am unaware of information beyond 2022. "
}
Output: {
    "question": "What was the groundbreaking feature of the smartphone invented in 2023?",
    "noncommittal": 1
}
-----------------------------

Now perform the same with the following input
input: {
    "response": "Peraturan Rektor Universitas Indonesia Nomor 2 Tahun 2025 mengatur tentang Biaya Pendidikan."
}
Output:
```

This sample is enough to show the exact runtime pattern:

1. the short instruction is only the first line
2. `ragas` appends a JSON schema
3. `ragas` appends built-in examples
4. `ragas` appends the current JSON input
5. the final LLM call is made from that full rendered string

The same rendering pipeline applies to the other metrics in this repo; only the instruction text, schema, examples, and input model differ.

### Is It Sourced from Actual RAGAS Documentation?

The safest answer is:

- the canonical behavior comes from the `ragas` package source and official docs together
- the package source is the ground truth for the exact live prompt classes and scoring flow
- the official RAGAS docs explain the conceptual metric purpose, expected inputs, and usage patterns

For this repo, when documenting the exact prompt behavior, prefer the installed package source first because it reflects what the runtime is actually using.

## Metric Caveats You Should Explain Out Loud

When presenting results, do not oversimplify the scores.

### Faithfulness Caveats

- depends on statement decomposition quality
- can under-score answers if the judge fails to decompose correctly
- can over-penalize compressed or implicit wording

### Answer Relevancy Caveats

- mixes judge generation with embedding similarity
- can be affected by the chosen evaluation embedding model
- does not directly prove factual correctness

### Context Precision Caveats

- sensitive to ranking order
- sensitive to chunk size and chunk boundaries
- can look worse even when the right evidence exists but is ranked too low

### Context Recall Caveats

- depends on the reference answer
- can punish retrieval if the reference answer contains claims that are too broad or too detailed for the chosen dataset
- can look artificially good if the reference answer is itself narrow or weak

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

Recommended long-term default:

- primary path uses an API judge
- keep the judge model stable while changing only the system under test

Do not assume:

- the best answer model is automatically the best judge
- the generation model should judge itself by default

Current practical recommendation for this repo:

- keep the local system-under-test comparison narrow: `qwen3.5:2b`, `qwen3.5:4b`, and `qwen3.5:8b`
- keep the judge fixed across those runs instead of changing both generation and judge at once
- current target serious judge is `gemma-4-31b-it`
- for now, use the normal Gemini API/OpenAI-compatible behavior for that judge rather than retrofitting Gemini-specific thinking controls into the repo's current eval path

Current deployment caveat:

- `gemma-4-31b-it` was validated live on the Gemini API and is the selected judge for the next round of comparisons
- Gemini-specific thinking controls were explored, but they are not wired into the repo's current evaluation path
- because of that, do not claim reduced or minimal thinking in eval reports unless the runtime path is later updated and re-verified

Current run layout:

- `evaluation/configs/eval_base_api_judge.yaml` as the canonical comparison baseline
- `evaluation/configs/config_eval_qwen35_8b.yaml` for the `qwen3.5:8b` run
- `evaluation/configs/config_eval_qwen35_4b.yaml` for the `qwen3.5:4b` run
- `evaluation/configs/config_eval_qwen35_2b.yaml` for the `qwen3.5:2b` run
- the per-model configs now inherit from `evaluation/configs/eval_base_api_judge.yaml` and override only the generation model under test
- `config_server.yaml` remains the deployment/runtime config and is no longer the evaluation inheritance root
- all three configs should keep the same judge settings so the comparison stays fair

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

Today, the repo has bootstrap datasets generated from `snapshot-chunk.json`, but they are still `synthetic_unreviewed` and should not be treated as final benchmarks.

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

Recommended long-term default:

- evaluate local or API generation with an API-based judge

Required separation:

- system under test != judge model, unless you are explicitly running a lower-trust fallback mode

Document in every report:

- generation model identity
- judge model identity
- evaluation embedding identity
- prompt or config context if it materially affects evaluation

### Current Gap

The runtime now honors `config.evaluation` directly, but the shipped defaults are still local-first. That means the system can separate the judge from generation by configuration, yet the default setup still uses the same local model family for early iteration.

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

The current repo emits stable JSON eval artifacts and captures non-streaming latency fields, but it still does not capture `ttft_ms` or streaming completion state in the main evaluation path.

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

- evaluation config must continue to support independent judge settings without silently falling back to the generation client
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

Today, the runtime reads evaluation config directly, but the default local-first configuration is still weaker than a truly independent API-judge setup.

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
2. Use the current local-first judge setup for fast iteration, but treat it as lower-trust.
3. Prefer an API judge later for serious comparison runs or thesis-grade claims.
4. Start from snapshot-grounded synthetic QA, then narrow into task-focused benchmark slices.
5. Manually review a benchmark subset before making strong claims.
6. Run retrieval diagnostics before celebrating RAGAS improvements.
7. Record config, model identities, and dataset version for every run.

## Current Repo Notes

The following behaviors are true today and should shape how you interpret evaluation results:

- the existing CLI `eval` path is minimal and should not yet be treated as the final bulletproof workflow
- the current bootstrap dataset artifact is `storage/eval_datasets/snapshot_chunk_synthetic_qa.json`, generated from `snapshot-chunk.json`
- the current default benchmark artifact is `storage/eval_datasets/ui_mixed_seed.json`
- the CLI now supports three practical input paths: `--questions`, `--synthetic`, or the configured `evaluation.dataset_path`
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
- local-first judge for iteration, then API judge for stronger later comparisons
- snapshot-grounded synthetic QA as the bootstrap dataset
- a mixed benchmark spanning multiple chunk sections as the default iteration target
- narrower slice benchmarks such as UKT/FASILKOM for targeted regression checks
- reviewed subset for strong claims
- retrieval-first diagnosis before headline RAGAS conclusions
- stable provenance and latency reporting as mandatory evaluation artifacts

## External References

When you need official upstream references while maintaining this guide, start with:

- RAGAS documentation: `https://docs.ragas.io/`
- RAGAS prompt reference: `https://docs.ragas.io/en/latest/references/prompt/`
- RAGAS GitHub repository: `https://github.com/explodinggradients/ragas`

For exact prompt behavior, verify the installed package source used by this repo before assuming the docs and your runtime are perfectly aligned.
