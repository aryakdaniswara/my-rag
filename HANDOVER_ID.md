# Dokumen Handover MyRAG

Terakhir divalidasi dari repository ini: 2026-07-16

Dokumen ini adalah handover terstruktur untuk repository MyRAG. Isinya menjelaskan fungsi repository, komponen yang tersedia, alur kerja sistem dari awal sampai akhir, cara mengoperasikan sistem, dan keputusan pengembangan yang masih terbuka.

Gunakan dokumen ini sebagai pintu masuk utama untuk maintainer baru. Dokumen lama tetap berguna sebagai referensi:

- `README.md` untuk quickstart dan catatan tingkat tinggi.
- `DOCUMENTATION.md` untuk catatan desain teknis yang lebih dalam.
- `API_GUIDE.md` untuk contoh endpoint.
- `EVALUATION_GUIDE.md` untuk workflow evaluasi.
- `SERVER_DEPLOYMENT_GUIDE.md` untuk catatan server Docker 20.10 yang lebih lama.

## 1. Ringkasan Eksekutif

MyRAG adalah sistem Retrieval-Augmented Generation modular untuk informasi Universitas Indonesia. Repository ini mengambil dokumen UI dari hasil crawl atau upload, terutama HTML dan PDF, lalu mengubahnya menjadi chunk yang bisa dicari, menyimpan dense vector dan sparse vector di Milvus, mengambil evidence yang relevan untuk pertanyaan pengguna, melakukan reranking jika diaktifkan, lalu meminta model LLM OpenAI-compatible menjawab hanya berdasarkan context yang berhasil diambil.

Project ini paling tepat dipahami sebagai backend RAG dan workbench riset/evaluasi. Repository ini belum menjadi bot WhatsApp final, modul aplikasi mobile final, atau produk customer support production-ready. Semua itu bisa menjadi arah lanjutan, tetapi saat ini repository berfokus pada:

- pengumpulan dan ingestion corpus,
- hybrid retrieval,
- grounded answer generation,
- akses API,
- debugging tools,
- safe index rebuild dan promotion,
- evaluation run dan score artifact.

## 2. Fungsi Sistem

Sistem mendukung lifecycle utama berikut:

1. Scrape atau letakkan dokumen terkait UI di bawah `data/`.
2. Parse file HTML/PDF dan pecah menjadi chunk.
3. Buat dense embedding dan sparse embedding untuk setiap chunk.
4. Simpan chunk dan vector ke Milvus.
5. Terima pertanyaan pengguna lewat CLI atau FastAPI.
6. Ambil candidate chunk menggunakan dense + sparse search.
7. Gabungkan hasil retrieval dengan Reciprocal Rank Fusion.
8. Opsional: panggil service reranker terpisah.
9. Kirim chunk terbaik ke LLM OpenAI-compatible.
10. Kembalikan jawaban bahasa Indonesia, formatted context, source card, confidence metadata, dan timing metadata.

Prompt jawaban dibuat ketat: assistant hanya boleh menjawab dalam scope Universitas Indonesia dan hanya berdasarkan retrieved context.

## 3. Batas Produk Saat Ini

Repository ini harus dihandover sebagai kemampuan backend, bukan sebagai channel experience final.

Batas saat ini:

- Backend FastAPI di port `8000`.
- CLI untuk ingestion, query, debug, rebuild, promotion, dan evaluation.
- Vector index berbasis Milvus.
- Endpoint generation lokal atau remote yang OpenAI-compatible.
- Service reranker eksternal yang opsional.
- Scraper job untuk domain UI yang sudah dikonfigurasi.

Yang belum termasuk:

- Manajemen session WhatsApp.
- Identitas pengguna, role, ticketing workflow, atau escalation workflow.
- UI frontend/mobile.
- Admin CMS untuk mengedit approved answer.
- Human-in-the-loop review queue.
- Auth/rate limiting untuk production.
- Monitoring dan alerting jangka panjang.

## 4. Gambaran Arsitektur

