from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Response
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any
from pathlib import Path
import os
import re
import logging
import json
import time

import httpx

from pipeline import RAGPipeline
from config import RAGConfig
from generation import LLM
from scraper_api import ScrapeConfig, ScraperJobManager
from scraper_api.sites import (
    config_from_configured_site,
    config_from_urls,
    list_configured_sites,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-api")

# ── Global pipeline instance ──────────────────────────────────────────────────
rag_pipeline: Optional[RAGPipeline] = None
llm_proxy_client: Optional[httpx.AsyncClient] = None
scraper_manager = ScraperJobManager(logger_=logging.getLogger("rag-api.scraper"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown using the modern FastAPI lifespan pattern."""
    global rag_pipeline, llm_proxy_client
    config_path = os.getenv("RAG_CONFIG_PATH", "config_rag.yaml")
    llm_proxy_client = httpx.AsyncClient(timeout=300.0)

    # Retry loop — Milvus may still be warming up even after its healthcheck
    # passes. We retry up to 5 times (50 seconds total) before giving up.
    max_attempts = 5
    retry_delay = 10  # seconds

    for attempt in range(1, max_attempts + 1):
        try:
            if not os.path.exists(config_path):
                logger.error(f"Config file not found: {config_path}")
                break

            config = RAGConfig.from_yaml(config_path)
            rag_pipeline = RAGPipeline.from_config(config)
            logger.info(f"RAG Pipeline initialized from {config_path} (attempt {attempt})")
            break  # success — exit the retry loop

        except Exception as e:
            logger.warning(
                f"Pipeline init attempt {attempt}/{max_attempts} failed: {e}"
            )
            if attempt < max_attempts:
                import asyncio
                logger.info(f"Retrying in {retry_delay}s ...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(
                    "Pipeline failed to initialize after all retry attempts. "
                    "Check Milvus logs: docker compose logs milvus",
                    exc_info=True,
                )

    yield  # Application runs here

    logger.info("RAG API shutting down.")
    await scraper_manager.shutdown()
    if llm_proxy_client is not None:
        await llm_proxy_client.aclose()


app = FastAPI(
    title="MyRAG System API",
    description=(
        "High-performance RAG pipeline using Harrier (dense), "
        "OpenSearch (sparse) with RRF fusion, and Jina-v3 listwise reranker."
    ),
    version="0.2.0",
    lifespan=lifespan,
)


# ── Request / Response schemas ────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str
    config_override: Optional[Dict[str, Any]] = None
    metadata_filter: Optional[Dict[str, Any]] = None

    model_config = {"json_schema_extra": {"example": {"query": "Apa itu mekanisme penelaahan usulan pembukaan program studi?"}}}


class IngestRequest(BaseModel):
    directory_path: str

    model_config = {"json_schema_extra": {"example": {"directory_path": "/app/data"}}}


class ScrapeJobRequest(BaseModel):
    domain: str
    folder: str
    seeds: List[str]
    allowed_paths: List[str] = Field(default_factory=list)
    disallowed_paths: List[str] = Field(default_factory=list)
    max_depth: int = 3
    max_parallelism: int = 2
    rate_limit_ms: int = 1000
    user_agent: str = "UI-RAG-Scraper/1.0"
    skip_existing: bool = False
    dry_run: bool = False
    output_dir: str = "/app/data"

    model_config = {
        "json_schema_extra": {
            "example": {
                "domain": "simak.ui.ac.id",
                "folder": "simak",
                "seeds": ["https://simak.ui.ac.id/"],
                "allowed_paths": ["/"],
                "disallowed_paths": ["/wp-admin"],
                "max_depth": 2,
                "max_parallelism": 2,
                "rate_limit_ms": 1000,
                "skip_existing": True,
                "dry_run": False,
                "output_dir": "/app/data",
            }
        }
    }


class ScrapeUrlsJobRequest(BaseModel):
    urls: List[str]
    allow_external: bool = False
    folder: Optional[str] = None
    output_dir: str = "/app/data"
    max_depth: int = 2
    max_parallelism: int = 2
    rate_limit_ms: int = 1000
    user_agent: str = "UI-RAG-Scraper/1.0"
    skip_existing: bool = True
    dry_run: bool = False
    disallowed_paths: List[str] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "example": {
                "urls": [
                    "https://simak.ui.ac.id/jadwal-seleksi/",
                    "https://simak.ui.ac.id/sk-biaya-pendidikan-ui/",
                ],
                "dry_run": True,
                "allow_external": False,
                "output_dir": "/app/data",
            }
        }
    }


class ScrapeConfiguredSiteJobRequest(BaseModel):
    site_url: str
    output_dir: str = "/app/data"
    skip_existing: bool = True
    dry_run: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {
                "site_url": "https://simak.ui.ac.id/",
                "dry_run": True,
                "output_dir": "/app/data",
            }
        }
    }


class RAGResponse(BaseModel):
    answer: str
    context: str
    sources: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class LLMModelsResponse(BaseModel):
    object: str
    data: List[Dict[str, Any]]


class LLMChatMessage(BaseModel):
    role: str
    content: Any

    model_config = ConfigDict(extra="allow")


class LLMChatCompletionsRequest(BaseModel):
    model: Optional[str] = None
    messages: List[LLMChatMessage]
    max_tokens: Optional[int] = None
    stream: bool = False
    reasoning_effort: Optional[Any] = None

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "model": "qwen3.5:4b",
                "messages": [
                    {"role": "user", "content": "Say hello in one short sentence."}
                ],
                "reasoning_effort": "none",
                "stream": False,
            }
        },
    )


class LLMCompletionsRequest(BaseModel):
    model: Optional[str] = None
    prompt: Any
    max_tokens: Optional[int] = None
    stream: bool = False
    reasoning_effort: Optional[Any] = None

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "model": "qwen3.5:4b",
                "prompt": "Say hello in one short sentence.",
                "reasoning_effort": "none",
                "stream": False,
            }
        },
    )


# ── Debug Request / Response schemas ───────────────────────────────────────────
class DebugChunksRequest(BaseModel):
    directory_path: str
    save_to_file: Optional[bool] = False
    output_format: Optional[str] = "json"  # json or txt


class ChunkInfo(BaseModel):
    id: int
    doc_id: str
    chunk_index: int
    text: str
    pdf_url: Optional[str] = None
    page_url: Optional[str] = None
    scraped_at: Optional[str] = None
    page_number: int
    char_count: int
    token_count: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class DebugChunksResponse(BaseModel):
    chunks: List[ChunkInfo]
    total_chunks: int
    processing_time_ms: float


class DebugRetrieveRequest(BaseModel):
    query: str
    k: Optional[int] = 20
    metadata_filter: Optional[Dict[str, Any]] = None


class RetrievedDocInfo(BaseModel):
    text: str
    doc_id: str
    chunk_index: int
    rrf_score: float
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    pdf_url: Optional[str] = None
    page_url: Optional[str] = None
    scraped_at: Optional[str] = None
    page_number: int


class DebugRetrieveResponse(BaseModel):
    query: str
    retrieved_docs: List[RetrievedDocInfo]
    total_candidates: int
    retrieval_time_ms: float


class DebugRerankRequest(BaseModel):
    query: str
    k: Optional[int] = 20
    rerank_top_k: Optional[int] = 5


class RerankedDocInfo(BaseModel):
    text: str
    doc_id: str
    chunk_index: int
    rrf_score: float
    rerank_score: float
    final_score: float
    pdf_url: Optional[str] = None
    page_url: Optional[str] = None
    scraped_at: Optional[str] = None
    page_number: int


class DebugRerankResponse(BaseModel):
    query: str
    reranked_docs: List[RerankedDocInfo]
    rerank_time_ms: float


# ── Helpers ───────────────────────────────────────────────────────────────────
def strip_thought_process(text: str) -> str:
    """Remove <think>...</think> blocks emitted by reasoning models (Qwen, DeepSeek)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _load_runtime_config() -> RAGConfig:
    if rag_pipeline:
        return rag_pipeline.config

    config_path = os.getenv("RAG_CONFIG_PATH", "config_rag.yaml")
    if not os.path.exists(config_path):
        raise HTTPException(status_code=503, detail="Runtime config not found")
    return RAGConfig.from_yaml(config_path)


def _extract_generation_override(config_override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(config_override, dict):
        return {}

    generation_override = config_override.get("generation")
    if isinstance(generation_override, dict):
        return generation_override

    direct_keys = {
        "llm_endpoint",
        "model_name",
        "max_tokens",
        "temperature",
        "reasoning_effort",
        "system_prompt",
    }
    return {key: value for key, value in config_override.items() if key in direct_keys}


def _extract_retrieval_override(config_override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(config_override, dict):
        return {}

    retrieval_override = config_override.get("retrieval")
    if isinstance(retrieval_override, dict):
        return retrieval_override

    direct_keys = {"k", "rerank_top_k"}
    return {key: value for key, value in config_override.items() if key in direct_keys}


def _build_request_llm(config_override: Optional[Dict[str, Any]] = None) -> LLM:
    runtime_config = _load_runtime_config()
    generation = runtime_config.generation
    generation_override = _extract_generation_override(config_override)

    return LLM(
        endpoint=generation_override.get("llm_endpoint", generation.llm_endpoint),
        model_name=generation_override.get("model_name", generation.model_name),
        max_tokens=generation_override.get("max_tokens", generation.max_tokens),
        temperature=generation_override.get("temperature", generation.temperature),
        reasoning_effort=generation_override.get("reasoning_effort", generation.reasoning_effort),
        system_prompt=generation_override.get("system_prompt", generation.system_prompt),
    )


def _resolve_request_retrieval(config_override: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    runtime_config = _load_runtime_config()
    retrieval = runtime_config.retrieval
    retrieval_override = _extract_retrieval_override(config_override)

    return {
        "k": int(retrieval_override.get("k", retrieval.k)),
        "rerank_top_k": int(
            retrieval_override.get("rerank_top_k", retrieval.rerank_top_k)
        ),
    }


def _llm_proxy() -> httpx.AsyncClient:
    if llm_proxy_client is None:
        raise HTTPException(status_code=503, detail="LLM proxy client not initialized")
    return llm_proxy_client


def _llm_base_url() -> str:
    return _load_runtime_config().generation.llm_endpoint.rstrip("/")


def _llm_default_model() -> str:
    return _load_runtime_config().generation.model_name


def _normalize_reasoning_effort(value: Any) -> Any:
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if normalized in {"none", "off", "false", "0"}:
        return "none"
    if normalized in {"true", "on", "1"}:
        return "high"
    if normalized in {"low", "medium", "high"}:
        return normalized
    return value


def _prepare_llm_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    forwarded = dict(payload)
    forwarded["model"] = forwarded.get("model") or _llm_default_model()
    if "reasoning_effort" in forwarded:
        forwarded["reasoning_effort"] = _normalize_reasoning_effort(
            forwarded.get("reasoning_effort")
        )
    return forwarded


def _llm_error_response(
    error_type: str,
    message: str,
    *,
    status_code: int,
    provider_error: Any = None,
) -> JSONResponse:
    payload: Dict[str, Any] = {
        "error": {
            "type": error_type,
            "message": message,
            "status_code": status_code,
        }
    }
    if provider_error is not None:
        payload["error"]["provider_error"] = provider_error
    return JSONResponse(status_code=status_code, content=payload)


def _scrape_config_from_dict(data: Dict[str, Any]) -> ScrapeConfig:
    return ScrapeConfig(
        domain=data["domain"],
        folder=data["folder"],
        seeds=data["seeds"],
        allowed_paths=data.get("allowed_paths", []),
        disallowed_paths=data.get("disallowed_paths", []),
        max_depth=data.get("max_depth", 3),
        max_parallelism=data.get("max_parallelism", 2),
        rate_limit_ms=data.get("rate_limit_ms", 1000),
        user_agent=data.get("user_agent", "UI-RAG-Scraper/1.0"),
        skip_existing=data.get("skip_existing", False),
        dry_run=data.get("dry_run", False),
        output_dir=data.get("output_dir", "/app/data"),
    )


async def _proxy_llm_json(path: str, payload: Dict[str, Any]) -> Response:
    upstream_url = f"{_llm_base_url()}/{path.lstrip('/')}"
    try:
        upstream = await _llm_proxy().post(upstream_url, json=payload)
    except httpx.TimeoutException:
        return _llm_error_response(
            "upstream_timeout",
            "Timed out while waiting for Ollama",
            status_code=504,
        )
    except httpx.HTTPError as exc:
        return _llm_error_response(
            "upstream_unreachable",
            f"Failed to reach Ollama: {exc}",
            status_code=502,
        )

    if upstream.is_success:
        content_type = upstream.headers.get("content-type", "")
        if "application/json" in content_type:
            return JSONResponse(status_code=upstream.status_code, content=upstream.json())
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=content_type or None,
        )

    try:
        provider_error = upstream.json()
    except ValueError:
        provider_error = upstream.text
    return _llm_error_response(
        "upstream_error",
        "Ollama returned an error",
        status_code=upstream.status_code,
        provider_error=provider_error,
    )


async def _proxy_llm_stream(path: str, payload: Dict[str, Any]):
    upstream_url = f"{_llm_base_url()}/{path.lstrip('/')}"
    try:
        async with _llm_proxy().stream("POST", upstream_url, json=payload) as upstream:
            if upstream.is_success:
                async for chunk in upstream.aiter_bytes():
                    if chunk:
                        yield chunk
                return

            body = await upstream.aread()
            try:
                provider_error = json.loads(body.decode("utf-8"))
            except Exception:
                provider_error = body.decode("utf-8", errors="replace")
            error_payload = {
                "error": {
                    "type": "upstream_error",
                    "message": "Ollama returned an error",
                    "status_code": upstream.status_code,
                    "provider_error": provider_error,
                }
            }
            yield f"data: {json.dumps(error_payload, ensure_ascii=True)}\n\n".encode("utf-8")
    except httpx.TimeoutException:
        yield b'data: {"error":{"type":"upstream_timeout","message":"Timed out while waiting for Ollama","status_code":504}}\n\n'
    except httpx.HTTPError as exc:
        error_payload = {
            "error": {
                "type": "upstream_unreachable",
                "message": f"Failed to reach Ollama: {exc}",
                "status_code": 502,
            }
        }
        yield f"data: {json.dumps(error_payload, ensure_ascii=True)}\n\n".encode("utf-8")


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health", summary="Health check")
async def health_check():
    """Returns pipeline and storage connectivity status."""
    return {
        "status": "healthy" if rag_pipeline else "uninitialized",
        "milvus": (
            "connected"
            if rag_pipeline and rag_pipeline.storage
            else "not_connected"
        ),
    }


@app.get("/v1/models", response_model=LLMModelsResponse, summary="List plain LLM models exposed by this API")
async def list_llm_models():
    model_name = _llm_default_model()
    return {
        "object": "list",
        "data": [
            {
                "id": model_name,
                "object": "model",
                "owned_by": "ollama",
            }
        ],
    }


@app.post("/v1/chat/completions", summary="Proxy plain chat completions to Ollama")
async def proxy_chat_completions(request: LLMChatCompletionsRequest):
    payload = _prepare_llm_payload(request.model_dump(exclude_unset=True))
    logger.info(
        "Plain LLM request /v1/chat/completions model=%s stream=%s",
        payload.get("model"),
        payload.get("stream", False),
    )

    if payload.get("stream"):
        return StreamingResponse(
            _proxy_llm_stream("/chat/completions", payload),
            media_type="text/event-stream",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    return await _proxy_llm_json("/chat/completions", payload)


@app.post("/v1/completions", summary="Proxy plain completions to Ollama")
async def proxy_completions(request: LLMCompletionsRequest):
    payload = _prepare_llm_payload(request.model_dump(exclude_unset=True))
    logger.info(
        "Plain LLM request /v1/completions model=%s stream=%s",
        payload.get("model"),
        payload.get("stream", False),
    )

    if payload.get("stream"):
        return StreamingResponse(
            _proxy_llm_stream("/completions", payload),
            media_type="text/event-stream",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    return await _proxy_llm_json("/completions", payload)


@app.get("/collections", summary="List indexed collections")
async def list_collections():
    """Returns the collections currently available in the vector store."""
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")
    try:
        collections = rag_pipeline.storage.list_collections()
        return {"collections": collections}
    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runtime/config", summary="Show active runtime storage config")
async def runtime_config():
    """Returns the active collection and ingestion state path used by the running API."""
    config = _load_runtime_config()
    active_collection = config.storage.collection_name
    collections = []
    if rag_pipeline and rag_pipeline.storage:
        try:
            collections = rag_pipeline.storage.list_collections()
        except Exception as e:
            logger.warning(f"Failed to list collections while reading runtime config: {e}")

    return {
        "config_path": os.getenv("RAG_CONFIG_PATH", "config_rag.yaml"),
        "active_collection": active_collection,
        "active_collection_present": active_collection in collections if collections else None,
        "ingestion_state_path": config.ingestion.state_path,
        "available_collections": collections,
    }


@app.get("/ingestion/status", summary="Get ingestion status of all files")
async def ingestion_status():
    """Returns the list of files currently ingested with their metadata."""
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")
    
    files = rag_pipeline.ingestion_state.get_all_ingested()
    return {"ingested_files": files, "count": len(files)}


@app.get("/scraper/sites", summary="Show configured scraper site settings")
async def list_scraper_sites():
    """Returns the built-in scraper site settings for inspection/reference."""
    try:
        return list_configured_sites()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/scraper/jobs/urls", summary="Start a scrape job from actual URLs")
async def start_scraper_job_from_urls(request: ScrapeUrlsJobRequest):
    """
    Starts a scrape job from actual URLs. Non-UI domains are blocked unless
    allow_external=true. One job targets one domain.
    """
    try:
        config_data = config_from_urls(
            request.urls,
            allow_external=request.allow_external,
            folder=request.folder,
            output_dir=request.output_dir,
            max_depth=request.max_depth,
            max_parallelism=request.max_parallelism,
            rate_limit_ms=request.rate_limit_ms,
            user_agent=request.user_agent,
            skip_existing=request.skip_existing,
            dry_run=request.dry_run,
            disallowed_paths=request.disallowed_paths,
        )
        return scraper_manager.start_job(_scrape_config_from_dict(config_data))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/scraper/jobs/configured-site", summary="Start a configured scrape job by URL")
async def start_scraper_job_from_configured_site(
    request: ScrapeConfiguredSiteJobRequest,
):
    """
    Starts a scrape job by matching site_url's domain against the built-in
    configured site list, then reusing that site's exact settings.
    """
    try:
        config_data = config_from_configured_site(
            request.site_url,
            output_dir=request.output_dir,
            skip_existing=request.skip_existing,
            dry_run=request.dry_run,
        )
        return scraper_manager.start_job(_scrape_config_from_dict(config_data))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/scraper/jobs", summary="Start a server-side scrape job")
async def start_scraper_job(request: ScrapeJobRequest):
    """
    Starts a background scraper job that writes page.html/page.meta.json and
    PDF sidecars under output_dir. This does not trigger ingestion.
    """
    try:
        return scraper_manager.start_job(_scrape_config_from_dict(request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/scraper/jobs/{job_id}", summary="Get scrape job status")
async def get_scraper_job(job_id: str):
    """Returns status, counters, current URL, errors, and output path."""
    status = scraper_manager.get_job(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Scrape job not found: {job_id}")
    return status


@app.post("/scraper/jobs/{job_id}/cancel", summary="Cancel a scrape job")
async def cancel_scraper_job(job_id: str):
    """Requests cancellation for an active scrape job."""
    status = scraper_manager.cancel_job(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Scrape job not found: {job_id}")
    return status


@app.post("/query", response_model=RAGResponse, summary="Run a RAG query")
async def query_rag(request: QueryRequest, response: Response):
    """
    Embed the query using dense (Harrier) + sparse (OpenSearch) models,
    fuse results with RRF, rerank with Jina-v3, and generate a grounded answer.
    """
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")

    try:
        query_started = time.time()
        retrieval_settings = _resolve_request_retrieval(request.config_override)
        retrieval_started = time.time()
        docs = rag_pipeline.retriever.retrieve(
            query=request.query,
            collection_name=rag_pipeline.config.storage.collection_name,
            metadata_filter=request.metadata_filter,
            k=retrieval_settings["k"],
        )
        docs = docs[: retrieval_settings["rerank_top_k"]]
        retrieval_time_ms = (time.time() - retrieval_started) * 1000

        generation_started = time.time()
        if request.config_override:
            request_llm = _build_request_llm(request.config_override)
            llm_result = request_llm.generate(
                prompt=request.query,
                retrieved_docs=docs,
                context=None if docs else "No context provided.",
            )
            generation_time_ms = (time.time() - generation_started) * 1000
            end_to_end_time_ms = (time.time() - query_started) * 1000
            clean_answer = strip_thought_process(llm_result.answer)
            confidence_score = rag_pipeline._compute_retrieval_strength(docs)
            metadata = {
                "query": request.query,
                "num_docs": len(docs),
                "confidence_score": confidence_score,
                "generation_override_applied": True,
                "retrieval_k": retrieval_settings["k"],
                "rerank_top_k": retrieval_settings["rerank_top_k"],
                "retrieval_time_ms": retrieval_time_ms,
                "generation_time_ms": generation_time_ms,
                "end_to_end_time_ms": end_to_end_time_ms,
            }
            sources = llm_result.sources
            context = llm_result.context
        else:
            llm_result = rag_pipeline.llm.generate(
                prompt=request.query,
                retrieved_docs=docs,
                context=None if docs else "No context provided.",
            )
            generation_time_ms = (time.time() - generation_started) * 1000
            end_to_end_time_ms = (time.time() - query_started) * 1000
            clean_answer = strip_thought_process(llm_result.answer)
            confidence_score = rag_pipeline._compute_retrieval_strength(docs)
            metadata = {
                "query": request.query,
                "num_docs": len(docs),
                "confidence_score": confidence_score,
                "retrieval_k": retrieval_settings["k"],
                "rerank_top_k": retrieval_settings["rerank_top_k"],
                "retrieval_time_ms": retrieval_time_ms,
                "generation_time_ms": generation_time_ms,
                "end_to_end_time_ms": end_to_end_time_ms,
            }
            sources = llm_result.sources
            context = llm_result.context

        # Set confidence header
        response.headers["X-Confidence-Rate"] = str(confidence_score)
        response.headers["X-Retrieval-Time-Ms"] = f"{retrieval_time_ms:.3f}"
        response.headers["X-Generation-Time-Ms"] = f"{generation_time_ms:.3f}"
        response.headers["X-End-To-End-Time-Ms"] = f"{end_to_end_time_ms:.3f}"

        return {
            "answer": clean_answer,
            "context": context,
            "sources": sources,
            "metadata": metadata,
        }
    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query/stream", summary="Run a RAG query with token streaming")
async def query_rag_stream(request: QueryRequest):
    """
    Streaming version of the RAG query.
    Returns an SSE stream of JSON objects (type: 'metadata', 'sources', 'token', or 'confidence').
    """
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")

    try:
        if request.config_override:
            query_started = time.time()
            retrieval_settings = _resolve_request_retrieval(request.config_override)
            retrieval_started = time.time()
            docs = rag_pipeline.retriever.retrieve(
                query=request.query,
                collection_name=rag_pipeline.config.storage.collection_name,
                metadata_filter=request.metadata_filter,
                k=retrieval_settings["k"],
            )
            docs = docs[: retrieval_settings["rerank_top_k"]]
            retrieval_time_ms = (time.time() - retrieval_started) * 1000
            request_llm = _build_request_llm(request.config_override)

            def _override_stream():
                metadata_payload = {
                    "num_docs": len(docs),
                    "query": request.query,
                    "generation_override_applied": True,
                    "retrieval_k": retrieval_settings["k"],
                    "rerank_top_k": retrieval_settings["rerank_top_k"],
                    "retrieval_time_ms": retrieval_time_ms,
                }
                yield f"data: {json.dumps({'type': 'metadata', 'content': metadata_payload})}\n\n"
                yield f"data: {json.dumps({'type': 'sources', 'content': [{'pdf_url': doc.metadata.get('pdf_url'), 'page_url': doc.metadata.get('page_url'), 'scraped_at': doc.metadata.get('scraped_at'), 'page': doc.metadata.get('page_number', 'Unknown')} for doc in docs]})}\n\n"
                generation_started = time.time()
                for token in request_llm.generate_stream(prompt=request.query, retrieved_docs=docs):
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                generation_time_ms = (time.time() - generation_started) * 1000
                end_to_end_time_ms = (time.time() - query_started) * 1000
                confidence_score = rag_pipeline._compute_retrieval_strength(docs)
                yield f"data: {json.dumps({'type': 'confidence', 'content': {'confidence_score': confidence_score, 'query': request.query}})}\n\n"
                yield f"data: {json.dumps({'type': 'timings', 'content': {'retrieval_time_ms': retrieval_time_ms, 'generation_time_ms': generation_time_ms, 'end_to_end_time_ms': end_to_end_time_ms, 'query': request.query, 'generation_override_applied': True, 'retrieval_k': retrieval_settings['k'], 'rerank_top_k': retrieval_settings['rerank_top_k']}})}\n\n"

            return StreamingResponse(
                _override_stream(),
                media_type="text/event-stream",
                headers={
                    "X-Accel-Buffering": "no",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )

        return StreamingResponse(
            rag_pipeline.query_stream(
                request.query,
                metadata_filter=request.metadata_filter,
            ),
            media_type="text/event-stream",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except Exception as e:
        logger.error(f"Streaming query setup failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _background_ingestion(directory: str) -> None:
    """Background task: ingest all documents in *directory* into the vector store."""
    if not rag_pipeline:
        logger.error("Ingestion failed: pipeline not initialized")
        return
    try:
        logger.info(f"Background ingestion started for: {directory}")
        if os.path.isfile(directory):
            rag_pipeline.ingest(paths=[directory])
        else:
            rag_pipeline.ingest(directory=directory)
        logger.info(f"Background ingestion completed for: {directory}")
    except Exception as e:
        logger.error(f"Background ingestion failed: {e}", exc_info=True)


@app.post("/ingest", summary="Ingest a directory of documents")
async def ingest_data(request: IngestRequest, background_tasks: BackgroundTasks):
    """
    Triggers document ingestion as a background task.
    Monitor progress with: docker compose logs -f rag-api
    """
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")

    if not os.path.exists(request.directory_path):
        raise HTTPException(
            status_code=400,
            detail=f"Directory not found: {request.directory_path}",
        )

    background_tasks.add_task(_background_ingestion, request.directory_path)
    return {
        "status": "ingestion_started",
        "directory": request.directory_path,
        "message": "Check container logs for progress.",
    }


@app.post("/ingestion/upload", summary="Upload and ingest a document")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Upload a single PDF or HTML file and trigger ingestion.
    Files are stored in the /app/uploads directory.
    """
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")

    # Ensure upload directory exists
    upload_dir = Path("/app/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    
    # Save the file
    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())
        logger.info(f"File uploaded: {file_path}")
    except Exception as e:
        logger.error(f"Failed to save upload: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    # Trigger ingestion for this specific file
    background_tasks.add_task(_background_ingestion, str(file_path))

    return {
        "status": "upload_success",
        "filename": file.filename,
        "message": "Ingestion triggered in background."
    }


@app.post("/debug/chunks", response_model=DebugChunksResponse, summary="Debug: View chunks before embedding")
async def debug_chunks(request: DebugChunksRequest):
    """
    View chunks after chunking but before embedding.
    Useful for inspecting how documents are being split and processed.
    """
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")

    import time
    start_time = time.time()

    try:
        # Process the directory to get chunks
        chunks = rag_pipeline.ingestion.process_directory(request.directory_path)

        # Prepare chunk data for response
        chunk_data = []
        for i, chunk in enumerate(chunks):
            # Estimate token count (rough approximation: 1 token ≈ 4 chars)
            token_count = len(chunk.text) // 4
            
            chunk_info = ChunkInfo(
                id=i,
                doc_id=chunk.doc_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                pdf_url=chunk.metadata.get("pdf_url"),
                page_url=chunk.metadata.get("page_url"),
                scraped_at=chunk.metadata.get("scraped_at"),
                page_number=chunk.page_number,
                char_count=len(chunk.text),
                token_count=token_count,
                metadata=dict(chunk.metadata) if chunk.metadata else {}
            )
            chunk_data.append(chunk_info)

        # Optionally save to file
        if request.save_to_file:
            import json
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"chunks_debug_{timestamp}.{request.output_format}"
            filepath = f"./debug_output/{filename}"
            
            # Create debug_output directory if it doesn't exist
            import os
            os.makedirs("./debug_output", exist_ok=True)
            
            if request.output_format == "json":
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump([chunk.dict() for chunk in chunk_data], f, indent=2, ensure_ascii=False)
            else:  # txt format
                with open(filepath, 'w', encoding='utf-8') as f:
                    for chunk in chunk_data:
                        f.write(f"=== CHUNK {chunk.id} ===\n")
                        f.write(f"Doc ID: {chunk.doc_id}\n")
                        f.write(f"Breadcrumb: {chunk.breadcrumb}\n")
                        f.write(f"Page: {chunk.page_number}\n")
                        f.write(f"Filename: {chunk.filename}\n")
                        f.write(f"Text: {chunk.text}\n")
                        f.write("\n" + "="*50 + "\n\n")

        processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds

        return DebugChunksResponse(
            chunks=chunk_data,
            total_chunks=len(chunk_data),
            processing_time_ms=processing_time
        )
    except Exception as e:
        logger.error(f"Debug chunks failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/debug/retrieve", response_model=DebugRetrieveResponse, summary="Debug: View retrieval results before reranking")
async def debug_retrieve(request: DebugRetrieveRequest):
    """
    View retrieval results after RRF fusion but before reranking.
    Shows how documents are retrieved and scored by the hybrid system.
    """
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")

    import time
    start_time = time.time()

    try:
        # Perform retrieval only (without reranking)
        docs = rag_pipeline.retriever.retrieve(
            query=request.query,
            collection_name=rag_pipeline.config.storage.collection_name,
            metadata_filter=request.metadata_filter,
            k=request.k,
        )

        # Prepare retrieved docs data for response
        retrieved_docs = []
        for doc in docs:
            # Note: We don't have individual dense/sparse scores here since
            # the retriever returns the fused RRF results. We'll leave them as None.
            doc_info = RetrievedDocInfo(
                text=doc.text,
                doc_id=doc.doc_id,
                chunk_index=doc.chunk_index,
                rrf_score=doc.score,
                dense_score=None,
                sparse_score=None,
                pdf_url=doc.metadata.get("pdf_url"),
                page_url=doc.metadata.get("page_url"),
                scraped_at=doc.metadata.get("scraped_at"),
                page_number=doc.metadata.get("page_number") or 0
            )
            retrieved_docs.append(doc_info)

        retrieval_time = (time.time() - start_time) * 1000  # Convert to milliseconds

        return DebugRetrieveResponse(
            query=request.query,
            retrieved_docs=retrieved_docs,
            total_candidates=len(retrieved_docs),
            retrieval_time_ms=retrieval_time
        )
    except Exception as e:
        logger.error(f"Debug retrieve failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/debug/rerank", response_model=DebugRerankResponse, summary="Debug: View rerank results before LLM")
async def debug_rerank(request: DebugRerankRequest):
    """
    View reranking results after Jina reranking but before LLM generation.
    Shows how the reranker modifies the order and scores of retrieved documents.
    """
    if not rag_pipeline:
        raise HTTPException(status_code=503, detail="RAG Pipeline not initialized")

    import time
    start_time = time.time()

    try:
        # Get the top k documents before reranking
        docs = rag_pipeline.retriever.retrieve(
            query=request.query,
            collection_name=rag_pipeline.config.storage.collection_name,
            k=request.k,
        )

        # Apply reranking using the retriever's internal method
        reranked_docs = rag_pipeline.retriever._rerank(request.query, docs)

        # Take only the top rerank_top_k documents
        reranked_docs = reranked_docs[:request.rerank_top_k]

        # Prepare reranked docs data for response
        reranked_docs_info = []
        for doc in reranked_docs:
            doc_info = RerankedDocInfo(
                text=doc.text,
                doc_id=doc.doc_id,
                chunk_index=doc.chunk_index,
                rrf_score=doc.score,  # This is the RRF score before reranking
                rerank_score=doc.score,  # The score after reranking
                final_score=doc.score,
                pdf_url=doc.metadata.get("pdf_url"),
                page_url=doc.metadata.get("page_url"),
                scraped_at=doc.metadata.get("scraped_at"),
                page_number=doc.metadata.get("page_number") or 0
            )
            reranked_docs_info.append(doc_info)

        rerank_time = (time.time() - start_time) * 1000  # Convert to milliseconds

        return DebugRerankResponse(
            query=request.query,
            reranked_docs=reranked_docs_info,
            rerank_time_ms=rerank_time
        )
    except Exception as e:
        logger.error(f"Debug rerank failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
