# MyRAG Handover Document

Last validated from this repository: 2026-07-16

This document is the structured handover for the MyRAG repository. It explains what the repository does, what parts exist, how the system works end to end, how to operate it, and what decisions are still open for future development.

Use this as the first document for a new maintainer. The older guides are still useful as references:

- `README.md` for quick commands and high-level notes.
- `DOCUMENTATION.md` for deeper technical design notes.
- `API_GUIDE.md` for endpoint examples.
- `EVALUATION_GUIDE.md` for evaluation workflow.
- `SERVER_DEPLOYMENT_GUIDE.md` for older Docker 20.10 server notes.

## 1. Executive Summary

MyRAG is a modular Retrieval-Augmented Generation system for Universitas Indonesia information. The repository turns crawled or uploaded UI-related HTML/PDF documents into searchable chunks, stores dense and sparse vectors in Milvus, retrieves relevant evidence for a question, optionally reranks the evidence, and asks an OpenAI-compatible LLM endpoint to answer strictly from that retrieved context.

The current project is best understood as a RAG backend and research/evaluation workbench. It is not yet a finished WhatsApp bot, mobile app module, or production customer-support product. Those are possible downstream products, but the repository currently focuses on:

- corpus collection and ingestion,
- hybrid retrieval,
- grounded answer generation,
- API access,
- debugging tools,
- safe index rebuild/promotion,
- evaluation runs and score artifacts.

## 2. What The System Does

The system supports this main lifecycle:

1. Scrape or place UI-related documents under `data/`.
2. Parse HTML/PDF files and split them into chunks.
3. Generate dense and sparse embeddings for each chunk.
4. Store chunks and vectors in Milvus.
5. Accept user questions through CLI or FastAPI.
6. Retrieve candidate chunks using dense + sparse search.
7. Fuse retrieval results with Reciprocal Rank Fusion.
8. Optionally call a separate reranker service.
9. Send the best chunks to an OpenAI-compatible LLM.
10. Return an Indonesian answer, formatted context, source cards, confidence metadata, and timing fields.

The answer prompt is intentionally strict: the assistant is scoped to Universitas Indonesia and must answer only from retrieved context.

## 3. Current Product Boundary

This repository should be handed over as a backend capability, not as a final channel experience.

Current boundary:

- A FastAPI backend on port `8000`.
- A CLI for ingestion, query, debug, rebuild, promotion, and evaluation.
- A Milvus-backed vector index.
- A local or remote OpenAI-compatible generation endpoint.
- Optional external reranker service.
- Scraper jobs for configured UI domains.

Not included yet:

- WhatsApp session management.
- User identity, roles, ticketing workflow, or escalation workflow.
- Frontend/mobile UI.
- Admin CMS for editing approved answers.
- Human-in-the-loop review queue.
- Production auth/rate limiting.
- Long-term monitoring/alerting.

## 4. Architecture At A Glance

```text
UI websites / PDFs / uploads
        |
        v
data/ and uploads/
        |
        v
IngestionPipeline
  - PDF: Docling + hierarchical chunking
  - HTML: Trafilatura + fallback parsing
  - metadata sidecars
  - incremental state and duplicate detection
        |
        v
Dense embedding + sparse embedding
        |
        v
Milvus collection
        |
        v
Retriever
  - dense search
  - sparse search
  - RRF fusion
  - optional HTTP reranker
        |
        v
LLM wrapper
  - OpenAI-compatible chat endpoint
  - strict UI-only prompt
  - Indonesian answer
        |
        v
FastAPI / CLI response
  - answer
  - context
  - public sources
  - retrieval-strength confidence
  - timing metadata
```

## 5. Main Repository Map

