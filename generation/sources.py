from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit


def build_public_sources(retrieved_docs: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Build deduplicated public source metadata from chunk-level docs."""
    if not retrieved_docs:
        return []

    sources_by_key: Dict[str, Dict[str, Any]] = {}
    page_sets: Dict[str, set[int]] = {}

    for doc in retrieved_docs:
        metadata = getattr(doc, "metadata", {}) or {}
        pdf_url = _clean_value(metadata.get("pdf_url"))
        page_url = _clean_value(metadata.get("page_url")) or _clean_value(
            metadata.get("source_url")
        )
        scraped_at = _clean_value(metadata.get("scraped_at"))
        page_number = _coerce_page_number(metadata.get("page_number"))

        key = _dedupe_key(pdf_url, page_url)
        if key not in sources_by_key:
            is_pdf_source = bool(pdf_url)
            sources_by_key[key] = {
                "pdf_url": pdf_url,
                "page_url": page_url,
                "scraped_at": scraped_at,
                "page": page_number if is_pdf_source else None,
                "pages": [],
            }
            page_sets[key] = set()

        source = sources_by_key[key]
        if source["pdf_url"] is None and pdf_url is not None:
            source["pdf_url"] = pdf_url
        if source["page_url"] is None and page_url is not None:
            source["page_url"] = page_url
        if source["scraped_at"] is None and scraped_at is not None:
            source["scraped_at"] = scraped_at

        if source["pdf_url"] and page_number is not None:
            if source["page"] is None:
                source["page"] = page_number
            page_sets[key].add(page_number)

    for key, source in sources_by_key.items():
        source["pages"] = sorted(page_sets[key])

    return list(sources_by_key.values())


def _dedupe_key(pdf_url: Optional[str], page_url: Optional[str]) -> str:
    if pdf_url:
        return f"pdf:{_normalize_url(pdf_url)}"
    if page_url:
        return f"page:{_normalize_url(page_url)}"
    return "missing-url"


def _normalize_url(url: str) -> str:
    value = url.strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or parsed.path
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _clean_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "unknown":
        return None
    return text


def _coerce_page_number(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None