```text
Website UI / PDF / upload
        |
        v
data/ dan uploads/
        |
        v
IngestionPipeline
  - PDF: Docling + hierarchical chunking
  - HTML: Trafilatura + fallback parsing
  - metadata sidecar
  - incremental state dan duplicate detection
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
  - jawaban bahasa Indonesia
        |
        v
Response FastAPI / CLI
  - answer
  - context
  - public sources
  - retrieval-strength confidence
  - timing metadata
```

## 5. Peta Repository Utama

| Path | Tanggung jawab |
|---|---|
| `api.py` | Aplikasi FastAPI, startup lifecycle, query endpoint, scraper endpoint, plain LLM proxy, debug endpoint, upload/ingest endpoint. |
| `pipeline.py` | Orkestrasi utama untuk ingestion, query, streaming query, evaluation, confidence scoring, dan rebuild-related behavior. |
| `config.py` | Dataclass config model dan YAML loading, termasuk dukungan `extends` dan ekspansi environment variable. |
| `config_rag.yaml` | Config local development/default. Secara default memakai URI lokal bergaya Milvus Lite. |
| `config_server.yaml` | Config Docker/server yang dimount sebagai `/app/config_rag.yaml`. Biasanya ini source of truth server. |
| `docker-compose.yml` | Stack Milvus standalone, API container, optional reranker profile, workaround Docker 20.10, dan bind mount. |
| `Dockerfile` | Python image, pin PyTorch CUDA-compatible untuk GTX 1080, dependency installation, API entrypoint. |
| `ingestion/` | File parsing, metadata loading, HTML/PDF chunking, ingestion abstraction. |
| `embedding/` | Wrapper dense embedding Harrier dan sparse encoder OpenSearch. |
| `storage/` | Milvus client dan persisted artifact. |
| `retrieval/` | Hybrid retriever, RRF fusion, optional llama.cpp reranker client. |
| `generation/` | LLM wrapper, strict prompt, public source shaping. |
| `scraper_api/` | Configured-site crawler setting dan scraper job service. |
| `evaluation/` | RAGAS evaluator dan adapter LLM/embedding. |
| `scripts/` | Wrapper shell untuk evaluation. |
| `tests/` | Test terfokus untuk scraper API, source shaping, dan retriever source metadata. |

## 6. Runtime Mode Dan Source Of Truth Config

Ada dua mode runtime umum.

| Mode | Config | Penggunaan umum |
|---|---|---|
| Local development | `config_rag.yaml` | Menjalankan command langsung dari repo. |
| Docker/server | `config_server.yaml` dimount ke `/app/config_rag.yaml` | Menjalankan `my-rag-api` lewat Docker Compose. |

Aturan penting: di server Docker, API aktif membaca `RAG_CONFIG_PATH`, yang default-nya adalah `/app/config_rag.yaml` di dalam container. Dalam setup Compose, path itu berasal dari `config_server.yaml`. Untuk menjelaskan behavior server, inspeksi `docker-compose.yml` plus `config_server.yaml`, bukan hanya `config_rag.yaml`.

API menyediakan `GET /runtime/config` untuk mengecek active collection, ingestion state path, dan daftar collection Milvus yang tersedia.

## 7. Konfigurasi Inti

Section config penting:

- `ingestion`: ukuran chunk, pilihan parser, snapshot behavior, incremental state path.
- `embedding`: nama model dense/sparse, penempatan GPU/CPU, quantization, batch size.
- `storage`: URI Milvus, collection base name, active collection name, database name.
- `retrieval`: candidate pool size, rerank top-k, reranker model, reranker endpoint.
- `generation`: endpoint OpenAI-compatible, model name, max tokens, temperature, reasoning effort, system prompt.
- `evaluation`: metrics, dataset path, judge model/endpoint, direktori artifact.

Highlight config server saat ini:

- Milvus URI: `http://127.0.0.1:19530`
- Active collection: `documents_rebuild_20260508_080948`
- Ingestion state: `storage/rebuilds/20260508_065352/ingestion_state.json`
- Generation endpoint: `${OLLAMA_LLM_ENDPOINT}`
- Generation model: `qwen3.5:9b`
- Reranker nonaktif di level API karena `retrieval.reranker_model: null`
- Reranker endpoint masih tertulis, tetapi tidak dipakai kecuali `reranker_model` diisi.

## 8. Data Dan Scraping