| Path | Responsibility |
|---|---|
| `api.py` | FastAPI application, startup lifecycle, query endpoints, scraper endpoints, plain LLM proxy, debug endpoints, upload/ingest endpoints. |
| `pipeline.py` | Main orchestration layer for ingestion, query, streaming query, evaluation, confidence scoring, rebuild-related behavior. |
| `config.py` | Dataclass config model and YAML loading, including `extends` support and environment-variable expansion. |
| `config_rag.yaml` | Local development/default config. Uses local Milvus Lite-style URI by default. |
| `config_server.yaml` | Docker/server config mounted as `/app/config_rag.yaml`. This is usually the active server truth. |
| `docker-compose.yml` | Milvus standalone stack, API container, optional reranker profile, Docker 20.10 workarounds, bind mounts. |
| `Dockerfile` | Python image, CUDA-compatible PyTorch pin for GTX 1080, dependency installation, API entrypoint. |
| `ingestion/` | File parsing, metadata loading, HTML/PDF chunking, ingestion abstractions. |
| `embedding/` | Dense Harrier embedding wrapper and OpenSearch sparse encoder wrapper. |
| `storage/` | Milvus client and persisted artifacts. |
| `retrieval/` | Hybrid retriever, RRF fusion, optional llama.cpp reranker client. |
| `generation/` | LLM wrapper, strict prompts, public source shaping. |
| `scraper_api/` | Configured-site crawler settings and scraper job service. |
| `evaluation/` | RAGAS evaluator and LLM/embedding adapters. |
| `scripts/` | Evaluation shell wrappers. |
| `tests/` | Focused tests for scraper API, source shaping, and retriever source metadata. |

## 6. Runtime Modes And Config Truth

There are two common runtime modes.

| Mode | Config | Typical use |
|---|---|---|
| Local development | `config_rag.yaml` | Running commands directly from the repo. |
| Docker/server | `config_server.yaml` mounted to `/app/config_rag.yaml` | Running `my-rag-api` through Docker Compose. |

Important rule: on the Docker server, the active API reads `RAG_CONFIG_PATH`, which defaults to `/app/config_rag.yaml` inside the container. In the Compose setup, that path is backed by `config_server.yaml`. For server behavior, inspect `docker-compose.yml` plus `config_server.yaml`, not only `config_rag.yaml`.

The API exposes `GET /runtime/config` to check the active collection, ingestion state path, and available Milvus collections.

## 7. Core Configuration

Important config sections:

- `ingestion`: chunk sizes, parser choices, snapshot behavior, incremental state path.
- `embedding`: dense/sparse model names, GPU/CPU placement, quantization, batch size.
- `storage`: Milvus URI, collection base name, active collection name, database name.
- `retrieval`: candidate pool size, rerank top-k, reranker model, reranker endpoint.
- `generation`: OpenAI-compatible endpoint, model name, max tokens, temperature, reasoning effort, system prompt.
- `evaluation`: metrics, dataset path, judge model/endpoint, artifact directories.

Current server config highlights:

- Milvus URI: `http://127.0.0.1:19530`
- Active collection: `documents_rebuild_20260508_080948`
- Ingestion state: `storage/rebuilds/20260508_065352/ingestion_state.json`
- Generation endpoint: `${OLLAMA_LLM_ENDPOINT}`
- Generation model: `qwen3.5:9b`
- Reranker disabled at API level because `retrieval.reranker_model: null`
- Reranker endpoint is still listed, but it is not used unless `reranker_model` is set.

## 8. Data And Scraping

The raw corpus lives under `data/`. The scraper can write:

- `page.html` for HTML pages,
- `page.meta.json` sidecars for HTML pages,
- PDF files beside the referring page,
- `<file>.pdf.meta.json` sidecars for PDFs.

Configured scraper domains live in `scraper_api/sites.py`:

- `simak.ui.ac.id`
- `www.ui.ac.id`
- `kemahasiswaan.ui.ac.id`
- `beasiswa.ui.ac.id`
- `penerimaan.ui.ac.id`
- `international.ui.ac.id`
- `admission.ui.ac.id`

Scraping and ingestion are intentionally separate. Scraping refreshes files under `data/`; ingestion turns those files into indexed vectors. After a scrape, inspect the output before indexing, especially if crawl rules changed.

Key scraper endpoints:

- `GET /scraper/sites`
- `POST /scraper/jobs/configured-site`
- `POST /scraper/jobs/urls`
- `GET /scraper/jobs/{job_id}`
- `POST /scraper/jobs/{job_id}/cancel`

## 9. Ingestion And Indexing

Ingestion is handled by `RAGPipeline.ingest()` and `IngestionPipeline`.

PDF path:

- parsed with Docling,
- chunked with Docling `HierarchicalChunker`,
- normalized with PDF min/max token-like thresholds,
- metadata can include page numbers and source PDF/page URLs.

