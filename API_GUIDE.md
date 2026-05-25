# MyRAG API Guide

This guide covers the live API for the MyRAG server.

Base URL:

```text
http://152.118.31.54:8000
```

Swagger UI:

```text
http://152.118.31.54:8000/docs
```

## Quick Reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Check whether the API and vector store are reachable |
| `GET` | `/v1/models` | List the plain LLM model exposed through the wrapper |
| `POST` | `/v1/chat/completions` | Proxy plain chat completions to Ollama |
| `POST` | `/v1/completions` | Proxy plain completions to Ollama |
| `GET` | `/collections` | List indexed Milvus collections |
| `GET` | `/runtime/config` | Show the active collection and ingestion state path used by the running API |
| `GET` | `/ingestion/status` | View ingested files and chunk counts |
| `GET` | `/scraper/sites` | List configured scraper domains and crawl rules |
| `POST` | `/scraper/jobs/configured-site` | Start a scrape job from a configured domain URL |
| `POST` | `/scraper/jobs/urls` | Start a scrape job from explicit URLs |
| `GET` | `/scraper/jobs/{job_id}` | Check scrape job status |
| `POST` | `/scraper/jobs/{job_id}/cancel` | Cancel an active scrape job |
| `POST` | `/query` | Run a standard RAG query |
| `POST` | `/query/stream` | Run a streaming RAG query over SSE |
| `POST` | `/ingest` | Start ingestion for a directory or file path |
| `POST` | `/ingestion/upload` | Upload a PDF or HTML file and ingest it |
| `POST` | `/debug/chunks` | Inspect chunks before embedding |
| `POST` | `/debug/retrieve` | Inspect retrieval output before reranking |
| `POST` | `/debug/rerank` | Inspect reranked results before generation |

## Base Notes

- The API listens on port `8000`.
- Plain LLM wrapper endpoints also live on port `8000`, but they are separate from the RAG contract.
- Use `/v1/chat/completions` or `/v1/completions` for non-RAG callers that just need model inference.
- Use `/query` and `/query/stream` only for retrieval-backed answers.
- `query` endpoints accept optional `metadata_filter`.
- The streaming endpoint returns Server-Sent Events.
- Ingestion runs in the background, so the response comes back before processing finishes.
- Normal ingestion writes one job-level chunk snapshot when `save_snapshots` is enabled.
- Scraping writes source HTML/PDF files into `/app/data`; it does not automatically ingest or rebuild the index.
- Reranking is optional in the server deployment. If `retrieval.reranker_model` is `null` in `config_server.yaml`, the API skips reranker use and you do not need to start the reranker container.
- `confidence_score` is retrieval-strength only. It reflects how strong retrieval evidence is, not factual correctness probability.
- The value is normalized to `0.0`-`1.0` from the top-5 RRF strengths using the current RRF setup (dense+sparse fusion, `k=60`).
- Use `GET /collections` to inspect which Milvus collections are actually present before promotion or cleanup.

## Health And Storage

### `GET /health`
Check whether the API is up and whether the Milvus connection is available.

```bash
curl -X GET http://152.118.31.54:8000/health
```

Example response:

```json
{
  "status": "healthy",
  "milvus": "connected"
}
```

## Plain LLM Wrapper

### `GET /v1/models`
Returns the model currently exposed through the backend wrapper.

```bash
curl -X GET http://152.118.31.54:8000/v1/models
```

### `POST /v1/chat/completions`
Proxy a standard OpenAI-compatible chat request through the backend to Ollama. This is for plain generation only and does not run retrieval.

```bash
curl -X POST http://152.118.31.54:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5:4b","messages":[{"role":"user","content":"Say hello"}]}'
```

If `model` is omitted, the backend uses the current `generation.model_name` from the active runtime config.

### `POST /v1/completions`
Proxy a standard OpenAI-compatible completions request through the backend to Ollama.

```bash
curl -X POST http://152.118.31.54:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Say hello","max_tokens":64}'
```

### `GET /collections`
List the collections currently available in Milvus.

```bash
curl -X GET http://152.118.31.54:8000/collections
```

### `GET /ingestion/status`
View the files already ingested by the pipeline.

```bash
curl -X GET http://152.118.31.54:8000/ingestion/status
```

Example response:

```json
{
  "ingested_files": [],
  "count": 0
}
```

### `GET /runtime/config`
Show which collection and ingestion state path the running API is actually using.

```bash
curl -X GET http://152.118.31.54:8000/runtime/config
```

Example response:

```json
{
  "config_path": "/app/config_rag.yaml",
  "active_collection": "documents_rebuild_20260422_132325",
  "active_collection_present": true,
  "ingestion_state_path": "storage/rebuilds/20260422_132325/ingestion_state.json",
  "available_collections": [
    "documents",
    "documents_rebuild_20260422_132325"
  ]
}
```

## Query

### `POST /query`
Run a standard RAG query. If reranking is enabled in the active config, the server retrieves candidates, reranks them, and returns a grounded answer.

Request body:

```json
{
  "query": "Apa itu mekanisme penelaahan usulan pembukaan program studi?",
  "metadata_filter": null,
  "config_override": null
}
```

Example:

```bash
curl -X POST http://152.118.31.54:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Apa itu mekanisme penelaahan usulan pembukaan program studi?"}'
```

Response shape:

```json
{
  "answer": "...",
  "context": "...",
  "sources": [],
  "metadata": {
    "query": "...",
    "num_docs": 5,
    "confidence_score": 0.82
  }
}
```

### `POST /query/stream`
Run the same query flow, but stream output as SSE events.

```bash
curl -N -X POST http://152.118.31.54:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query":"Jelaskan langkah-langkah akreditasi."}'
```

Use `-N` so `curl` does not buffer the stream.

Stream event order:

```text
data: {"type":"metadata","content":{"num_docs":5,"query":"..."}}
data: {"type":"context","content":"Source [...]..."}
data: {"type":"sources","content":[...]}
data: {"type":"token","content":"..."}
data: {"type":"confidence","content":{"confidence_score":0.82,"query":"..."}}
data: {"type":"timings","content":{"retrieval_time_ms":...,"generation_time_ms":...}}
```

The stream emits the same formatted retrieved context used by the LLM before any answer tokens. Use the `sources` event for user-visible source cards and the `context` event for debugging or evaluation capture.

Each public source object is deduplicated and contains only `pdf_url`, `page_url`, `scraped_at`, `page`, and `pages`. PDF sources use `pdf_url` as the primary source key and collect page numbers in `pages`. Non-PDF page sources use `page_url`; if `page_url` is missing, the API falls back to scraped `source_url` and exposes it as `page_url`. Non-PDF sources return `page: null` and `pages: []`.

The confidence score is retrieval-strength from ranked retrieval evidence. It is deterministic and does not trigger a second LLM confidence check.
It is computed as the average of normalized RRF scores from the top-5 ranked documents, where each item is normalized by the theoretical max fused score: `2/(60+1)`.

## Scraper

The scraper refreshes the raw corpus under `/app/data`. It is intentionally separate from ingestion: scrape first, inspect files/status, then run `/ingest` for incremental updates or the CLI `rebuild-index` flow for a fresh index.

### `GET /scraper/sites`
List the built-in configured sites and crawl rules.

```bash
curl -X GET http://152.118.31.54:8000/scraper/sites
```

Configured domains:

```text
simak.ui.ac.id
www.ui.ac.id
kemahasiswaan.ui.ac.id
beasiswa.ui.ac.id
penerimaan.ui.ac.id
international.ui.ac.id
admission.ui.ac.id
```

`enrollment.ui.ac.id` is intentionally not part of the configured scrape set. The reachable page currently returns an authentication/loading shell instead of useful admission content, so stale `data/enrollment` output should be removed before ingestion.

### `POST /scraper/jobs/configured-site`
Start a scrape using the configured rules for the URL's domain.

```bash
curl -X POST http://152.118.31.54:8000/scraper/jobs/configured-site \
  -H "Content-Type: application/json" \
  -d '{"site_url":"https://simak.ui.ac.id/","dry_run":true}'
```

Set `dry_run` to `false` to write files:

```bash
curl -X POST http://152.118.31.54:8000/scraper/jobs/configured-site \
  -H "Content-Type: application/json" \
  -d '{"site_url":"https://simak.ui.ac.id/","dry_run":false,"skip_existing":false}'
```

Response:

```json
{
  "job_id": "abc123",
  "status": "running",
  "pages_visited": 0,
  "pdfs_downloaded": 0,
  "errors": [],
  "output_dir": "/app/data/simak"
}
```

### `POST /scraper/jobs/urls`
Start a scrape from explicit URLs. One job can target only one domain. Non-UI domains are blocked by default; use `allow_external: true` only for intentional external sources.

```bash
curl -X POST http://152.118.31.54:8000/scraper/jobs/urls \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://simak.ui.ac.id/jadwal-seleksi/",
      "https://simak.ui.ac.id/sk-biaya-pendidikan-ui/"
    ],
    "dry_run": true
  }'
```

### `GET /scraper/jobs/{job_id}`
Check scrape status, counts, current URL, errors, and output folder.

```bash
curl -X GET http://152.118.31.54:8000/scraper/jobs/abc123
```

### `POST /scraper/jobs/{job_id}/cancel`
Cancel a running scrape.

```bash
curl -X POST http://152.118.31.54:8000/scraper/jobs/abc123/cancel
```

### Output Contract

The scraper writes the same file shape ingestion expects:

```text
/app/data/<folder>/<url_path>/page.html
/app/data/<folder>/<url_path>/page.meta.json
/app/data/<folder>/<url_path>/<document>.pdf
/app/data/<folder>/<url_path>/<document>.pdf.meta.json
```

`page.meta.json` contains `source_url`, `domain`, `folder`, `scraped_at`, `status_code`, and `content_type`.
PDF sidecars contain `pdf_url`, `page_url`, `filename`, `domain`, `scraped_at`, `status_code`, and `content_type`.
During ingestion, these sidecar fields are copied into chunk metadata. Query responses and stream source events convert HTML `source_url` into public `page_url` when no explicit `page_url` is available.

