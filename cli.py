import argparse
import json
import math
import os
import re
import sys
import time
from urllib.parse import urlparse
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import httpx

from pipeline import RAGPipeline
from config import RAGConfig
from storage import MilvusClient


def _load_yaml(path: str) -> dict:
    import yaml

    def _expand_env_vars(value):
        if isinstance(value, str):
            return os.path.expandvars(value)
        if isinstance(value, list):
            return [_expand_env_vars(item) for item in value]
        if isinstance(value, dict):
            return {key: _expand_env_vars(item) for key, item in value.items()}
        return value

    with open(path, "r", encoding="utf-8") as f:
        return _expand_env_vars(yaml.safe_load(f) or {})


def _write_yaml(path: Path, data: dict) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _timestamped_path(directory: str | Path, prefix: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(directory) / f"{prefix}_{timestamp}.json"


def _artifact_path_for_label(
    directory: str | Path,
    prefix: str,
    label: str | None = None,
) -> Path:
    base_prefix = prefix
    slug = _slugify_label(label)
    if slug:
        base_prefix = f"{base_prefix}_{slug}"
    return _timestamped_path(directory, base_prefix)


def _slugify_label(value: str | None) -> str | None:
    if not value:
        return None
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return slug.strip("._-") or None


def _load_eval_dataset(path: Path) -> tuple[list[str], list[str] | None, dict]:
    if not path.exists():
        raise FileNotFoundError(f"evaluation dataset not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list) or not rows:
        raise ValueError(f"evaluation dataset must be a non-empty JSON array: {path}")

    questions: list[str] = []
    ground_truths: list[str | None] = []
    sample_label_counts: dict[str, int] = {}

    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"dataset row {idx} must be a JSON object")

        question = row.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"dataset row {idx} is missing a non-empty 'question'")

        reference = row.get("ground_truth")
        if reference is None:
            reference = row.get("reference")
        if reference is None:
            reference = row.get("answer")

        if reference is not None and not isinstance(reference, str):
            raise ValueError(
                f"dataset row {idx} has a non-string reference answer field"
            )

        questions.append(question)
        ground_truths.append(reference.strip() if isinstance(reference, str) else None)

        sample_label = row.get("sample_label")
        if isinstance(sample_label, str) and sample_label.strip():
            sample_label_counts[sample_label] = sample_label_counts.get(sample_label, 0) + 1

    has_any_ground_truth = any(
        isinstance(reference, str) and reference for reference in ground_truths
    )
    metadata = {
        "dataset_path": str(path),
        "dataset_row_count": len(rows),
        "has_ground_truths": has_any_ground_truth,
        "sample_label_counts": sample_label_counts,
    }

    return questions, (ground_truths if has_any_ground_truth else None), metadata


def _resolve_eval_inputs(args, parser, rag: RAGPipeline) -> tuple[list[str], list[str] | None, dict | None]:
    return _resolve_eval_inputs_from_dataset_path(
        args,
        parser,
        rag.config.evaluation.dataset_path,
    )


def _resolve_eval_inputs_from_dataset_path(args, parser, default_dataset_path: str | None) -> tuple[list[str], list[str] | None, dict | None]:
    questions = args.questions
    ground_truths = None
    dataset_metadata = None

    if not questions:
        dataset_path_value = args.dataset or default_dataset_path
        if not dataset_path_value:
            parser.error(
                "eval requires --questions or evaluation.dataset_path"
            )
        dataset_path = Path(dataset_path_value)
        questions, ground_truths, dataset_metadata = _load_eval_dataset(dataset_path)
        print(f"Loaded {len(questions)} evaluation samples from {dataset_path}")

    if not questions:
        parser.error("eval requires --questions or a dataset")

    return questions, ground_truths, dataset_metadata


def _load_prediction_samples(path: Path) -> tuple[list[dict], dict]:
    if not path.exists():
        raise FileNotFoundError(f"prediction artifact not found: {path}")

    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"prediction artifact must be a JSON object: {path}")

    artifacts = payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        raise ValueError(f"prediction artifact missing 'artifacts' object: {path}")

    samples = artifacts.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError(f"prediction artifact missing non-empty artifacts.samples: {path}")

    for idx, sample in enumerate(samples, start=1):
        if not isinstance(sample, dict):
            raise ValueError(f"prediction sample {idx} must be a JSON object")
        question = sample.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"prediction sample {idx} is missing a non-empty 'question'")

    dataset_metadata = payload.get("dataset", {})
    if not isinstance(dataset_metadata, dict):
        dataset_metadata = {}
    dataset_metadata = dict(dataset_metadata)
    dataset_metadata["prediction_artifact_path"] = str(path)
    payload_models = payload.get("models", {})
    if isinstance(payload_models, dict):
        for key in (
            "generation_model",
            "generation_endpoint",
            "generation_reasoning_effort",
        ):
            if key in payload_models:
                dataset_metadata[key] = payload_models[key]
    return samples, dataset_metadata


def _apply_eval_generate_overrides(config: RAGConfig, args) -> str | None:
    label = args.label
    if args.model:
        config.generation.model_name = args.model
    if args.endpoint:
        config.generation.llm_endpoint = args.endpoint
    if args.max_tokens is not None:
        config.generation.max_tokens = args.max_tokens
    if args.temperature is not None:
        config.generation.temperature = args.temperature
    if args.reasoning_effort is not None:
        config.generation.reasoning_effort = args.reasoning_effort

    return label or config.generation.model_name


def _apply_eval_score_overrides(config: RAGConfig, args) -> None:
    if args.judge_model:
        config.evaluation.eval_llm = args.judge_model
    if args.judge_endpoint:
        config.evaluation.eval_llm_endpoint = args.judge_endpoint
    if args.judge_mode:
        config.evaluation.judge_mode = args.judge_mode
    if args.judge_api_key_env:
        config.evaluation.eval_llm_api_key_env = args.judge_api_key_env
    if args.eval_embeddings:
        config.evaluation.eval_embeddings = args.eval_embeddings
    if args.eval_embeddings_endpoint:
        config.evaluation.eval_embeddings_endpoint = args.eval_embeddings_endpoint
    if args.judge_reasoning_effort is not None:
        config.evaluation.eval_reasoning_effort = args.judge_reasoning_effort
    if args.judge_include_thoughts:
        config.evaluation.eval_include_thoughts = True