HTML path:

- parsed with Trafilatura,
- falls back when needed,
- chunked with the standard text chunker,
- preserves crawl metadata from sidecars.

Incremental behavior:

- Files are fingerprinted with SHA-256.
- Unchanged files are skipped.
- Modified files are reprocessed and replace old vectors for that source.
- Duplicate files are recorded as aliases instead of inserting duplicate vectors.
- Optional ingestion snapshots go under `storage/snapshots/`.

Normal ingestion:

```bash
python cli.py ingest --config config_rag.yaml --directory ./data
```

Docker API ingestion:

```bash
curl -X POST http://127.0.0.1:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"directory_path":"/app/data"}'
```

Use normal ingestion when files changed. Use rebuild when parser/chunker/index behavior changed but file bytes are mostly the same.

## 10. Safe Rebuild And Promotion

The safe workflow is shadow-first:

1. Build a new collection with a fresh state file.
2. Validate that collection.
3. Promote by applying the printed config patch.
4. Restart the API if config changed.
5. Clean up old collections only after validation.

Local rebuild:

```bash
python cli.py rebuild-index --config config_rag.yaml --directory ./data
```

Server detached rebuild:

```bash
docker exec -d my-rag-api sh -lc 'python cli.py rebuild-index --config /app/config_rag.yaml --directory /app/data > /app/storage/rebuild-index.log 2>&1'
docker exec -it my-rag-api sh -lc 'tail -f /app/storage/rebuild-index.log'
```

Promote:

```bash
python cli.py promote-index --rebuild-dir storage/rebuilds/YYYYMMDD_HHMMSS
```

List collections:

```bash
python cli.py collections --config storage/rebuilds/YYYYMMDD_HHMMSS/config.yaml
```

Clean up old collection:

```bash
python cli.py cleanup-collection --rebuild-dir storage/rebuilds/YYYYMMDD_HHMMSS --yes
```

Promotion prints the config change; it does not mutate production config automatically.

## 11. Retrieval Pipeline

Retrieval is implemented in `retrieval/retriever.py`.

The default query flow:

1. Dense query embedding with `microsoft/harrier-oss-v1-0.6b`.
2. Sparse query embedding with `opensearch-project/opensearch-neural-sparse-encoding-doc-v3-gte`.
3. Dense search in Milvus using cosine similarity.
4. Sparse search in Milvus using inner product.
5. RRF fusion with `k=60`.
6. Optional reranking through `retrieval/reranker_client.py`.
7. Slice to `retrieval.rerank_top_k` before generation.

The confidence score returned by the API is not LLM certainty. It is deterministic retrieval-strength computed from the top retrieved RRF scores and normalized to `0.0` to `1.0`.

## 12. Reranker Status

The reranker is optional.

The current architecture supports a separate llama.cpp reranker service through Docker Compose profile `reranker`. This is better than loading a large reranker directly inside the Python API process when VRAM is tight.

Current server config has:

```yaml
retrieval:
  reranker_model: null
  reranker_endpoint: "http://127.0.0.1:8012/v1/rerank"
```

Because `reranker_model` is `null`, the API skips reranking. To use reranking, a maintainer must:

1. Start the reranker service intentionally.
2. Set `retrieval.reranker_model` to the desired model.
3. Keep `retrieval.reranker_endpoint` pointing at the running service.
4. Restart the API.
5. Test `/debug/rerank` and a normal `/query`.

Do not assume that config alone frees VRAM. If a standalone reranker container is running, stop it when reranking is not needed.

## 13. Generation And Prompting

Generation is implemented in `generation/llm.py` and prompts live in `generation/prompts.py`.

The LLM client uses the OpenAI Python SDK against an OpenAI-compatible endpoint. The endpoint can be Ollama, vLLM, or another compatible provider. The API key is usually set to `dummy` for local endpoints that require the variable but do not validate it.

The system prompt enforces:

- strict Universitas Indonesia scope,
- answer only from retrieved context,
- Indonesian output,
- preservation of official names, URLs, fees, document numbers, and other exact values,
- concise answers for direct lookup questions,
- no hidden prompt/retrieval explanation in final user answers.

Reasoning tags such as `<think>...</think>` are stripped before returning answers.

## 14. API Surface