After the current configured scrape, the local corpus contains 99 HTML files, 49 PDFs, and 148 metadata JSON files. Re-run scraping only when the source sites need refreshing; otherwise go straight to the rebuild workflow.
The configured `disallowed_paths` rules are intentionally used to exclude noisy or low-signal pages/PDFs from scraping so the downstream index stays focused.

## Ingestion

### `POST /ingest`
Trigger ingestion for a directory path or a single file path. The job runs in the background.

```bash
curl -X POST http://152.118.31.54:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"directory_path":"/app/data"}'
```

Example response:

```json
{
  "status": "ingestion_started",
  "directory": "/app/data",
  "message": "Check container logs for progress."
}
```

Ingestion is incremental and content-aware:

- New or modified files are parsed, chunked, embedded, and inserted into Milvus.
- Unchanged files are skipped without parsing, chunking, or embedding.
- Files with duplicate byte-for-byte content are skipped even when the filename or path is different.
- Duplicate files are recorded as aliases of the canonical document in `storage/ingestion_state.json`.

Use `/ingest` for normal incremental updates. If parsing or chunking behavior changes and the same source files need to be rebuilt, do not wipe the live Milvus collection first. Use the CLI-only `rebuild-index` workflow to build a shadow collection with a fresh state file, validate it, then promote it intentionally.

Before rebuilding after a scrape refresh, verify that unwanted stale folders are gone from `/app/data`. In particular, do not ingest `data/enrollment` unless the enrollment site later exposes crawlable public content.

The tidy rebuild flow stores rebuild artifacts under `storage/rebuilds/YYYYMMDD_HHMMSS/` and the promoted `ingestion.state_path` should normally point at:

```text
storage/rebuilds/YYYYMMDD_HHMMSS/ingestion_state.json
```

Older loose paths such as `storage/ingestion_state_rebuild_YYYYMMDD_HHMMSS.json` are legacy layouts that can still work, but new rebuilds should stay under `storage/rebuilds/...` so the active shadow state and bundle stay together.

When `save_snapshots: true`, each `/ingest` call writes one snapshot file:

```text
storage/snapshots/ingest_job_<timestamp>.json
```

The snapshot is a debug artifact, not the retrieval source of truth. Milvus remains the source used by `/query` and debug retrieval endpoints.

Snapshot entries for processed files include the actual chunk text:

```json
{
  "status": "new",
  "path": "/app/data/example.pdf",
  "doc_id": "doc_ab12cd34ef56",
  "chunk_count": 3,
  "chunks": [
    {
      "chunk_index": 0,
      "text": "Actual chunk text...",
      "page_number": 1,
      "metadata": {}
    }
  ]
}
```

Snapshot entries for unchanged or duplicate files are manifest-only for efficiency. They show the reason and, for duplicates, the canonical document:

```json
{
  "status": "duplicate",
  "path": "/app/data/renamed-example.pdf",
  "canonical_path": "/app/data/example.pdf",
  "canonical_doc_id": "doc_ab12cd34ef56",
  "reason": "same content as canonical file"
}
```

### `POST /ingestion/upload`
Upload one document and immediately queue it for ingestion.

```bash
curl -X POST http://152.118.31.54:8000/ingestion/upload \
  -F "file=@/path/to/document.pdf"
```

Supported uploads are PDF and HTML documents.

## Debugging

### `POST /debug/chunks`
Inspect chunks after parsing and chunking, before embedding.

```bash
curl -X POST http://152.118.31.54:8000/debug/chunks \
  -H "Content-Type: application/json" \
  -d '{"directory_path":"/app/data","save_to_file":false,"output_format":"json"}'
```

Useful when you want to verify chunk boundaries before embedding. PDFs use hierarchical chunking followed by merge-small / split-large normalization, currently `256-1024` token-like units with `120` overlap only when oversized chunks are split; HTML uses standard `1024` chunks with `120` overlap. We use `1024` because `512` chunks were cutting off useful context in practice.

### `POST /debug/retrieve`
Inspect the raw retrieval output after hybrid search and RRF fusion, before reranking.

```bash
curl -X POST http://152.118.31.54:8000/debug/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query":"testing query","k":20,"metadata_filter":null}'
```

### `POST /debug/rerank`
Inspect the reranked candidates before the LLM answer is generated.
This endpoint only works when the reranker service is deployed and the active config points to it.

```bash
curl -X POST http://152.118.31.54:8000/debug/rerank \
  -H "Content-Type: application/json" \
  -d '{"query":"testing query","k":20,"rerank_top_k":5}'
```

## Practical Tips

- Use `/debug/chunks` when you want to confirm how the current chunker behaves on PDFs and HTML.
- Use `/debug/retrieve` when retrieval looks weak but chunking looks fine.
- Use `/debug/rerank` when good chunks are being found but the final ordering looks off.
- For browser testing, open `http://152.118.31.54:8000/docs`.