def _runtime_settings_snapshot(config: RAGConfig, config_path: str | None = None) -> dict:
    return {
        "config_path": config_path,
        "collection": {
            "collection_name": config.storage.collection_name,
            "collection_base_name": config.storage.collection_base_name,
            "milvus_uri": config.storage.milvus_uri,
            "db_name": config.storage.db_name,
        },
        "retrieval": {
            "k": config.retrieval.k,
            "rerank_top_k": config.retrieval.rerank_top_k,
            "reranker_model": config.retrieval.reranker_model,
            "reranker_endpoint": config.retrieval.reranker_endpoint,
        },
        "embeddings": {
            "dense_model": config.embedding.dense_model,
            "sparse_model": config.embedding.sparse_model,
            "device": config.embedding.device,
            "dense_device": config.embedding.dense_device,
            "sparse_device": config.embedding.sparse_device,
            "batch_size": config.embedding.batch_size,
            "quantize_8bit": config.embedding.quantize_8bit,
        },
        "generation": {
            "model_name": config.generation.model_name,
            "llm_endpoint": config.generation.llm_endpoint,
            "max_tokens": config.generation.max_tokens,
            "temperature": config.generation.temperature,
            "reasoning_effort": config.generation.reasoning_effort,
        },
        "evaluation": {
            "judge_mode": config.evaluation.judge_mode,
            "metrics": list(config.evaluation.metrics),
            "eval_llm": config.evaluation.eval_llm,
            "eval_llm_endpoint": config.evaluation.eval_llm_endpoint,
            "eval_llm_api_key_env": config.evaluation.eval_llm_api_key_env,
            "eval_llm_max_tokens": config.evaluation.eval_llm_max_tokens,
            "eval_reasoning_effort": config.evaluation.eval_reasoning_effort,
            "eval_include_thoughts": config.evaluation.eval_include_thoughts,
            "eval_embeddings": config.evaluation.eval_embeddings,
            "eval_embeddings_endpoint": config.evaluation.eval_embeddings_endpoint,
            "dataset_path": config.evaluation.dataset_path,
            "report_dir": config.evaluation.report_dir,
            "prediction_dir": config.evaluation.prediction_dir,
            "answer_relevancy_strictness": config.evaluation.answer_relevancy_strictness,
        },
    }


def _derive_ollama_generate_url(llm_endpoint: str) -> str:
    endpoint = llm_endpoint.rstrip("/")
    if endpoint.endswith("/v1"):
        return endpoint[:-3] + "/api/generate"
    if endpoint.endswith("/api"):
        return endpoint + "/generate"

    parsed = urlparse(endpoint)
    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else endpoint
    return base.rstrip("/") + "/api/generate"