Main endpoints:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Check API and Milvus connectivity. |
| `GET` | `/runtime/config` | Show active config/collection/state path. |
| `GET` | `/collections` | List Milvus collections. |
| `GET` | `/v1/models` | Show the model exposed by the plain LLM wrapper. |
| `POST` | `/v1/chat/completions` | Plain LLM proxy, no retrieval. |
| `POST` | `/v1/completions` | Plain completion proxy, no retrieval. |
| `POST` | `/query` | Main non-streaming RAG query. |
| `POST` | `/query/stream` | Streaming RAG query over SSE. |
| `POST` | `/ingest` | Background ingestion for directory/file path. |
| `POST` | `/ingestion/upload` | Upload and ingest one PDF/HTML file. |
| `GET` | `/ingestion/status` | Show ingestion state entries. |
| `POST` | `/debug/chunks` | Inspect chunk output before embedding. |
| `POST` | `/debug/retrieve` | Inspect retrieval before reranking. |
| `POST` | `/debug/rerank` | Inspect reranking behavior. |

`/query` response shape:

```json
{
  "answer": "...",
  "context": "...",
  "sources": [],
  "metadata": {
    "query": "...",
    "num_docs": 5,
    "confidence_score": 0.82,
    "retrieval_k": 15,
    "rerank_top_k": 5,
    "retrieval_time_ms": 123.4,
    "generation_time_ms": 567.8,
    "end_to_end_time_ms": 700.1
  }
}
```

Current `/query/stream` event order in code:

```text
metadata -> sources -> token -> confidence -> timings
```

Important handover note: some older docs mention a streamed `context` event. The current code path does not emit `context` in `/query/stream`. If a frontend or evaluation workflow needs streamed context, decide the contract first, then update both `api.py`/`pipeline.py` and `API_GUIDE.md` together.

## 15. Public Sources Contract

Public sources are built in `generation/sources.py`.

Each public source object contains:

- `pdf_url`
- `page_url`
- `scraped_at`
- `page`
- `pages`

Behavior:

- PDF sources are deduped by normalized `pdf_url` plus page number.
- HTML/page sources are deduped by normalized `page_url`.
- If `page_url` is absent, HTML can fall back to `source_url`.
- Non-PDF sources return `page: null` and `pages: []`.
- Missing URL metadata collapses to a single fallback source object.

Chunk-level internals such as `doc_id`, `chunk_index`, and raw `source_url` should not be exposed as the normal public source card contract.

## 16. CLI Surface

Common commands:

```bash
python cli.py query --config config_rag.yaml --query "..."
python cli.py ingest --config config_rag.yaml --directory ./data
python cli.py find-keyword --config config_rag.yaml --keyword "UKT"
python cli.py trace --config config_rag.yaml --query "..." --check-keyword "UKT"
python cli.py inspect-chunks --config config_rag.yaml --directory ./data
python cli.py debug-query --config config_rag.yaml --query "..."
python cli.py collections --config config_rag.yaml
python cli.py rebuild-index --config config_rag.yaml --directory ./data
python cli.py promote-index --rebuild-dir storage/rebuilds/YYYYMMDD_HHMMSS
python cli.py cleanup-collection --rebuild-dir storage/rebuilds/YYYYMMDD_HHMMSS --yes
```

Evaluation commands are listed in `EVALUATION_GUIDE.md` and `evaluation/configs/README.md`.

## 17. Evaluation

Evaluation uses RAGAS through local adapters in `evaluation/`. The repo separates prediction generation from scoring so expensive generation can be reused.

Key paths:

- datasets: `storage/eval_datasets/`
- configs: `evaluation/configs/`
- scripts: `scripts/eval_*.sh`
- run artifacts: `storage/eval_runs/<run_name>/`
- predictions: `storage/eval_runs/<run_name>/predictions/`
- scores: `storage/eval_runs/<run_name>/scores/`
- logs: `storage/eval_runs/<run_name>/logs/`

Typical server matrix flow:

```bash
sh /app/scripts/eval_generate_matrix.sh evaluation/configs/matrices/generation_rerank5.yaml http://127.0.0.1:8000
sh /app/scripts/eval_score_matrix.sh evaluation/configs/matrices/generation_rerank5.yaml
```

Use generation profiles for answer quality and retrieval profiles for context quality. Do not mix score claims without checking the exact dataset, config, generated predictions, and judge endpoint.