Raw corpus berada di bawah `data/`. Scraper dapat menulis:

- `page.html` untuk halaman HTML,
- `page.meta.json` sebagai sidecar halaman HTML,
- file PDF di sebelah halaman referer,
- `<file>.pdf.meta.json` sebagai sidecar PDF.

Domain scraper yang dikonfigurasi berada di `scraper_api/sites.py`:

- `simak.ui.ac.id`
- `www.ui.ac.id`
- `kemahasiswaan.ui.ac.id`
- `beasiswa.ui.ac.id`
- `penerimaan.ui.ac.id`
- `international.ui.ac.id`
- `admission.ui.ac.id`

Scraping dan ingestion sengaja dipisah. Scraping hanya memperbarui file di bawah `data/`; ingestion mengubah file tersebut menjadi vector yang terindeks. Setelah scrape, inspeksi output sebelum indexing, terutama jika crawl rule berubah.

Endpoint scraper utama:

- `GET /scraper/sites`
- `POST /scraper/jobs/configured-site`
- `POST /scraper/jobs/urls`
- `GET /scraper/jobs/{job_id}`
- `POST /scraper/jobs/{job_id}/cancel`

## 9. Ingestion Dan Indexing

Ingestion ditangani oleh `RAGPipeline.ingest()` dan `IngestionPipeline`.

Jalur PDF:

- diparse dengan Docling,
- dichunk dengan Docling `HierarchicalChunker`,
- dinormalisasi dengan threshold min/max token-like untuk PDF,
- metadata dapat memuat page number dan source PDF/page URL.

Jalur HTML:

- diparse dengan Trafilatura,
- memakai fallback bila perlu,
- dichunk dengan standard text chunker,
- mempertahankan crawl metadata dari sidecar.

Behavior incremental:

- File difingerprint dengan SHA-256.
- File unchanged diskip.
- File modified diproses ulang dan menggantikan vector lama untuk source tersebut.
- File duplicate dicatat sebagai alias, bukan dimasukkan sebagai duplicate vector.
- Snapshot ingestion opsional disimpan di `storage/snapshots/`.

Ingestion normal:

```bash
python cli.py ingest --config config_rag.yaml --directory ./data
```

Ingestion lewat Docker API:

```bash
curl -X POST http://127.0.0.1:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"directory_path":"/app/data"}'
```

Gunakan ingestion normal ketika file berubah. Gunakan rebuild ketika behavior parser/chunker/index berubah tetapi byte file sumber mayoritas tetap sama.

## 10. Safe Rebuild Dan Promotion

Workflow yang aman adalah shadow-first:

1. Build collection baru dengan state file baru.
2. Validasi collection tersebut.
3. Promote dengan menerapkan config patch yang dicetak.
4. Restart API jika config berubah.
5. Bersihkan collection lama hanya setelah validasi.

Rebuild lokal:

```bash
python cli.py rebuild-index --config config_rag.yaml --directory ./data
```

Rebuild detached di server:

```bash
docker exec -d my-rag-api sh -lc 'python cli.py rebuild-index --config /app/config_rag.yaml --directory /app/data > /app/storage/rebuild-index.log 2>&1'
docker exec -it my-rag-api sh -lc 'tail -f /app/storage/rebuild-index.log'
```

Promote:

```bash
python cli.py promote-index --rebuild-dir storage/rebuilds/YYYYMMDD_HHMMSS
```

List collection:

```bash
python cli.py collections --config storage/rebuilds/YYYYMMDD_HHMMSS/config.yaml
```

Bersihkan collection lama:

```bash
python cli.py cleanup-collection --rebuild-dir storage/rebuilds/YYYYMMDD_HHMMSS --yes
```

Promotion hanya mencetak perubahan config; command ini tidak mengubah production config secara otomatis.

## 11. Retrieval Pipeline

Retrieval diimplementasikan di `retrieval/retriever.py`.

Alur query default:

1. Dense query embedding dengan `microsoft/harrier-oss-v1-0.6b`.
2. Sparse query embedding dengan `opensearch-project/opensearch-neural-sparse-encoding-doc-v3-gte`.
3. Dense search di Milvus memakai cosine similarity.
4. Sparse search di Milvus memakai inner product.
5. RRF fusion dengan `k=60`.
6. Opsional: reranking lewat `retrieval/reranker_client.py`.
7. Slice ke `retrieval.rerank_top_k` sebelum generation.

