import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data = _expand_env_vars(data)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data


def _expand_env_vars(value):
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env_vars(item) for key, item in value.items()}
    return value


def _merge_dicts(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_config(path: Path) -> dict:
    data = _load_yaml(path)
    extends_value = data.pop("extends", None)
    if not extends_value:
        return data

    if isinstance(extends_value, str):
        extends_paths = [extends_value]
    elif isinstance(extends_value, list) and all(isinstance(item, str) for item in extends_value):
        extends_paths = extends_value
    else:
        raise ValueError(f"'extends' must be a string or list of strings: {path}")

    merged: dict = {}
    for parent in extends_paths:
        merged = _merge_dicts(merged, _load_config((path.parent / parent).resolve()))
    return _merge_dicts(merged, data)


def _http_get_json(url: str, headers: dict | None = None, timeout: int = 10) -> tuple[int, object]:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.getcode()
        raw = response.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return status, payload


def _print_ok(message: str) -> None:
    print(f"[OK] {message}")


def _fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    raise SystemExit(1)


def _ensure_dir(path_str: str, label: str) -> None:
    path = Path(path_str)
    path.mkdir(parents=True, exist_ok=True)
    _print_ok(f"{label} directory ready: {path}")


def _check_file(path_str: str, label: str) -> Path:
    path = Path(path_str)
    if not path.exists():
        _fail(f"{label} not found: {path}")
    _print_ok(f"{label} found: {path}")
    return path


def _check_api_health(api_base_url: str) -> None:
    health_url = f"{api_base_url.rstrip('/')}/health"
    try:
        status, payload = _http_get_json(health_url)
    except Exception as exc:
        _fail(f"RAG API health check failed at {health_url}: {exc}")

    if status != 200:
        _fail(f"RAG API health check returned status {status} at {health_url}")

    if isinstance(payload, dict) and payload.get("status") == "uninitialized":
        _fail(f"RAG API is reachable but uninitialized at {health_url}")

    _print_ok(f"RAG API healthy at {health_url}")


def _build_auth_headers(api_key_env: str | None) -> dict:
    headers = {}
    if api_key_env:
        api_key = os.getenv(api_key_env)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            _print_ok(f"API key env is set: {api_key_env}")
        else:
            print(f"[WARN] API key env is not set: {api_key_env}")
    return headers


def _check_openai_compatible_endpoint(
    endpoint: str | None,
    label: str,
    api_key_env: str | None = None,
) -> object:
    if not endpoint:
        _fail(f"No {label} endpoint configured")

    headers = _build_auth_headers(api_key_env)
    models_url = f"{endpoint.rstrip('/')}/models"
    try:
        status, payload = _http_get_json(models_url, headers=headers)
    except urllib.error.HTTPError as exc:
        _fail(f"{label} endpoint reachable but /models returned HTTP {exc.code}: {models_url}")
    except Exception as exc:
        _fail(f"{label} endpoint check failed at {models_url}: {exc}")

    if status != 200:
        _fail(f"{label} endpoint /models returned status {status}: {models_url}")

    _print_ok(f"{label} endpoint healthy at {models_url}")
    return payload


def _slugify(value: str | None, fallback: str = "model") -> str:
    if not value:
        return fallback
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return slug.strip("._-") or fallback


def _parse_model_spec_tokens(tokens: str | None) -> list[dict]:
    specs = []
    for token in (tokens or "").split():
        if "|" in token:
            parts = token.split("|")
            model_name = parts[0].strip()
            label = parts[1].strip() if len(parts) > 1 and parts[1].strip() else _slugify(model_name)
            rerank_top_k = parts[2].strip() if len(parts) > 2 and parts[2].strip() != "-" else None
        elif "=" in token:
            model_name, label = token.split("=", 1)
            model_name = model_name.strip()
            label = label.strip() or _slugify(model_name)
            rerank_top_k = None
        else:
            model_name = token.strip()
            label = _slugify(model_name)
            rerank_top_k = None

        if model_name:
            specs.append(
                {
                    "model_name": model_name,
                    "label": label,
                    "rerank_top_k": rerank_top_k,
                }
            )
    return specs


def _matrix_model_specs(config: dict, override_tokens: str | None = None) -> list[dict]:
    override_specs = _parse_model_spec_tokens(override_tokens)
    if override_specs:
        return override_specs

    evaluation = config.get("evaluation", {}) or {}
    model_matrix = evaluation.get("model_matrix") or []
    specs = []
    if isinstance(model_matrix, list):
        for item in model_matrix:
            if not isinstance(item, dict):
                continue
            model_name = item.get("model_name")
            if not isinstance(model_name, str) or not model_name.strip():
                continue
            label = item.get("label")
            rerank_top_k = item.get("rerank_top_k")
            specs.append(
                {
                    "model_name": model_name.strip(),
                    "label": label.strip() if isinstance(label, str) and label.strip() else _slugify(model_name),
                    "rerank_top_k": str(rerank_top_k) if rerank_top_k is not None else None,
                }
            )

    if specs:
        return specs

    generation = config.get("generation", {}) or {}
    model_name = generation.get("model_name")
    if isinstance(model_name, str) and model_name.strip():
        return [
            {
                "model_name": model_name.strip(),
                "label": _slugify(model_name),
                "rerank_top_k": None,
            }
        ]
    return []


def _format_model_specs(specs: list[dict]) -> str:
    tokens = []
    for spec in specs:
        rerank_top_k = spec.get("rerank_top_k") or "-"
        tokens.append(f"{spec['model_name']}|{spec['label']}|{rerank_top_k}")
    return " ".join(tokens)


def _format_labels(specs: list[dict]) -> str:
    return " ".join(spec["label"] for spec in specs if spec.get("label"))


def _model_ids_from_payload(payload: object) -> set[str]:
    model_ids: set[str] = set()
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    model_id = item.get("id") or item.get("name") or item.get("model")
                    if isinstance(model_id, str):
                        model_ids.add(model_id)
                elif isinstance(item, str):
                    model_ids.add(item)

        models = payload.get("models")
        if isinstance(models, list):
            for item in models:
                if isinstance(item, dict):
                    model_id = item.get("id") or item.get("name") or item.get("model")
                    if isinstance(model_id, str):
                        model_ids.add(model_id)
                elif isinstance(item, str):
                    model_ids.add(item)
    return model_ids


def _check_models_available(
    endpoint: str | None,
    label: str,
    required_models: list[str],
    api_key_env: str | None = None,
) -> None:
    unique_required = []
    seen = set()
    for model in required_models:
        if model and model not in seen:
            unique_required.append(model)
            seen.add(model)

    if not unique_required:
        _fail(f"No required {label} models found in config")

    payload = _check_openai_compatible_endpoint(endpoint, label, api_key_env=api_key_env)
    available_models = _model_ids_from_payload(payload)
    if not available_models:
        _fail(f"{label} endpoint /models response did not include model IDs")

    missing = [model for model in unique_required if model not in available_models]
    if missing:
        _fail(
            f"{label} endpoint is missing required models: {', '.join(missing)}"
        )

    _print_ok(f"{label} models available: {', '.join(unique_required)}")


def _check_judge_endpoint(config: dict, explicit_judge_endpoint: str | None = None) -> None:
    evaluation = config.get("evaluation", {}) or {}
    judge_endpoint = explicit_judge_endpoint or evaluation.get("eval_llm_endpoint")
    if not judge_endpoint:
        _fail("No evaluation judge endpoint configured")

    _check_models_available(
        endpoint=judge_endpoint,
        label="Judge",
        required_models=[evaluation.get("eval_llm")],
        api_key_env=evaluation.get("eval_llm_api_key_env"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight checks for eval scripts")
    parser.add_argument("--mode", choices=["generate", "score", "full"], required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--api-base-url")
    parser.add_argument("--predictions")
    parser.add_argument("--judge-endpoint")
    parser.add_argument("--model-specs")
    parser.add_argument("--run-dir")
    parser.add_argument("--emit-model-specs", action="store_true")
    parser.add_argument("--emit-labels", action="store_true")
    args = parser.parse_args()

    if args.emit_model_specs or args.emit_labels:
        config_path = Path(args.config)
        if not config_path.exists():
            _fail(f"config not found: {config_path}")
    else:
        config_path = _check_file(args.config, "config")
    config = _load_config(config_path.resolve())
    model_specs = _matrix_model_specs(config, override_tokens=args.model_specs)

    if args.emit_model_specs:
        print(_format_model_specs(model_specs))
        return

    if args.emit_labels:
        print(_format_labels(model_specs))
        return

    evaluation = config.get("evaluation", {}) or {}
    dataset_path = evaluation.get("dataset_path")
    run_dir = args.run_dir or evaluation.get("run_dir", "storage/eval_runs")
    _ensure_dir(run_dir, "eval run root")

    if args.mode == "generate":
        if not args.api_base_url:
            _fail("--api-base-url is required for generate preflight")
        if not dataset_path:
            _fail("evaluation.dataset_path is not configured")
        _check_file(dataset_path, "evaluation dataset")
        _check_api_health(args.api_base_url)
        generation = config.get("generation", {}) or {}
        _check_models_available(
            endpoint=generation.get("llm_endpoint"),
            label="Generation",
            required_models=[spec["model_name"] for spec in model_specs],
            api_key_env="OPENAI_API_KEY",
        )
        print("[OK] Generate preflight passed")
        return

    if args.mode == "score":
        if not args.predictions:
            _fail("--predictions is required for score preflight")
        _check_file(args.predictions, "prediction artifact")
        _check_judge_endpoint(config, explicit_judge_endpoint=args.judge_endpoint)
        print("[OK] Score preflight passed")
        return

    if args.mode == "full":
        if not dataset_path:
            _fail("evaluation.dataset_path is not configured")
        _check_file(dataset_path, "evaluation dataset")
        generation = config.get("generation", {}) or {}
        _check_models_available(
            endpoint=generation.get("llm_endpoint"),
            label="Generation",
            required_models=[spec["model_name"] for spec in model_specs],
            api_key_env="OPENAI_API_KEY",
        )
        if (evaluation.get("judge_mode") or "").lower() == "api":
            _check_judge_endpoint(config, explicit_judge_endpoint=args.judge_endpoint)
        print("[OK] Full eval preflight passed")
        return


if __name__ == "__main__":
    main()