## 18. Deployment Notes

The Docker stack includes:

- `etcd`
- `minio`
- `milvus`
- `rag-api`
- optional `reranker`

The API container uses `network_mode: host` and several Docker 20.10 workarounds:

- `pids_limit: -1`
- `security_opt: seccomp:unconfined`
- no apt-based system dependencies in the Dockerfile
- `PIP_PROGRESS_BAR=off`
- pinned CUDA 11.8 PyTorch for GTX 1080 compatibility

Important mounts:

- `.:/app:rw` for live code in the current Compose file.
- `./data:/app/data:rw` for raw corpus and scraper output.
- `./config_server.yaml:/app/config_rag.yaml` for active server config.
- `./storage/hf_cache:/root/.cache/huggingface` for model cache.
- `./storage/rebuilds:/app/storage/rebuilds` for rebuild bundles.
- `./uploads:/app/uploads:rw` for uploaded documents.

Restart vs rebuild:

- Config/code changes in bind-mounted files usually need container restart.
- Dependency, Dockerfile, or image-level changes need rebuild.
- Collection/state-path changes need config update plus API restart.

## 19. Operational Checks

Use these before and after meaningful changes:

```bash
docker compose ps
docker compose logs --tail=100 rag-api
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/runtime/config
curl http://127.0.0.1:8000/collections
curl http://127.0.0.1:8000/ingestion/status
```

