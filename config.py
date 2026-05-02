from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from generation.prompts import DEFAULT_SYSTEM_PROMPT


@dataclass
class IngestionConfig:
    chunk_size: int = 512
    chunk_overlap: int = 50
    pdf_min_chunk_tokens: int = 300
    pdf_max_chunk_tokens: int = 1000
    pdf_split_overlap_tokens: int = 120
    pdf_parser: str = "docling"
    pdf_chunking_strategy: str = "hierarchical"
    html_parser: str = "trafilatura"
    html_chunking_strategy: str = "standard"
    save_snapshots: bool = False
    incremental: bool = True
    state_path: str = "storage/ingestion_state.json"
    upload_dir: str = "uploads"


@dataclass
class EmbeddingConfig:
    dense_model: str = "microsoft/harrier-oss-v1-0.6b"
    sparse_model: str = "opensearch-project/opensearch-neural-sparse-encoding-doc-v3-gte"
    device: str = "cuda"  # Multi-GPU: This is the default for Dense
    dense_device: str = "cuda:0"
    sparse_device: str = "cpu"  # Sparse query is fast on CPU
    quantize_8bit: bool = True
    batch_size: int = 32


@dataclass
class StorageConfig:
    milvus_uri: str = "./milvus.db"
    collection_base_name: str = "documents"
    collection_name: str = "documents"
    db_name: str = "default"
    metric_type: str = "COSINE"


@dataclass
class RetrievalConfig:
    k: int = 50
    """Candidate pool size fetched from Milvus before reranking."""

    rerank_top_k: int = 5
    """Number of documents passed to the LLM after reranking."""

    hybrid_weight: float = 0.5
    reranker_model: Optional[str] = "jinaai/jina-reranker-v3-GGUF:Q5_K_M"
    reranker_endpoint: Optional[str] = "http://127.0.0.1:8012/v1/rerank"
    min_score: float = 0.0


@dataclass
class GenerationConfig:
    llm_endpoint: str = "http://localhost:8000/v1"
    model_name: str = "llama-3-8b"
    max_tokens: int = 512
    temperature: float = 0.0
    reasoning_effort: Optional[str] = None
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


@dataclass
class EvaluationConfig:
    @dataclass
    class ModelSpec:
        model_name: str
        llm_endpoint: Optional[str] = None
        max_tokens: Optional[int] = None
        temperature: Optional[float] = None
        reasoning_effort: Optional[str] = None
        label: Optional[str] = None

    metrics: List[str] = field(
        default_factory=lambda: [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
        ]
    )
    judge_mode: str = "local"
    eval_llm: str = "llama-3-8b"
    eval_llm_endpoint: Optional[str] = "http://localhost:8000/v1"
    eval_llm_api_key_env: str = "OPENAI_API_KEY"
    eval_embeddings: str = "microsoft/harrier-oss-v1-0.6b"
    eval_embeddings_endpoint: Optional[str] = None
    dataset_path: Optional[str] = "storage/eval_datasets/ui_mixed_seed.json"
    report_dir: str = "storage/eval_reports"
    num_synthetic_qa: int = 3
    model_matrix: List["EvaluationConfig.ModelSpec"] = field(default_factory=list)


@dataclass
class RAGConfig:
    ingestion: IngestionConfig = field(default_factory=IngestionConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "RAGConfig":
        """Load config from a YAML file. Any missing top-level key falls back to defaults."""
        import yaml

        def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
            merged = dict(base)
            for key, value in override.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = _merge_dicts(merged[key], value)
                else:
                    merged[key] = value
            return merged

        def _load_config_file(config_path: Path, seen: set[Path]) -> dict[str, Any]:
            resolved_path = config_path.resolve()
            if resolved_path in seen:
                raise ValueError(f"Config inheritance cycle detected at: {resolved_path}")

            with open(resolved_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}

            if not isinstance(loaded, dict):
                raise ValueError(f"Config file must contain a YAML mapping: {resolved_path}")

            extends_value = loaded.pop("extends", None)
            if not extends_value:
                return loaded

            if isinstance(extends_value, str):
                extends_paths = [extends_value]
            elif isinstance(extends_value, list) and all(
                isinstance(item, str) for item in extends_value
            ):
                extends_paths = extends_value
            else:
                raise ValueError(
                    f"'extends' must be a string or list of strings: {resolved_path}"
                )

            merged_base: dict[str, Any] = {}
            seen.add(resolved_path)
            try:
                for parent_path in extends_paths:
                    parent_data = _load_config_file(
                        (resolved_path.parent / parent_path).resolve(), seen
                    )
                    merged_base = _merge_dicts(merged_base, parent_data)
            finally:
                seen.remove(resolved_path)

            return _merge_dicts(merged_base, loaded)

        data = _load_config_file(Path(path), seen=set())

        ingestion_data = dict(data.get("ingestion", {}))
        legacy_chunking_strategy = ingestion_data.pop("chunking_strategy", None)
        if legacy_chunking_strategy is not None:
            ingestion_data.setdefault("pdf_chunking_strategy", legacy_chunking_strategy)
            ingestion_data.setdefault("html_chunking_strategy", legacy_chunking_strategy)

        evaluation_data = dict(data.get("evaluation", {}))
        model_matrix_data = evaluation_data.pop("model_matrix", []) or []

        return cls(
            ingestion=IngestionConfig(**ingestion_data),
            embedding=EmbeddingConfig(**data.get("embedding", {})),
            storage=StorageConfig(**data.get("storage", {})),
            retrieval=RetrievalConfig(**data.get("retrieval", {})),
            generation=GenerationConfig(**data.get("generation", {})),
            evaluation=EvaluationConfig(
                **evaluation_data,
                model_matrix=[
                    EvaluationConfig.ModelSpec(**item) for item in model_matrix_data
                ],
            ),
        )
