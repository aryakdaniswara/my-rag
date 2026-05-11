# Evaluation Dataset Layout

Use simple names plus version numbers:

- `main/ui_main_v3.json`: main user-like benchmark for regular comparisons
- `main/ui_main_v4.json`: expanded answerable snapshot-grounded benchmark for retrieval-aware RAGAS checks; not promoted by default
- `main/ui_main_v2.json`: controlled chunk-grounded benchmark kept for technical comparison
- `diagnostics/ui_refusal_v1.json`: refusal and out-of-scope diagnostic split
- `seeds/ui_seed_v1.json`: lighter seed benchmark for smoke checks
- `archive/snapshot_chunk_seed_v0.json`: older synthetic snapshot-chunk seed kept only for reference

Naming rule:

- `ui_main_vN`: main benchmark promoted for regular comparisons; current promoted set is user-like
- `ui_refusal_vN`: refusal-focused diagnostic benchmark
- `ui_seed_vN`: lighter seed benchmark
- `snapshot_chunk_seed_vN`: archive material from earlier synthetic generation passes

## Ground Truth Design

The main datasets have evolved from plain question-answer pairs into retrieval-aware ground truth rows. The goal is not only to check whether a generated answer sounds correct, but also whether the RAG system retrieves the evidence needed to support it.

For answerable RAGAS datasets:

- `reference` is the concise ideal answer.
- `ground_truth` mirrors `reference` so the eval loader and RAGAS scoring path have a consistent reference answer.
- `answer` may also mirror `reference` in dataset files for compatibility with scripts that expect an answer field.
- `must_include` lists the minimum exact facts a correct answer should contain, such as fees, dates, URLs, program names, or category labels.
- `should_not_include` lists common misleading additions, usually wrong pathways, wrong years, wrong applicant categories, or mixing UKT and IPI.
- `source_evidence` gives a compact trace back to the supporting source text.
- `metadata.source_chunk_ids` records the snapshot chunks that should support the answer.

`scope_category` should describe the actual evidence shape:

- `single_chunk`: the answer is supported by one cited chunk, and top-level `chunk_id` should match that chunk.
- `multi_chunk`: the answer requires at least two relevant chunks, with top-level `chunk_id` set to `null`.
- `cross_section`: the answer compares or combines facts across sections, categories, programs, pathways, or tables, with top-level `chunk_id` set to `null`.

Keep answerable main datasets separate from refusal, unanswerable, and wrong-university diagnostics. Mixing those cases into the main set makes RAGAS scores harder to interpret because retrieval/generation quality and refusal behavior become entangled.