Test a query:

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Apa saja jalur penerimaan mahasiswa baru UI?"}'
```

Test stream:

```bash
curl -N -X POST http://127.0.0.1:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query":"Apa saja jalur penerimaan mahasiswa baru UI?"}'
```

## 20. Debugging Playbook

When answers are wrong, diagnose by stage:

1. Check `/runtime/config` to confirm active collection and state path.
2. Check `/debug/retrieve` to see whether relevant chunks appear before reranking.
3. Check `/debug/rerank` only if reranker is enabled.
4. Check `/query` response `context` to see what the LLM actually received.
5. Check public `sources` to ensure metadata is preserved.
6. If context is good but answer is bad, inspect prompt/generation settings.
7. If context is bad, inspect scraper scope, ingestion chunks, or retrieval config.
8. If ingestion skipped files after chunking/parser changes, use shadow rebuild.

Common failure boundaries:

- Plain `/v1/chat/completions` is not RAG and should not be used to judge retrieval quality.
- `confidence_score` is retrieval-strength, not answer correctness.
- Reranker config and reranker container lifecycle are separate concerns.
- Scraper output does not automatically become searchable until ingestion/rebuild runs.
- Docker server behavior follows `config_server.yaml` mounted as `/app/config_rag.yaml`.

## 21. Known Limitations And Risks

Current limitations:

- The product channel is undecided. The backend can serve many channels, but no final WhatsApp/mobile/web integration is implemented here.
- Current streaming code does not emit `context`, despite older docs mentioning it.
- Local model serving quality and latency depend heavily on the active Ollama/vLLM model and GPU availability.
- Reranking can improve precision but may add latency and VRAM pressure.
- Some docs contain older server assumptions and should be treated as references, not automatically current truth.
- Auth, quota, abuse prevention, and user/session analytics are not implemented.
- Source freshness depends on scrape coverage and rebuild/ingestion discipline.
- Eval scores are only meaningful when dataset, judge, model, config, and prediction artifact are named together.

## 22. Future Development Direction

The next product direction is not finalized. Do not assume the project must become a WhatsApp bot, a mobile-only module, or an entirely local model system. Treat this repo as the RAG backend foundation and decide the channel after requirements are clear.

Reasonable future paths:

| Path | When it makes sense | Main work needed |
|---|---|---|
| API backend for another app | There is already a web/mobile/ticketing system that can call RAG. | Stabilize API contract, auth, rate limit, source-card format, deployment monitoring. |
| WhatsApp bot | Kemahasiswaan wants a conversational public/self-service channel. | Choose WhatsApp provider, conversation flow, escalation rules, answer latency tolerance, source rendering, abuse handling. |
| Mobile app module | UI mobile app already has user context and needs a Q&A feature. | Define mobile API contract, user/session context, source display, caching, telemetry, auth. |
| Internal staff tool | Staff need assisted lookup, not automated public answers. | Add admin UI, review notes, retrieval debug views, manual answer correction workflow. |
| Local/offline deployment | Data sensitivity, budget, or network policy favors self-hosted inference. | Pick smaller models, benchmark quality/latency, simplify GPU allocation, accept slower or lower-quality outputs where necessary. |
| API-model deployment | Reliability, speed, and engineering simplicity matter more than fully local inference. | Budget provider usage, handle provider fallback, privacy review, request logging policy. |

The API-vs-local decision should be a tradeoff, not a slogan.

API model advantages:

- faster to operate,
- less GPU maintenance,
- easier scaling,
- often better quality for generation,
- fewer CUDA/runtime issues.

API model risks:

- ongoing usage cost,
- data governance and privacy review,
- network dependency,
- vendor/provider changes.

Local model advantages:

- better control of data path,
- can be cheaper at low or fixed usage if hardware already exists,
- works for experimentation,
- smaller models may be good enough for scoped UI questions.

Local model risks:

- GPU/VRAM constraints,
- model serving maintenance,
- slower iteration,
- lower quality for some tasks,
- harder production operations.

Recommended decision process:

1. Interview the actual owner/user group first.
2. Collect real historical questions if available.
3. Decide whether the first product is public-facing, staff-facing, or embedded in another app.
4. Define latency tolerance. WhatsApp may tolerate minutes; app search usually should not.
5. Define answer-risk policy for fees, deadlines, payments, and admissions.
6. Decide whether sources must always be visible.
7. Run a small benchmark comparing local small models, local larger models, and API models.
8. Choose the simplest deployment that meets quality, privacy, budget, and maintenance constraints.

Questions to ask stakeholders:

- Who is the primary user?
- What channel do they actually use today?
- What question categories matter most?
- Which answers are high risk and need human review?
- Should the system answer directly, suggest documents, or route to staff?
- How fresh must the data be?
- Who owns scraping and source updates?
- Who approves source domains and exclusions?
- What latency is acceptable?
- What budget exists for model APIs or server maintenance?
- What user data will be sent to the model?
- Is there an existing app, CRM, ticketing system, or WhatsApp provider to integrate with?

## 23. Suggested Next Steps For A New Maintainer

First week:

1. Run the API locally or on the server and verify `/health`.
2. Call `/runtime/config` and write down the active collection and state path.
3. Run one known query through `/query`.
4. Inspect `/debug/retrieve` for that same query.
5. Read `generation/prompts.py` to understand answer constraints.
6. Read `scraper_api/sites.py` to understand corpus scope.
7. Run source-shaping tests:

```bash
python -m unittest discover -s tests -p "test_public_sources.py"
python -m unittest discover -s tests -p "test_retriever_sources.py"
```

Second week:

1. Pick one corpus update or scrape refresh and run it end to end.
2. Run a shadow rebuild instead of editing live collection directly.
3. Generate a small eval artifact and score it.
4. Compare local/API model behavior on the same predictions.
5. Decide whether streaming needs `context` and update code/docs consistently.

Before production handoff:

1. Decide the product channel.
2. Add auth/rate limiting if exposed beyond a trusted network.
3. Add monitoring/log retention.
4. Define data refresh ownership.
5. Define escalation behavior for uncertain or high-risk answers.
6. Freeze a public API contract for the consuming frontend/channel.

## 24. Glossary

| Term | Meaning |
|---|---|
| RAG | Retrieval-Augmented Generation: retrieve evidence first, then generate an answer from that evidence. |
| Chunk | A piece of parsed document text stored and retrieved independently. |
| Dense embedding | Vector representation from a neural embedding model. |
| Sparse embedding | Token-weight representation useful for lexical/term matching. |
| RRF | Reciprocal Rank Fusion, used to combine dense and sparse result rankings. |
| Reranker | A second-stage model that reorders retrieved candidates by relevance. |
| Milvus | Vector database used to store dense/sparse vectors and chunk metadata. |
| Ingestion state | JSON registry tracking file hashes, doc IDs, chunk counts, and aliases. |
| Shadow collection | A newly built collection used for validation before promotion. |
| Public source | Deduplicated source metadata safe to expose to clients. |
| Confidence score | Retrieval-strength score, not answer correctness probability. |