Confidence score yang dikembalikan API bukan keyakinan LLM. Nilai itu adalah retrieval-strength deterministik yang dihitung dari top retrieved RRF scores dan dinormalisasi ke `0.0` sampai `1.0`.

## 12. Status Reranker

Reranker bersifat opsional.

Arsitektur saat ini mendukung service reranker llama.cpp terpisah lewat Docker Compose profile `reranker`. Ini lebih sesuai dibanding meload reranker besar langsung di dalam proses Python API ketika VRAM terbatas.

Config server saat ini:

```yaml
retrieval:
  reranker_model: null
  reranker_endpoint: "http://127.0.0.1:8012/v1/rerank"
```

Karena `reranker_model` bernilai `null`, API melewati reranking. Untuk memakai reranking, maintainer harus:

1. Menyalakan service reranker secara sengaja.
2. Mengisi `retrieval.reranker_model` dengan model yang diinginkan.
3. Memastikan `retrieval.reranker_endpoint` menunjuk ke service yang berjalan.
4. Restart API.
5. Test `/debug/rerank` dan `/query` normal.

Jangan menganggap config saja cukup untuk membebaskan VRAM. Jika standalone reranker container masih berjalan, stop container tersebut ketika reranking tidak diperlukan.

## 13. Generation Dan Prompting

Generation diimplementasikan di `generation/llm.py`, dan prompt berada di `generation/prompts.py`.

LLM client memakai OpenAI Python SDK ke endpoint OpenAI-compatible. Endpoint bisa berupa Ollama, vLLM, atau provider lain yang compatible. API key biasanya diset ke `dummy` untuk endpoint lokal yang mensyaratkan variable tersebut tetapi tidak memvalidasinya.

System prompt menegakkan:

- scope ketat Universitas Indonesia,
- jawaban hanya dari retrieved context,
- output bahasa Indonesia,
- preservasi nama resmi, URL, biaya, nomor dokumen, dan exact value lain,
- jawaban singkat untuk lookup langsung,
- tidak menjelaskan hidden prompt/retrieval behavior di final answer pengguna.

Reasoning tag seperti `<think>...</think>` dihapus sebelum jawaban dikembalikan.

## 14. Permukaan API

Endpoint utama:

| Method | Path | Fungsi |
|---|---|---|
| `GET` | `/health` | Mengecek koneksi API dan Milvus. |
| `GET` | `/runtime/config` | Menampilkan active config/collection/state path. |
| `GET` | `/collections` | Menampilkan daftar collection Milvus. |
| `GET` | `/v1/models` | Menampilkan model yang diekspos plain LLM wrapper. |
| `POST` | `/v1/chat/completions` | Plain LLM proxy, tanpa retrieval. |
| `POST` | `/v1/completions` | Plain completion proxy, tanpa retrieval. |
| `POST` | `/query` | Query RAG utama non-streaming. |
| `POST` | `/query/stream` | Query RAG streaming via SSE. |
| `POST` | `/ingest` | Background ingestion untuk directory/file path. |
| `POST` | `/ingestion/upload` | Upload dan ingest satu file PDF/HTML. |
| `GET` | `/ingestion/status` | Menampilkan entry ingestion state. |
| `POST` | `/debug/chunks` | Inspeksi chunk sebelum embedding. |
| `POST` | `/debug/retrieve` | Inspeksi retrieval sebelum reranking. |
| `POST` | `/debug/rerank` | Inspeksi behavior reranking. |

Shape response `/query`:

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

Urutan event `/query/stream` pada kode saat ini:

```text
metadata -> sources -> token -> confidence -> timings
```

Catatan penting handover: beberapa dokumen lama menyebut streamed `context` event. Code path saat ini tidak mengirim `context` di `/query/stream`. Jika frontend atau workflow evaluation membutuhkan streamed context, putuskan kontraknya dulu, lalu update `api.py`/`pipeline.py` dan `API_GUIDE.md` bersama-sama.

## 15. Kontrak Public Sources

