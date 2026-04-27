from typing import Any, Dict, List
from ingestion.base import ChunkRecord
import logging
import os
logger = logging.getLogger(__name__)


class Chunker:
    """Chunk Docling documents and plain extracted text."""

    def __init__(
        self,
        embedding_model: str = "microsoft/harrier-oss-v1-0.6b",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        pdf_min_chunk_tokens: int = 300,
        pdf_max_chunk_tokens: int = 1000,
        pdf_split_overlap_tokens: int = 120,
    ):
        self.chunk_size = max(1, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size - 1))
        self.pdf_min_chunk_tokens = max(1, pdf_min_chunk_tokens)
        self.pdf_max_chunk_tokens = max(self.pdf_min_chunk_tokens, pdf_max_chunk_tokens)
        self.pdf_split_overlap_tokens = max(
            0,
            min(pdf_split_overlap_tokens, self.pdf_max_chunk_tokens - 1),
        )
        logger.info(
            "Using Docling HierarchicalChunker with hybrid normalization: "
            "pdf_min_chunk_tokens=%s, pdf_max_chunk_tokens=%s, "
            "pdf_split_overlap_tokens=%s. HTML keeps chunk_size=%s and "
            "chunk_overlap=%s.",
            self.pdf_min_chunk_tokens,
            self.pdf_max_chunk_tokens,
            self.pdf_split_overlap_tokens,
            self.chunk_size,
            self.chunk_overlap,
        )
        self.chunker = None

    def chunk(
        self,
        docling_doc,
        filename: str,
        doc_id: str = "",
        external_metadata: dict = None,
    ) -> List[ChunkRecord]:
        """
        Use HierarchicalChunker to preserve document structure.
        """
        from docling.chunking import HierarchicalChunker

        if external_metadata is None:
            external_metadata = {}
        if self.chunker is None:
            self.chunker = HierarchicalChunker()

        raw_chunks = []
        # Priority: pdf_url > source_url > page_url
        source_url = (
            external_metadata.get("pdf_url")
            or external_metadata.get("source_url")
            or external_metadata.get("page_url", "")
        )

        for chunk in self.chunker.chunk(docling_doc):
            chunk_text = chunk.text

            # --- Breadcrumb replacement ---
            # We no longer use structural breadcrumbs. Metadata URLs are used instead downstream.
            breadcrumb = ""

            # Page number
            page_number = None
            if hasattr(chunk.meta, "doc_items") and chunk.meta.doc_items:
                item = chunk.meta.doc_items[0]
                if hasattr(item, "prov") and item.prov:
                    page_number = item.prov[0].page_no

            # Merge Docling metadata with external metadata
            full_metadata = chunk.meta.to_dict() if hasattr(chunk.meta, "to_dict") else {}
            full_metadata.update(external_metadata)
            # Ensure source_url is explicitly present
            full_metadata["source_url"] = source_url
            full_metadata["chunking_strategy"] = "hierarchical_hybrid"

            raw_chunks.append(
                {
                    "text": chunk_text,
                    "doc_id": doc_id or chunk.chunk_id,
                    "breadcrumb": breadcrumb,
                    "page_number": page_number,
                    "filename": filename,
                    "metadata": full_metadata,
                }
            )

        normalized_chunks = self._normalize_hierarchical_chunks(raw_chunks)
        return [
            ChunkRecord(
                text=chunk["text"],
                doc_id=chunk["doc_id"],
                chunk_index=index,
                breadcrumb=chunk["breadcrumb"],
                page_number=chunk["page_number"],
                filename=chunk["filename"],
                metadata=chunk["metadata"],
            )
            for index, chunk in enumerate(normalized_chunks)
        ]

    def chunk_text(
        self,
        text: str,
        filename: str,
        doc_id: str = "",
        external_metadata: dict = None,
    ) -> List[ChunkRecord]:
        """Split plain text into overlapping chunks using configured token-like units."""
        if external_metadata is None:
            external_metadata = {}

        normalized_text = "\n".join(
            line.strip() for line in text.splitlines() if line.strip()
        )
        if not normalized_text:
            return []

        source_url = (
            external_metadata.get("pdf_url")
            or external_metadata.get("source_url")
            or external_metadata.get("page_url", "")
        )

        records = []
        for chunk_text in self._split_text(normalized_text):
            metadata = dict(external_metadata)
            metadata["source_url"] = source_url
            metadata["chunking_strategy"] = "standard_text"

            records.append(
                ChunkRecord(
                    text=chunk_text,
                    doc_id=doc_id or os.path.splitext(os.path.basename(filename))[0],
                    chunk_index=len(records),
                    breadcrumb="",
                    page_number=None,
                    filename=filename,
                    metadata=metadata,
                )
            )

        return records

    def _split_text(self, text: str) -> List[str]:
        return self._split_tokens(text.split())

    def _split_tokens(self, tokens: List[str]) -> List[str]:
        chunks = []
        step = self.chunk_size - self.chunk_overlap
        for start in range(0, len(tokens), step):
            chunk_tokens = tokens[start : start + self.chunk_size]
            if chunk_tokens:
                chunks.append(" ".join(chunk_tokens))
            if start + self.chunk_size >= len(tokens):
                break
        return chunks

    def _split_tokens_with_window(
        self,
        tokens: List[str],
        chunk_size: int,
        chunk_overlap: int,
    ) -> List[List[str]]:
        chunk_size = max(1, chunk_size)
        chunk_overlap = max(0, min(chunk_overlap, chunk_size - 1))
        step = chunk_size - chunk_overlap
        chunks = []
        for start in range(0, len(tokens), step):
            chunk_tokens = tokens[start : start + chunk_size]
            if chunk_tokens:
                chunks.append(chunk_tokens)
            if start + chunk_size >= len(tokens):
                break
        return chunks

    def _normalize_hierarchical_chunks(
        self,
        raw_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged_chunks = self._merge_small_hierarchical_chunks(raw_chunks)
        normalized = []
        for chunk in merged_chunks:
            normalized.extend(self._split_large_hierarchical_chunk(chunk))
        return normalized

    def _merge_small_hierarchical_chunks(
        self,
        raw_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged_chunks: List[Dict[str, Any]] = []
        pending_group: List[Dict[str, Any]] = []
        pending_tokens = 0

        for chunk in raw_chunks:
            chunk_tokens = self._estimate_token_count(chunk["text"])
            if chunk_tokens >= self.pdf_min_chunk_tokens:
                if pending_group:
                    merged_chunks.append(self._merge_chunk_group(pending_group))
                    pending_group = []
                    pending_tokens = 0
                merged_chunks.append(self._clone_chunk_dict(chunk))
                continue

            pending_group.append(chunk)
            pending_tokens += chunk_tokens
            if pending_tokens >= self.pdf_min_chunk_tokens:
                merged_chunks.append(self._merge_chunk_group(pending_group))
                pending_group = []
                pending_tokens = 0

        if pending_group:
            if merged_chunks:
                merged_chunks[-1] = self._merge_chunk_group(
                    [merged_chunks[-1], *pending_group]
                )
            else:
                merged_chunks.append(self._merge_chunk_group(pending_group))

        return merged_chunks

    def _merge_chunk_group(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        chunk_group = [
            self._clone_chunk_dict(chunk)
            for chunk in chunks
            if chunk["text"].strip()
        ]
        if not chunk_group:
            return self._clone_chunk_dict(chunks[0])

        merged_text = "\n\n".join(chunk["text"].strip() for chunk in chunk_group)
        merged_metadata = dict(chunk_group[0]["metadata"])
        merged_metadata["chunking_strategy"] = "hierarchical_hybrid"
        merged_metadata["chunk_merge_count"] = len(chunk_group)
        merged_metadata["was_split_from_hierarchical"] = False
        merged_metadata["merged_from_page_numbers"] = [
            chunk["page_number"]
            for chunk in chunk_group
            if chunk.get("page_number") is not None
        ]

        return {
            "text": merged_text,
            "doc_id": chunk_group[0]["doc_id"],
            "breadcrumb": chunk_group[0]["breadcrumb"],
            "page_number": chunk_group[0]["page_number"],
            "filename": chunk_group[0]["filename"],
            "metadata": merged_metadata,
        }

    def _split_large_hierarchical_chunk(
        self,
        chunk: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        tokens = chunk["text"].split()
        if len(tokens) <= self.pdf_max_chunk_tokens:
            normalized_chunk = self._clone_chunk_dict(chunk)
            normalized_chunk["metadata"]["chunking_strategy"] = "hierarchical_hybrid"
            normalized_chunk["metadata"].setdefault("chunk_merge_count", 1)
            normalized_chunk["metadata"]["was_split_from_hierarchical"] = False
            return [normalized_chunk]

        split_token_groups = self._split_tokens_with_window(
            tokens,
            chunk_size=self.pdf_max_chunk_tokens,
            chunk_overlap=self.pdf_split_overlap_tokens,
        )
        split_chunks = []
        for split_index, token_group in enumerate(split_token_groups):
            split_metadata = dict(chunk["metadata"])
            split_metadata["chunking_strategy"] = "hierarchical_hybrid"
            split_metadata["chunk_merge_count"] = split_metadata.get("chunk_merge_count", 1)
            split_metadata["was_split_from_hierarchical"] = True
            split_metadata["hierarchical_split_index"] = split_index
            split_metadata["hierarchical_split_count"] = len(split_token_groups)

            split_chunks.append(
                {
                    "text": " ".join(token_group),
                    "doc_id": chunk["doc_id"],
                    "breadcrumb": chunk["breadcrumb"],
                    "page_number": chunk["page_number"],
                    "filename": chunk["filename"],
                    "metadata": split_metadata,
                }
            )

        return split_chunks

    @staticmethod
    def _estimate_token_count(text: str) -> int:
        return len(text.split())

    @staticmethod
    def _clone_chunk_dict(chunk: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "text": chunk["text"],
            "doc_id": chunk["doc_id"],
            "breadcrumb": chunk.get("breadcrumb", ""),
            "page_number": chunk.get("page_number"),
            "filename": chunk.get("filename", ""),
            "metadata": dict(chunk.get("metadata") or {}),
        }