def _unload_ollama_model(llm_endpoint: str, model_name: str) -> None:
    unload_url = _derive_ollama_generate_url(llm_endpoint)
    payload = {
        "model": model_name,
        "keep_alive": 0,
        "stream": False,
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(unload_url, json=payload)
            response.raise_for_status()
        print(f"Requested Ollama unload for model {model_name} via {unload_url}")
    except Exception as exc:
        print(f"Warning: failed to unload Ollama model {model_name}: {exc}")


def _generate_eval_predictions_via_api(
    config: RAGConfig,
    api_base_url: str,
    questions: list[str],
    ground_truths: list[str] | None = None,
    dataset_metadata: dict | None = None,
    generation_override: dict | None = None,
) -> dict:
    api_url = f"{api_base_url.rstrip('/')}/query"
    samples = []
    timing_rows = []
    run_started = time.time()

    with httpx.Client(timeout=300.0) as client:
        for index, question in enumerate(questions):
            started = time.time()
            payload: dict[str, object] = {"query": question}
            if generation_override:
                payload["config_override"] = {"generation": generation_override}

            response = client.post(api_url, json=payload)
            response.raise_for_status()
            body = response.json()
            metadata = body.get("metadata", {})
            end_to_end_time_ms = (time.time() - started) * 1000
            retrieval_time_ms = metadata.get("retrieval_time_ms")
            generation_time_ms = metadata.get("generation_time_ms")
            api_end_to_end_time_ms = metadata.get("end_to_end_time_ms")

            sample = {
                "question": question,
                "answer": body.get("answer", ""),
                "context": body.get("context", ""),
                "retrieved_contexts": [body.get("context", "")],
                "sources": body.get("sources", []),
                "confidence_score": metadata.get("confidence_score"),
                "num_docs": metadata.get("num_docs"),
                "timings": {
                    "retrieval_time_ms": retrieval_time_ms,
                    "generation_time_ms": generation_time_ms,
                    "end_to_end_time_ms": api_end_to_end_time_ms or end_to_end_time_ms,
                    "ttft_ms": None,
                    "stream_completed": None,
                },
            }
            if ground_truths and index < len(ground_truths):
                sample["ground_truth"] = ground_truths[index]
            samples.append(sample)
            timing_rows.append(
                {
                    "question": question,
                    **sample["timings"],
                }
            )

    report = {
        "generated_at": datetime.now().isoformat(),
        "mode": "prediction_generation_api",
        "runtime_settings": _runtime_settings_snapshot(
            config,
            getattr(config, "source_config_path", None),
        ),
        "summary": {
            "question_count": len(questions),
            "timings": {
                "retrieval_time_ms_avg": (
                    sum(
                        float(row["retrieval_time_ms"])
                        for row in timing_rows
                        if row.get("retrieval_time_ms") is not None
                    )
                    / len([row for row in timing_rows if row.get("retrieval_time_ms") is not None])
                    if any(row.get("retrieval_time_ms") is not None for row in timing_rows)
                    else None
                ),
                "generation_time_ms_avg": (
                    sum(
                        float(row["generation_time_ms"])
                        for row in timing_rows
                        if row.get("generation_time_ms") is not None
                    )
                    / len([row for row in timing_rows if row.get("generation_time_ms") is not None])
                    if any(row.get("generation_time_ms") is not None for row in timing_rows)
                    else None
                ),
                "end_to_end_time_ms_avg": (
                    sum(row["end_to_end_time_ms"] for row in timing_rows) / len(timing_rows)
                    if timing_rows else None
                ),
                "ttft_ms_avg": None,
                "total_runtime_ms": (time.time() - run_started) * 1000,
            },
        },
        "api_base_url": api_base_url,
        "models": {
            "generation_model": generation_override.get("model_name", config.generation.model_name)
            if generation_override
            else config.generation.model_name,
            "generation_endpoint": api_base_url,
            "upstream_generation_endpoint": generation_override.get("llm_endpoint", config.generation.llm_endpoint)
            if generation_override
            else config.generation.llm_endpoint,
            "generation_reasoning_effort": generation_override.get("reasoning_effort", config.generation.reasoning_effort)
            if generation_override
            else config.generation.reasoning_effort,
        },
        "dataset": {
            "dataset_path": config.evaluation.dataset_path,
            "question_count": len(questions),
            "has_ground_truths": bool(
                ground_truths and any(isinstance(g, str) and g.strip() for g in ground_truths)
            ),
        },
        "timings": {
            "per_question": timing_rows,
            "summary": {
                "retrieval_time_ms_avg": (
                    sum(
                        float(row["retrieval_time_ms"])
                        for row in timing_rows
                        if row.get("retrieval_time_ms") is not None
                    )
                    / len([row for row in timing_rows if row.get("retrieval_time_ms") is not None])
                    if any(row.get("retrieval_time_ms") is not None for row in timing_rows)
                    else None
                ),
                "generation_time_ms_avg": (
                    sum(
                        float(row["generation_time_ms"])
                        for row in timing_rows
                        if row.get("generation_time_ms") is not None
                    )
                    / len([row for row in timing_rows if row.get("generation_time_ms") is not None])
                    if any(row.get("generation_time_ms") is not None for row in timing_rows)
                    else None
                ),
                "end_to_end_time_ms_avg": (
                    sum(row["end_to_end_time_ms"] for row in timing_rows) / len(timing_rows)
                    if timing_rows else None
                ),
                "ttft_ms_avg": None,
            },
        },
        "artifacts": {
            "samples": samples,
        },
        "caveats": [
            "Predictions were generated through the live /query API and reused the running RAG service",
            "End-to-end timing falls back to client-side round-trip time if the API metadata omits it",
        ],
    }
    if dataset_metadata:
        report["dataset"].update(dataset_metadata)
    return report


def _metric_means(results: dict) -> dict[str, float | None]:
    metrics = results.get("metrics")
    if not isinstance(metrics, dict):
        return {}

    summary: dict[str, float | None] = {}
    for metric_name, raw_values in metrics.items():
        if isinstance(raw_values, dict):
            candidates = raw_values.values()
        elif isinstance(raw_values, list):
            candidates = raw_values
        else:
            candidates = [raw_values]

        numeric_values = [
            float(value)
            for value in candidates
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        numeric_values = [value for value in numeric_values if math.isfinite(value)]
        summary[metric_name] = (
            sum(numeric_values) / len(numeric_values) if numeric_values else None
        )
    return summary


def _primary_score(metric_means: dict[str, float | None]) -> float | None:
    numeric_values = [
        value for value in metric_means.values() if isinstance(value, (int, float))
    ]
    numeric_values = [value for value in numeric_values if math.isfinite(value)]
    return sum(numeric_values) / len(numeric_values) if numeric_values else None


def _build_leaderboards(model_entries: list[dict]) -> dict[str, list[dict]]:
    metric_names: set[str] = set()
    for entry in model_entries:
        metric_names.update(entry.get("metric_means", {}).keys())

    leaderboards: dict[str, list[dict]] = {}
    for metric_name in sorted(metric_names):
        ranked_entries = []
        for entry in model_entries:
            score = entry.get("metric_means", {}).get(metric_name)
            if isinstance(score, (int, float)) and math.isfinite(score):
                ranked_entries.append(
                    {
                        "label": entry.get("label"),
                        "generation_model": entry.get("generation_model"),
                        "score": score,
                        "report_path": entry.get("report_path"),
                    }
                )
        ranked_entries.sort(key=lambda item: item["score"], reverse=True)
        leaderboards[metric_name] = ranked_entries

    overall = []
    for entry in model_entries:
        score = entry.get("primary_score")
        if isinstance(score, (int, float)) and math.isfinite(score):
            overall.append(
                {
                    "label": entry.get("label"),
                    "generation_model": entry.get("generation_model"),
                    "score": score,
                    "report_path": entry.get("report_path"),
                }
            )
    overall.sort(key=lambda item: item["score"], reverse=True)
    leaderboards["overall"] = overall
    return leaderboards


def _build_matrix_entry(report: dict, label: str) -> dict:
    results_block = report.get("results", {}) if isinstance(report.get("results"), dict) else {}
    timings = report.get("timings", {}).get("summary", {})
    metric_means = _metric_means(results_block)
    return {
        "label": label,
        "generation_model": report.get("models", {}).get("generation_model"),
        "generation_endpoint": report.get("models", {}).get("generation_endpoint"),
        "generation_reasoning_effort": report.get("models", {}).get("generation_reasoning_effort"),
        "judge_model": report.get("models", {}).get("judge_model"),
        "dataset_path": report.get("dataset", {}).get("dataset_path"),
        "question_count": report.get("dataset", {}).get("question_count"),
        "metric_means": metric_means,
        "primary_score": _primary_score(metric_means),
        "error": results_block.get("error"),
        "requested_metrics": results_block.get("requested_metrics"),
        "used_metrics": results_block.get("used_metrics"),
        "timings": timings,
        "report_path": report.get("report_path"),
    }


def _run_eval_matrix(
    rag: RAGPipeline,
    questions: list[str],
    ground_truths: list[str] | None,
    dataset_metadata: dict | None,
    output_path: str | None,
) -> dict:
    model_specs = rag.config.evaluation.model_matrix
    run_started = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = (
        Path(output_path)
        if output_path
        else Path(rag.config.evaluation.report_dir) / f"eval_matrix_summary_{timestamp}.json"
    )

    aggregate = {
        "generated_at": datetime.now().isoformat(),
        "mode": "matrix",
        "status": "running",
        "runtime_settings": _runtime_settings_snapshot(
            rag.config,
            getattr(rag.config, "source_config_path", None),
        ),
        "base_generation_endpoint": rag.config.generation.llm_endpoint,
        "judge_mode": rag.config.evaluation.judge_mode,
        "judge_model": rag.config.evaluation.eval_llm,
        "dataset": {
            "dataset_path": rag.config.evaluation.dataset_path,
            "question_count": len(questions),
        },
        "models": [],
        "completed_models": 0,
        "total_models": len(model_specs),
        "summary": {
            "question_count": len(questions),
            "best_overall": None,
            "timings": {},
        },
    }
    if dataset_metadata:
        aggregate["dataset"].update(dataset_metadata)
    _write_json(summary_path, aggregate)

    for index, spec in enumerate(model_specs, start=1):
        run_config = deepcopy(rag.config)
        run_config.generation.model_name = spec.model_name
        if spec.llm_endpoint is not None:
            run_config.generation.llm_endpoint = spec.llm_endpoint
        if spec.max_tokens is not None:
            run_config.generation.max_tokens = spec.max_tokens
        if spec.temperature is not None:
            run_config.generation.temperature = spec.temperature
        if spec.reasoning_effort is not None:
            run_config.generation.reasoning_effort = spec.reasoning_effort

        label = spec.label or spec.model_name
        print(f"[{index}/{len(model_specs)}] Evaluating {label}")
        run_rag = None
        try:
            run_rag = RAGPipeline(run_config)
            report = run_rag.evaluate(
                questions=questions,
                ground_truths=ground_truths,
                dataset_metadata=dataset_metadata,
            )
        except Exception as exc:
            report = {
                "generated_at": datetime.now().isoformat(),
                "runtime_settings": _runtime_settings_snapshot(
                    run_config,
                    getattr(run_config, "source_config_path", None),
                ),
                "models": {
                    "generation_model": run_config.generation.model_name,
                    "generation_endpoint": run_config.generation.llm_endpoint,
                    "judge_model": run_config.evaluation.eval_llm,
                },
                "dataset": {
                    "dataset_path": run_config.evaluation.dataset_path,
                    "question_count": len(questions),
                },
                "timings": {"summary": {}},
                "results": {
                    "error": str(exc),
                    "requested_metrics": run_config.evaluation.metrics,
                    "used_metrics": [],
                },
                "report_path": None,
            }
        finally:
            if run_rag is not None:
                run_rag.close()

        matrix_entry = _build_matrix_entry(report, label)
        aggregate["models"].append(matrix_entry)
        aggregate["completed_models"] = len(aggregate["models"])
        aggregate["status"] = (
            "completed"
            if aggregate["completed_models"] == aggregate["total_models"]
            else "running"
        )
        aggregate["leaderboards"] = _build_leaderboards(aggregate["models"])
        aggregate["updated_at"] = datetime.now().isoformat()
        _write_json(summary_path, aggregate)
        score_display = (
            f"{matrix_entry['primary_score']:.4f}"
            if isinstance(matrix_entry.get("primary_score"), (int, float))
            else "n/a"
        )
        print(
            f"Completed {label}: primary_score={score_display}, "
            f"report={matrix_entry.get('report_path')}"
        )

    aggregate["leaderboards"] = _build_leaderboards(aggregate["models"])
    aggregate["summary"]["timings"]["total_runtime_ms"] = (time.time() - run_started) * 1000
    aggregate["summary"]["timings"]["total_runtime_seconds"] = (
        aggregate["summary"]["timings"]["total_runtime_ms"] / 1000.0
    )
    aggregate["summary_path"] = str(summary_path)
    _write_json(summary_path, aggregate)
    top_overall = aggregate["leaderboards"].get("overall", [])
    if top_overall:
        winner = top_overall[0]
        aggregate["summary"]["best_overall"] = winner
        _write_json(summary_path, aggregate)
        print(
            f"Top overall: {winner['label']} "
            f"({winner['score']:.4f})"
        )
    return aggregate


def _default_rebuild_root(base_config_path: str, timestamp: str) -> Path:
    base_path = Path(base_config_path)
    return base_path.parent / "storage" / "rebuilds" / timestamp


def _build_rebuild_config(
    base_config_path: str,
    collection_name: str = None,
    state_path: str = None,
    output_config: str = None,
    rebuild_dir: str = None,
) -> tuple[Path, str, str]:
    base_path = Path(base_config_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    base_data = _load_yaml(base_config_path)
    rebuild_data = deepcopy(base_data)
    ingestion = rebuild_data.setdefault("ingestion", {})
    storage = rebuild_data.setdefault("storage", {})

    configured_collection = storage.get("collection_name", "documents")
    base_collection = storage.get("collection_base_name", "documents")
    rebuild_collection = collection_name or f"{base_collection}_rebuild_{timestamp}"
    if rebuild_dir:
        rebuild_root = Path(rebuild_dir)
        rebuild_config_path = rebuild_root / "config.yaml"
    elif output_config:
        rebuild_root = Path(output_config).parent
        rebuild_config_path = Path(output_config)
    else:
        rebuild_root = _default_rebuild_root(base_config_path, timestamp)
        rebuild_config_path = rebuild_root / "config.yaml"
    rebuild_state_path = (
        Path(state_path)
        if state_path
        else rebuild_root / "ingestion_state.json"
    )
    manifest_path = rebuild_root / "rebuild_manifest.json"

    storage["collection_name"] = rebuild_collection
    ingestion["state_path"] = str(rebuild_state_path)

    rebuild_root.mkdir(parents=True, exist_ok=True)
    _write_yaml(rebuild_config_path, rebuild_data)
    _write_json(
        manifest_path,
        {
            "created_at": timestamp,
            "source_config_path": str(base_path),
            "source_collection_name": configured_collection,
            "rebuild_collection_name": rebuild_collection,
            "rebuild_root": str(rebuild_root),
            "rebuild_config_path": str(rebuild_config_path),
            "rebuild_state_path": str(rebuild_state_path),
        },
    )
    return rebuild_config_path, rebuild_collection, rebuild_state_path


def _load_rebuild_manifest(rebuild_root: Path) -> dict:
    manifest_path = rebuild_root / "rebuild_manifest.json"
    if manifest_path.exists():
        return _load_json(manifest_path)

    rebuild_config_path = rebuild_root / "config.yaml"
    rebuild_state_path = rebuild_root / "ingestion_state.json"
    config = RAGConfig.from_yaml(str(rebuild_config_path))
    return {
        "rebuild_root": str(rebuild_root),
        "rebuild_config_path": str(rebuild_config_path),
        "rebuild_state_path": str(rebuild_state_path),
        "rebuild_collection_name": config.storage.collection_name,
        "source_collection_name": None,
    }


def _print_rebuild_next_steps(
    rebuild_root: Path,
    rebuild_config_path: Path,
    collection_name: str,
    state_path: str,
    directory: str,
    indexed_count: int,
) -> None:
    print("\nRebuild index completed.")
    print(f"Indexed chunks: {indexed_count}")
    print(f"Source directory: {directory}")
    print(f"Rebuild folder: {rebuild_root}")
    print(f"Rebuild config: {rebuild_config_path}")
    print(f"Rebuild collection: {collection_name}")
    print(f"Rebuild state path: {state_path}")
    print("\nInspect the live Milvus collections:")
    print(
        "  python cli.py collections "
        f"--config {rebuild_config_path}"
    )
    print("\nValidate the rebuilt collection:")
    print(
        "  python cli.py debug-query "
        f"--config {rebuild_config_path} "
        '--query "known test question" --show-stages'
    )
    print("\nPromote after validation:")
    print(
        "  python cli.py promote-index "
        f"--rebuild-dir {rebuild_root}"
    )
    print("\nCleanup the old collection only after the rebuilt one is healthy:")
    print(
        "  python cli.py cleanup-collection "
        f"--rebuild-dir {rebuild_root} --yes"
    )
    print("\nRollback remains the old collection/state from your production config.")


def _print_promotion_instructions(bundle: dict) -> None:
    print("Promotion patch to apply to the production config:")
    print(f"Rebuild folder: {bundle['rebuild_root']}")
    print(f"Rebuild config: {bundle['rebuild_config_path']}")
    if bundle.get("source_collection_name"):
        print(f"Previous collection: {bundle['source_collection_name']}")
    print("\ningestion:")
    print(f'  state_path: "{bundle["rebuild_state_path"]}"')
    print("\nstorage:")
    print(f'  collection_name: "{bundle["rebuild_collection_name"]}"')
    print("\nThen restart only the API:")
    print("  docker compose restart rag-api")
    if bundle.get("source_collection_name"):
        print("\nAfter validation, clean up the old collection with:")
        print(
            "  python cli.py cleanup-collection "
            f"--collection-name {bundle['source_collection_name']} --yes"
        )
    print("\nRollback by restoring the previous collection_name/state_path and restarting rag-api.")


def _print_collection_inventory(config: RAGConfig, collections: list[str]) -> None:
    active = config.storage.collection_name
    payload = {
        "active_collection": active,
        "active_collection_present": active in collections,
        "collections": collections,
    }
    print(json.dumps(payload, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="MyRAG CLI for debugging and inspection"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    query_parser = subparsers.add_parser("query", help="Query the RAG system")
    query_parser.add_argument("--config", required=True, help="Path to config YAML")
    query_parser.add_argument("--query", required=True, help="Query string")
    query_parser.add_argument("--doc-ids", nargs="*", help="Filter by document IDs")
    query_parser.add_argument(
        "--k", type=int, default=5, help="Number of documents to retrieve"
    )

    find_parser = subparsers.add_parser(
        "find-keyword", help="Find chunks containing keyword"
    )
    find_parser.add_argument("--config", required=True, help="Path to config YAML")
    find_parser.add_argument("--keyword", required=True, help="Keyword to search")
    find_parser.add_argument("--doc-id", help="Filter by document ID")
    find_parser.add_argument(
        "--case-sensitive", action="store_true", help="Case sensitive search"
    )

    trace_parser = subparsers.add_parser("trace", help="Trace query with keyword check")
    trace_parser.add_argument("--config", required=True, help="Path to config YAML")
    trace_parser.add_argument("--query", required=True, help="Query string")
    trace_parser.add_argument(
        "--check-keyword", required=True, help="Keyword to verify in results"
    )
    trace_parser.add_argument("--doc-ids", nargs="*", help="Filter by document IDs")
    trace_parser.add_argument(
        "--k", type=int, default=5, help="Number of documents to retrieve"
    )

    eval_parser = subparsers.add_parser("eval", help="Evaluate RAG using a dataset file")
    eval_parser.add_argument("--config", required=True, help="Path to config YAML")
    eval_parser.add_argument("--questions", nargs="*", help="Questions to evaluate")
    eval_parser.add_argument(
        "--dataset",
        help="Optional dataset JSON file. Defaults to evaluation.dataset_path when --questions is omitted.",
    )
    eval_parser.add_argument("--output", help="Output file for results")

    eval_generate_parser = subparsers.add_parser(
        "eval-generate",
        help="Generate a saved prediction artifact from the main RAG pipeline",
    )
    eval_generate_parser.add_argument("--config", required=True, help="Path to config YAML")
    eval_generate_parser.add_argument("--questions", nargs="*", help="Questions to evaluate")
    eval_generate_parser.add_argument(
        "--dataset",
        help="Optional dataset JSON file. Defaults to evaluation.dataset_path when --questions is omitted.",
    )
    eval_generate_parser.add_argument(
        "--output",
        help="Output file for saved predictions. Defaults to evaluation.prediction_dir/eval_predictions_<model>_<timestamp>.json",
    )
    eval_generate_parser.add_argument("--model", help="Override generation model for this run")
    eval_generate_parser.add_argument("--endpoint", help="Override generation endpoint for this run")
    eval_generate_parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the live RAG API used for generation",
    )
    eval_generate_parser.add_argument("--label", help="Optional label used in the saved artifact filename")
    eval_generate_parser.add_argument("--max-tokens", type=int, help="Override generation max tokens")
    eval_generate_parser.add_argument("--temperature", type=float, help="Override generation temperature")
    eval_generate_parser.add_argument(
        "--reasoning-effort",
        help="Override generation reasoning effort for this run",
    )

    eval_score_parser = subparsers.add_parser(
        "eval-score",
        help="Score a saved prediction artifact with RAGAS without rerunning retrieval or generation",
    )
    eval_score_parser.add_argument("--config", required=True, help="Path to config YAML")
    eval_score_parser.add_argument(
        "--predictions",
        required=True,
        help="Path to a saved prediction artifact JSON file",
    )
    eval_score_parser.add_argument("--output", help="Output file for scored results")
    eval_score_parser.add_argument("--judge-model", help="Override evaluation judge model")
    eval_score_parser.add_argument("--judge-endpoint", help="Override evaluation judge endpoint")
    eval_score_parser.add_argument(
        "--judge-mode",
        choices=["api", "local", "reuse_generation"],
        help="Override evaluation judge mode",
    )
    eval_score_parser.add_argument(
        "--judge-api-key-env",
        help="Override environment variable used for the evaluation judge API key",
    )
    eval_score_parser.add_argument(
        "--eval-embeddings",
        help="Override evaluation embeddings model",
    )
    eval_score_parser.add_argument(
        "--eval-embeddings-endpoint",
        help="Override evaluation embeddings endpoint",
    )
    eval_score_parser.add_argument(
        "--judge-reasoning-effort",
        help="Override judge reasoning effort. Use 'none' to disable reasoning where supported.",
    )
    eval_score_parser.add_argument(
        "--judge-include-thoughts",
        action="store_true",
        help="Request judge thoughts when the backend supports them",
    )

    ingest_parser = subparsers.add_parser("ingest", help="Ingest documents")
    ingest_parser.add_argument("--config", required=True, help="Path to config YAML")
    ingest_parser.add_argument("--paths", nargs="+", help="File paths to ingest")
    ingest_parser.add_argument("--directory", help="Directory to ingest")
    ingest_parser.add_argument("--prefix", default="doc", help="Document ID prefix")

    rebuild_parser = subparsers.add_parser(
        "rebuild-index",
        help="Build a shadow Milvus collection with a fresh ingestion state",
    )
    rebuild_parser.add_argument("--config", required=True, help="Base config YAML")
    rebuild_parser.add_argument("--directory", required=True, help="Directory to ingest")
    rebuild_parser.add_argument("--prefix", default="doc", help="Document ID prefix")
    rebuild_parser.add_argument(
        "--collection-name",
        help="Shadow collection name. Defaults to <base>_rebuild_<timestamp>",
    )
    rebuild_parser.add_argument(
        "--state-path",
        help=(
            "Shadow ingestion state path. Defaults to "
            "storage/rebuilds/<timestamp>/ingestion_state.json"
        ),
    )
    rebuild_parser.add_argument(
        "--rebuild-dir",
        help=(
            "Folder for generated rebuild artifacts. "
            "Defaults to storage/rebuilds/<timestamp> beside --config."
        ),
    )
    rebuild_parser.add_argument(
        "--output-config",
        help="Deprecated override for the generated config path.",
    )

    promote_parser = subparsers.add_parser(
        "promote-index",
        help="Print production config changes for promoting a rebuilt collection",
    )
    promote_parser.add_argument(
        "--rebuild-dir",
        help="Rebuild folder containing config.yaml, ingestion_state.json, and rebuild_manifest.json",
    )
    promote_parser.add_argument(
        "--collection-name",
        help="Fallback rebuilt collection name for legacy promotion flow",
    )
    promote_parser.add_argument(
        "--state-path",
        help="Fallback rebuilt state path for legacy promotion flow",
    )

    cleanup_parser = subparsers.add_parser(
        "cleanup-collection",
        help="Drop an old Milvus collection after a rebuilt one is validated",
    )
    cleanup_parser.add_argument(
        "--rebuild-dir",
        help="Rebuild folder used to infer the old collection name from the manifest",
    )
    cleanup_parser.add_argument(
        "--collection-name",
        help="Collection name to drop when no rebuild manifest is available",
    )
    cleanup_parser.add_argument(
        "--config",
        help="Path to config YAML when dropping a collection without a rebuild manifest",
    )
    cleanup_parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually drop the collection. Without this flag the command is dry-run only.",
    )

    collections_parser = subparsers.add_parser(
        "collections",
        help="List the Milvus collections in the configured database",
    )
    collections_parser.add_argument("--config", required=True, help="Path to config YAML")

    inspect_chunks_parser = subparsers.add_parser("inspect-chunks", help="Inspect chunks before embedding")
    inspect_chunks_parser.add_argument("--config", required=True, help="Path to config YAML")
    inspect_chunks_parser.add_argument("--directory", required=True, help="Directory to process")
    inspect_chunks_parser.add_argument("--output-file", help="Save chunks to file")
    inspect_chunks_parser.add_argument("--show-stats", action="store_true", help="Show chunking statistics")
    inspect_chunks_parser.add_argument("--filter-keyword", help="Filter chunks containing keyword")

    debug_query_parser = subparsers.add_parser("debug-query", help="Debug query with full pipeline inspection")
    debug_query_parser.add_argument("--config", required=True, help="Path to config YAML")
    debug_query_parser.add_argument("--query", required=True, help="Query string")
    debug_query_parser.add_argument("--show-stages", action="store_true", help="Show results at each stage")
    debug_query_parser.add_argument("--output-format", choices=["json", "text", "detailed"], default="json", help="Output format")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "promote-index":
        if args.rebuild_dir:
            bundle = _load_rebuild_manifest(Path(args.rebuild_dir))
        else:
            if not args.collection_name or not args.state_path:
                parser.error(
                    "promote-index requires either --rebuild-dir or both "
                    "--collection-name and --state-path"
                )
            bundle = {
                "rebuild_root": "<legacy>",
                "rebuild_config_path": "<legacy>",
                "rebuild_state_path": args.state_path,
                "rebuild_collection_name": args.collection_name,
                "source_collection_name": None,
            }
        _print_promotion_instructions(bundle)
        return

    if args.command == "cleanup-collection":
        if args.rebuild_dir:
            bundle = _load_rebuild_manifest(Path(args.rebuild_dir))
            collection_name = args.collection_name or bundle.get("source_collection_name")
            config = RAGConfig.from_yaml(str(Path(args.rebuild_dir) / "config.yaml"))
        else:
            collection_name = args.collection_name
            if not args.config:
                parser.error(
                    "cleanup-collection requires --config when --rebuild-dir is not provided"
                )
            config = RAGConfig.from_yaml(args.config)

        if not collection_name:
            parser.error(
                "cleanup-collection requires either --rebuild-dir or --collection-name"
            )
        if not args.yes:
            print(
                "Dry run only. Re-run with --yes to drop collection: "
                f"{collection_name}"
            )
            return

        storage = MilvusClient(
            uri=config.storage.milvus_uri,
            db_name=config.storage.db_name,
        )
        if not storage.has_collection(collection_name):
            print(f"Collection not found, nothing to drop: {collection_name}")
            return
        storage.drop_collection(collection_name)
        print(f"Dropped collection: {collection_name}")
        print(
            json.dumps(
                {
                    "dropped_collection": collection_name,
                    "remaining_collections": storage.list_collections(),
                },
                indent=2,
            )
        )
        return

    if args.command == "rebuild-index":
        if not Path(args.directory).exists():
            parser.error(f"directory does not exist: {args.directory}")

        rebuild_config_path, collection_name, state_path = _build_rebuild_config(
            base_config_path=args.config,
            collection_name=args.collection_name,
            state_path=args.state_path,
            output_config=args.output_config,
            rebuild_dir=args.rebuild_dir,
        )
        config = RAGConfig.from_yaml(str(rebuild_config_path))
        rag = RAGPipeline.from_config(config)
        count = rag.ingest(
            directory=args.directory,
            doc_id_prefix=args.prefix,
        )
        rebuild_root = rebuild_config_path.parent
        manifest_path = rebuild_root / "rebuild_manifest.json"
        manifest = _load_json(manifest_path) if manifest_path.exists() else {}
        manifest.update(
            {
                "completed_at": datetime.now().strftime("%Y%m%d_%H%M%S"),
                "indexed_chunks": count,
            }
        )
        _write_json(manifest_path, manifest)
        _print_rebuild_next_steps(
            rebuild_root=rebuild_root,
            rebuild_config_path=rebuild_config_path,
            collection_name=collection_name,
            state_path=state_path,
            directory=args.directory,
            indexed_count=count,
        )
        return

    if args.command == "collections":
        config = RAGConfig.from_yaml(args.config)
        storage = MilvusClient(
            uri=config.storage.milvus_uri,
            db_name=config.storage.db_name,
        )
        collections = storage.list_collections()
        _print_collection_inventory(config, collections)
        return

    config = RAGConfig.from_yaml(args.config)
    setattr(config, "source_config_path", args.config)
    base_generation_model = config.generation.model_name
    base_generation_endpoint = config.generation.llm_endpoint
    output_label = None
    if args.command == "eval-generate":
        output_label = _apply_eval_generate_overrides(config, args)
    elif args.command == "eval-score":
        _apply_eval_score_overrides(config, args)

    if args.command == "eval-generate":
        questions, ground_truths, dataset_metadata = _resolve_eval_inputs_from_dataset_path(
            args,
            parser,
            config.evaluation.dataset_path,
        )
        generation_override = {
            "model_name": config.generation.model_name,
            "llm_endpoint": config.generation.llm_endpoint,
            "max_tokens": config.generation.max_tokens,
            "temperature": config.generation.temperature,
            "reasoning_effort": config.generation.reasoning_effort,
        }
        results = _generate_eval_predictions_via_api(
            config=config,
            api_base_url=args.api_base_url,
            questions=questions,
            ground_truths=ground_truths,
            dataset_metadata=dataset_metadata,
            generation_override=generation_override,
        )
        output = args.output or _artifact_path_for_label(
            config.evaluation.prediction_dir,
            "eval_predictions",
            output_label,
        )
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Prediction artifact saved to {output_path}")
        should_unload_custom_model = bool(
            args.model and (
                config.generation.model_name != base_generation_model
                or config.generation.llm_endpoint != base_generation_endpoint
            )
        )
        if should_unload_custom_model:
            _unload_ollama_model(
                llm_endpoint=config.generation.llm_endpoint,
                model_name=config.generation.model_name,
            )
        return

    preload_retrieval_models = args.command != "eval-score"
    rag = RAGPipeline.from_config(config) if preload_retrieval_models else RAGPipeline(
        config,
        preload_retrieval_models=False,
    )

    try:
        if args.command == "query":
            result = rag.query(
                query=args.query,
                doc_ids=args.doc_ids,
                k=args.k,
            )
            print(
                json.dumps(
                    {
                        "answer": result.answer,
                        "context": result.context,
                        "num_docs": result.metadata["num_docs"],
                    },
                    indent=2,
                )
            )

        elif args.command == "find-keyword":
            matches = rag.find_keyword(
                keyword=args.keyword,
                doc_id=args.doc_id,
            )
            print(
                json.dumps(
                    {
                        "keyword": args.keyword,
                        "num_matches": len(matches),
                        "matches": matches,
                    },
                    indent=2,
                )
            )

        elif args.command == "trace":
            result = rag.query_with_keyword_check(
                query=args.query,
                check_keyword=args.check_keyword,
                doc_ids=args.doc_ids,
                k=args.k,
            )
            print(json.dumps(result, indent=2, default=str))

        elif args.command == "eval":
            questions, ground_truths, dataset_metadata = _resolve_eval_inputs(args, parser, rag)

            if rag.config.evaluation.model_matrix:
                results = _run_eval_matrix(
                    rag=rag,
                    questions=questions,
                    ground_truths=ground_truths,
                    dataset_metadata=dataset_metadata,
                    output_path=args.output,
                )
                output = results.get("summary_path") or args.output or "eval_matrix_results.json"
            else:
                results = rag.evaluate(
                    questions=questions,
                    ground_truths=ground_truths,
                    dataset_metadata=dataset_metadata,
                )
                output = args.output or results.get("report_path") or "eval_results.json"
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, default=str)
            print(f"Results saved to {output_path}")

        elif args.command == "eval-score":
            prediction_path = Path(args.predictions)
            samples, dataset_metadata = _load_prediction_samples(prediction_path)
            results = rag.score_eval_predictions(
                samples=samples,
                dataset_metadata=dataset_metadata,
                prediction_path=str(prediction_path),
            )
            output = args.output or results.get("report_path") or "eval_results.json"
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, default=str)
            print(f"Scored evaluation report saved to {output_path}")

        elif args.command == "ingest":
            count = rag.ingest(
                paths=args.paths,
                directory=args.directory,
                doc_id_prefix=args.prefix,
            )
            print(f"Indexed {count} chunks")

        elif args.command == "inspect-chunks":
            chunks = rag.save_chunks_before_embedding(
                directory=args.directory,
                output_file=args.output_file
            )

            if args.filter_keyword:
                filtered_chunks = [c for c in chunks if args.filter_keyword.lower() in c.text.lower()]
                print(f"Found {len(filtered_chunks)} chunks containing '{args.filter_keyword}':")
                for i, chunk in enumerate(filtered_chunks):
                    print(f"\n--- Chunk {i+1} ---")
                    print(f"Doc ID: {chunk.doc_id}")
                    print(f"Breadcrumb: {chunk.breadcrumb}")
                    print(f"Page: {chunk.page_number}")
                    print(f"Filename: {chunk.filename}")
                    print(f"Text Preview: {chunk.text[:200]}...")
            else:
                print(f"Total chunks: {len(chunks)}")
                if args.show_stats:
                    total_chars = sum(len(c.text) for c in chunks)
                    avg_chars = total_chars / len(chunks) if chunks else 0
                    print(f"Total characters: {total_chars}")
                    print(f"Average characters per chunk: {avg_chars:.2f}")
                    print(f"Unique documents: {len(set(c.doc_id for c in chunks))}")

                    if chunks:
                        print("\nFirst few chunks:")
                        for i, chunk in enumerate(chunks[:3]):
                            print(f"\n--- Chunk {i+1} ---")
                            print(f"Doc ID: {chunk.doc_id}")
                            print(f"Breadcrumb: {chunk.breadcrumb}")
                            print(f"Page: {chunk.page_number}")
                            print(f"Filename: {chunk.filename}")
                            print(f"Text Preview: {chunk.text[:200]}...")

        elif args.command == "debug-query":
            print(f"Processing query: {args.query}")

            if args.show_stages:
                print("\n1. Retrieving documents...")
                docs = rag.retriever.retrieve(
                    query=args.query,
                    collection_name=rag.config.storage.collection_name,
                    k=rag.config.retrieval.k,
                )
                print(f"Retrieved {len(docs)} documents after RRF fusion")

                print("\n2. Applying reranking...")
                reranked_docs = rag.retriever._rerank(args.query, docs)
                # Slice to rerank_top_k to match the pipeline behavior
                rerank_top_k = rag.config.retrieval.rerank_top_k
                reranked_docs = reranked_docs[:rerank_top_k]
                print(f"Reranked to top {len(reranked_docs)} documents")

                if args.output_format == "detailed":
                    print("\nDetailed results:")
                    for i, doc in enumerate(reranked_docs):
                        print(f"\n--- Document {i+1} (Score: {doc.score:.4f}) ---")
                        print(f"Doc ID: {doc.doc_id}")
                        print(f"Breadcrumb: {doc.metadata.get('breadcrumb', 'N/A')}")
                        print(f"Page: {doc.metadata.get('page_number', 'N/A')}")
                        print(f"Text Preview: {doc.text[:300]}...")
                elif args.output_format == "text":
                    print("\nContext that would be sent to LLM:")
                    for i, doc in enumerate(reranked_docs):
                        print(f"\n[Source {doc.metadata.get('breadcrumb', f'Doc_{i+1}')}]")
                        print(doc.text)
                else:  # json format
                    result = {
                        "query": args.query,
                        "retrieved_count": len(docs),
                        "reranked_count": len(reranked_docs),
                        "documents": [
                            {
                                "doc_id": doc.doc_id,
                                "breadcrumb": doc.metadata.get("breadcrumb", "N/A"),
                                "page_number": doc.metadata.get("page_number", "N/A"),
                                "score": doc.score,
                                "text_preview": doc.text[:300] + "..." if len(doc.text) > 300 else doc.text
                            }
                            for doc in reranked_docs
                        ]
                    }
                    print(json.dumps(result, indent=2, default=str))
            else:
                # Just run the normal query
                result = rag.query(query=args.query)
                print(json.dumps({
                    "answer": result.answer,
                    "context": result.context,
                    "num_docs": result.metadata["num_docs"],
                }, indent=2))
    finally:
        rag.close()


if __name__ == "__main__":
    main()