Public sources dibuat di `generation/sources.py`.

Setiap object public source berisi:

- `pdf_url`
- `page_url`
- `scraped_at`
- `page`
- `pages`

Behavior:

- Source PDF didedupe berdasarkan normalized `pdf_url` plus page number.
- Source HTML/page didedupe berdasarkan normalized `page_url`.
- Jika `page_url` tidak ada, HTML dapat fallback ke `source_url`.
- Source non-PDF mengembalikan `page: null` dan `pages: []`.
- Metadata tanpa URL digabung ke satu fallback source object.

Internal chunk-level seperti `doc_id`, `chunk_index`, dan raw `source_url` tidak seharusnya diekspos sebagai kontrak source card publik normal.

## 16. Permukaan CLI

Command umum:

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

Command evaluation tersedia di `EVALUATION_GUIDE.md` dan `evaluation/configs/README.md`.

## 17. Evaluation

Evaluation memakai RAGAS melalui adapter lokal di `evaluation/`. Repository memisahkan prediction generation dari scoring agar generation yang mahal bisa dipakai ulang.

Path penting:

- dataset: `storage/eval_datasets/`
- config: `evaluation/configs/`
- script: `scripts/eval_*.sh`
- run artifact: `storage/eval_runs/<run_name>/`
- prediction: `storage/eval_runs/<run_name>/predictions/`
- score: `storage/eval_runs/<run_name>/scores/`
- log: `storage/eval_runs/<run_name>/logs/`

Flow matrix umum di server:

```bash
sh /app/scripts/eval_generate_matrix.sh evaluation/configs/matrices/generation_rerank5.yaml http://127.0.0.1:8000
sh /app/scripts/eval_score_matrix.sh evaluation/configs/matrices/generation_rerank5.yaml
```

Gunakan generation profile untuk kualitas jawaban dan retrieval profile untuk kualitas context. Jangan mencampur klaim score tanpa menyebut dataset, config, generated prediction, dan judge endpoint yang tepat.

## 18. Catatan Deployment

Stack Docker berisi:

- `etcd`
- `minio`
- `milvus`
- `rag-api`
- optional `reranker`

API container memakai `network_mode: host` dan beberapa workaround Docker 20.10:

- `pids_limit: -1`
- `security_opt: seccomp:unconfined`
- tidak ada system dependency berbasis apt di Dockerfile
- `PIP_PROGRESS_BAR=off`
- pinned PyTorch CUDA 11.8 untuk kompatibilitas GTX 1080

Mount penting:

- `.:/app:rw` untuk live code pada Compose file saat ini.
- `./data:/app/data:rw` untuk raw corpus dan scraper output.
- `./config_server.yaml:/app/config_rag.yaml` untuk active server config.
- `./storage/hf_cache:/root/.cache/huggingface` untuk model cache.
- `./storage/rebuilds:/app/storage/rebuilds` untuk rebuild bundle.
- `./uploads:/app/uploads:rw` untuk uploaded document.

Restart vs rebuild:

- Perubahan config/code pada file bind-mounted biasanya butuh restart container.
- Perubahan dependency, Dockerfile, atau image-level butuh rebuild.
- Perubahan collection/state-path butuh update config plus restart API.

## 19. Operational Checks

Gunakan command berikut sebelum dan sesudah perubahan penting:

```bash
docker compose ps
docker compose logs --tail=100 rag-api
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/runtime/config
curl http://127.0.0.1:8000/collections
curl http://127.0.0.1:8000/ingestion/status
```

Test query:

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

Ketika jawaban salah, diagnosis per stage:

1. Cek `/runtime/config` untuk memastikan active collection dan state path.
2. Cek `/debug/retrieve` untuk melihat apakah chunk relevan muncul sebelum reranking.
3. Cek `/debug/rerank` hanya jika reranker aktif.
4. Cek response `/query` bagian `context` untuk melihat apa yang benar-benar diterima LLM.
5. Cek public `sources` untuk memastikan metadata terjaga.
6. Jika context bagus tetapi jawaban buruk, inspeksi prompt/generation setting.
7. Jika context buruk, inspeksi scraper scope, ingestion chunks, atau retrieval config.
8. Jika ingestion melewati file setelah perubahan chunking/parser, gunakan shadow rebuild.

