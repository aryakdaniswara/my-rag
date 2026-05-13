# MyRAG - Modular RAG Pipeline

A production-ready Retrieval-Augmented Generation (RAG) pipeline designed for research and extensibility.

This repo is organized to support two common modes:

- local development with `config_rag.yaml`
- Docker server deployment with `config_server.yaml` mounted as `/app/config_rag.yaml`

## Features

- **Advanced Ingestion**: PDF parsing via Docling with hierarchical-first hybrid chunking that normalizes PDF chunks into a `256-1024` token-like range and uses `120` overlap only when splitting oversized chunks, plus HTML extraction via Trafilatura with `1024` chunks and `120` overlap to reduce cutoff risk observed at `512`.
- **Hybrid Search**: Combines Dense (BGE) and Sparse (SPLADE) embeddings using Milvus.
- **Reranking**: Integration with a dedicated GGUF reranker service to improve retrieval precision.
- **Debuggability**: 
  - `find-keyword`: Locate specific keywords across all stored chunks.
  - `trace`: Verify if retrieved chunks contain specific keywords.
- **Evaluation**: Built-in RAGAS evaluation.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### 1. Configuration
Edit `config_rag.yaml` to set your LLM endpoint, embedding models, and Milvus URI.

### 2. Ingestion
```bash
python cli.py ingest --config config_rag.yaml --directory ./data
```

### 3. Safe index rebuild
When parser or chunker behavior changes, build a shadow collection with a fresh ingestion state instead of wiping the live collection:

```bash
python cli.py rebuild-index --config config_rag.yaml --directory ./data
```

The rebuild now writes a tidy bundle under `storage/rebuilds/<timestamp>/`:

- `config.yaml`
- `ingestion_state.json`
- `rebuild_manifest.json`

After promotion, keep the active shadow state path aligned to that same folder:

```text
storage/rebuilds/YYYYMMDD_HHMMSS/ingestion_state.json
```

Older loose files like `storage/ingestion_state_rebuild_YYYYMMDD_HHMMSS.json` are legacy layouts. They still work if the config points there, but new rebuilds should keep the state file inside the rebuild folder so the bundle stays organized.

If you want to run the rebuild in the background on the server with the current host-networked deployment, use detached `docker exec` inside the already running API container and write logs to shared storage:

```bash
docker exec -d my-rag-api sh -lc 'python cli.py rebuild-index --config /app/config_rag.yaml --directory /app/data > /app/storage/rebuild-index.log 2>&1'
docker exec -it my-rag-api sh -lc 'tail -f /app/storage/rebuild-index.log'
```

The detached `docker compose run -d ...` path may fail on older `docker-compose` versions with this repo's `network_mode: host` setup.

After validation, print the promotion patch from the rebuild folder:

```bash
python cli.py promote-index \
  --rebuild-dir storage/rebuilds/YYYYMMDD_HHMMSS
```

Check the live collections before and after promotion:

```bash
python cli.py collections --config storage/rebuilds/YYYYMMDD_HHMMSS/config.yaml
```

After the rebuilt collection is healthy, clean up the old collection explicitly:

```bash
python cli.py cleanup-collection \
  --rebuild-dir storage/rebuilds/YYYYMMDD_HHMMSS \
  --yes
```

If you also want to remove the old rebuild bundle folder on a Docker server and the host user gets `permission denied`, delete it from inside the running API container:

```bash
docker exec -it my-rag-api sh
rm -rf /app/storage/rebuilds/YYYYMMDD_HHMMSS
```

### 4. Querying
```bash
python cli.py query --config config_rag.yaml --query "What is the main topic?"
```

### 5. Debugging
Find chunks containing a keyword:
```bash
python cli.py find-keyword --config config_rag.yaml --keyword "machine learning"
```

Trace retrieval with a keyword check:
```bash
python cli.py trace --config config_rag.yaml --query "..." --check-keyword "activation"
```

### 5. Evaluation
Evaluation guidance now lives in [EVALUATION_GUIDE.md](./EVALUATION_GUIDE.md).

Use that guide as the canonical source of truth for:

- the current eval truth path and judge config ownership
- how the new run-folder and manifest layout works
- the recommended full-run wrapper plus generate-only and score-only flows
- how to run qwen3.6:27b judging with generation or retrieval metric profiles

For day-to-day iteration, the default evaluation dataset is `storage/eval_datasets/main/ui_main_v3.json`, a 50-row user-like benchmark manually reviewed against the local `/data` corpus. The prior `storage/eval_datasets/main/ui_main_v2.json` remains as a controlled chunk-grounded benchmark for technical comparison. The lighter seed benchmark now lives at `storage/eval_datasets/seeds/ui_seed_v1.json`, while refusal diagnostics are kept separately at `storage/eval_datasets/diagnostics/ui_refusal_v1.json`. Narrower slices such as `storage/eval_datasets/ukt_fasilkom_seed.json` are kept for targeted checks.

Recommended entrypoints:

```bash
sh /app/scripts/eval_generate_matrix.sh evaluation/configs/matrices/generation_rerank5.yaml http://127.0.0.1:8000
sh /app/scripts/eval_score_matrix.sh evaluation/configs/matrices/generation_rerank5.yaml
sh /app/scripts/eval_score.sh --latest qwen35_4b_rerank5 evaluation/configs/profiles/retrieval.yaml
```

The structured eval workspace now lives under `storage/eval_runs/<run_name>/` with:

- `run_manifest.json`
- `predictions/`
- `scores/`
- `logs/`

## Architecture

- `ingestion/`: Document parsing and chunking.
- `embedding/`: Dense and Sparse embedding model wrappers.
- `storage/`: Milvus client and schema management.
- `retrieval/`: Hybrid retriever and reranker.
- `generation/`: LLM interface and prompt templates.
- `evaluation/`: RAGAS metrics and synthetic data generation.
- `debugging/`: Tools for tracing and inspecting chunks.

## Known Limitations

- **Chunker Config**: HTML uses `chunk_size: 1024` and `chunk_overlap: 120`. PDFs use Docling `HierarchicalChunker` plus hybrid normalization with `pdf_min_chunk_tokens: 256`, `pdf_max_chunk_tokens: 1024`, and `pdf_split_overlap_tokens: 120`.
- **VRAM Competition**: Running long-context reranking (8k tokens) on consumer GPUs alongside a large LLM may require careful GPU allocation.