Batas kegagalan umum:

- Plain `/v1/chat/completions` bukan RAG dan tidak boleh dipakai untuk menilai kualitas retrieval.
- `confidence_score` adalah retrieval-strength, bukan kebenaran jawaban.
- Config reranker dan lifecycle container reranker adalah dua hal terpisah.
- Output scraper tidak otomatis searchable sampai ingestion/rebuild berjalan.
- Behavior server Docker mengikuti `config_server.yaml` yang dimount sebagai `/app/config_rag.yaml`.

## 21. Limitasi Dan Risiko Yang Diketahui

Limitasi saat ini:

- Channel produk belum diputuskan. Backend bisa melayani banyak channel, tetapi belum ada integrasi final WhatsApp/mobile/web di repo ini.
- Kode streaming saat ini tidak mengirim `context`, meskipun beberapa dokumen lama pernah menyebutnya.
- Kualitas dan latency local model serving sangat bergantung pada model Ollama/vLLM aktif dan ketersediaan GPU.
- Reranking bisa meningkatkan presisi, tetapi dapat menambah latency dan tekanan VRAM.
- Beberapa dokumen memuat asumsi server lama dan harus diperlakukan sebagai referensi, bukan kebenaran runtime otomatis.
- Auth, quota, abuse prevention, dan user/session analytics belum diimplementasikan.
- Freshness source bergantung pada coverage scrape dan disiplin rebuild/ingestion.
- Eval score hanya bermakna ketika dataset, judge, model, config, dan prediction artifact disebut bersama.

## 22. Arah Pengembangan Lanjutan

Arah produk berikutnya belum final. Jangan menganggap project ini harus menjadi bot WhatsApp, modul mobile-only, atau sistem yang sepenuhnya local model. Perlakukan repo ini sebagai fondasi backend RAG, lalu tentukan channel setelah kebutuhan jelas.

Pilihan arah yang masuk akal:

| Arah | Kapan masuk akal | Pekerjaan utama |
|---|---|---|
| API backend untuk app lain | Sudah ada web/mobile/ticketing system yang bisa memanggil RAG. | Stabilkan kontrak API, auth, rate limit, format source-card, deployment monitoring. |
| Bot WhatsApp | Kemahasiswaan membutuhkan channel percakapan public atau self-service. | Pilih WhatsApp provider, conversation flow, escalation rule, toleransi latency jawaban, rendering source, abuse handling. |
| Modul aplikasi mobile | Aplikasi mobile UI sudah punya user context dan butuh fitur Q&A. | Definisikan kontrak API mobile, user/session context, tampilan source, caching, telemetry, auth. |
| Internal staff tool | Staff butuh assisted lookup, bukan automated public answer. | Tambah admin UI, review note, retrieval debug view, manual answer correction workflow. |
| Local/offline deployment | Data sensitivity, budget, atau network policy lebih cocok self-hosted inference. | Pilih model lebih kecil, benchmark quality/latency, sederhanakan alokasi GPU, terima output yang mungkin lebih lambat atau lebih rendah kualitasnya bila masih memenuhi kebutuhan. |
| API-model deployment | Reliability, speed, dan kemudahan maintenance lebih penting daripada fully local inference. | Siapkan budget provider, provider fallback, privacy review, request logging policy. |

Keputusan API-vs-local harus berupa tradeoff, bukan slogan.

Kelebihan API model:

- lebih cepat dioperasikan,
- maintenance GPU lebih sedikit,
- scaling lebih mudah,
- sering lebih bagus untuk generation,
- lebih sedikit masalah CUDA/runtime.

Risiko API model:

- biaya usage berkelanjutan,
- perlu review data governance dan privacy,
- bergantung pada network,
- perubahan vendor/provider.

Kelebihan local model:

- kontrol data path lebih kuat,
- bisa lebih murah untuk usage rendah atau fixed jika hardware sudah tersedia,
- cocok untuk eksperimen,
- model kecil bisa cukup bagus untuk pertanyaan UI yang scoped.

Risiko local model:

- constraint GPU/VRAM,
- maintenance model serving,
- iterasi lebih lambat,
- kualitas bisa lebih rendah untuk beberapa task,
- operasi production lebih sulit.

Proses keputusan yang direkomendasikan:

1. Interview owner/user group yang sebenarnya.
2. Kumpulkan riwayat pertanyaan nyata jika tersedia.
3. Putuskan apakah produk pertama public-facing, staff-facing, atau embedded di app lain.
4. Definisikan toleransi latency. WhatsApp mungkin menoleransi hitungan menit; app search biasanya tidak.
5. Definisikan answer-risk policy untuk biaya, deadline, pembayaran, dan admissions.
6. Putuskan apakah source harus selalu terlihat.
7. Jalankan benchmark kecil yang membandingkan local small model, local larger model, dan API model.
8. Pilih deployment paling sederhana yang memenuhi quality, privacy, budget, dan maintenance constraint.

Pertanyaan untuk stakeholder:

- Siapa pengguna utama?
- Channel apa yang benar-benar mereka gunakan sekarang?
- Kategori pertanyaan apa yang paling penting?
- Jawaban mana yang high risk dan perlu human review?
- Apakah sistem harus menjawab langsung, menyarankan dokumen, atau route ke staff?
- Seberapa fresh data harus dijaga?
- Siapa pemilik scraping dan source update?
- Siapa yang menyetujui source domain dan exclusion?
- Latency seperti apa yang dapat diterima?
- Budget apa yang tersedia untuk model API atau server maintenance?
- Data pengguna apa yang akan dikirim ke model?
- Apakah sudah ada app, CRM, ticketing system, atau WhatsApp provider untuk integrasi?

## 23. Langkah Lanjutan Untuk Maintainer Baru

Minggu pertama:

1. Jalankan API lokal atau di server dan verifikasi `/health`.
2. Panggil `/runtime/config` dan catat active collection serta state path.
3. Jalankan satu known query lewat `/query`.
4. Inspeksi `/debug/retrieve` untuk query yang sama.
5. Baca `generation/prompts.py` untuk memahami constraint jawaban.
6. Baca `scraper_api/sites.py` untuk memahami scope corpus.
7. Jalankan source-shaping tests:

```bash
python -m unittest discover -s tests -p "test_public_sources.py"
python -m unittest discover -s tests -p "test_retriever_sources.py"
```

Minggu kedua:

1. Pilih satu corpus update atau scrape refresh dan jalankan end to end.
2. Jalankan shadow rebuild, bukan mengedit live collection langsung.
3. Generate eval artifact kecil dan score artifact tersebut.
4. Bandingkan behavior local/API model pada prediction yang sama.
5. Putuskan apakah streaming membutuhkan `context` dan update code/docs secara konsisten.

Sebelum production handoff:

1. Putuskan product channel.
2. Tambahkan auth/rate limiting jika diekspos di luar trusted network.
3. Tambahkan monitoring/log retention.
4. Definisikan kepemilikan data refresh.
5. Definisikan escalation behavior untuk jawaban uncertain atau high-risk.
6. Freeze kontrak API publik untuk frontend/channel consumer.

## 24. Glosarium

| Istilah | Arti |
|---|---|
| RAG | Retrieval-Augmented Generation: mengambil evidence dulu, lalu menghasilkan jawaban dari evidence tersebut. |
| Chunk | Potongan teks dokumen yang disimpan dan diretrieve secara independen. |
| Dense embedding | Representasi vector dari neural embedding model. |
| Sparse embedding | Representasi token-weight yang berguna untuk lexical/term matching. |
| RRF | Reciprocal Rank Fusion, dipakai untuk menggabungkan ranking dense dan sparse retrieval. |
| Reranker | Model second-stage yang menyusun ulang candidate hasil retrieval berdasarkan relevansi. |
| Milvus | Vector database untuk menyimpan dense/sparse vector dan metadata chunk. |
| Ingestion state | Registry JSON yang melacak file hash, doc ID, chunk count, dan alias. |
| Shadow collection | Collection baru yang dibuat untuk validasi sebelum promotion. |
| Public source | Metadata source yang sudah didedupe dan aman diekspos ke client. |
| Confidence score | Retrieval-strength score, bukan probabilitas kebenaran jawaban. |
