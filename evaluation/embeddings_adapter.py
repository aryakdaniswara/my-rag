from __future__ import annotations

import asyncio
from typing import List

from embedding.dense import DenseEmbeddingModel


class LocalDenseRagasEmbeddings:
    """RAGAS-compatible adapter around the repo's dense embedding model."""

    def __init__(
        self,
        model_name: str,
        device: str,
        batch_size: int = 8,
        quantize_8bit: bool = False,
        query_prompt_name: str = "web_search_query",
    ):
        self._embedder = DenseEmbeddingModel(
            model_name=model_name,
            device=device,
            query_prompt_name=query_prompt_name,
            quantize_8bit=quantize_8bit,
        )
        self.batch_size = batch_size

    def embed_query(self, text: str) -> List[float]:
        return self._embedder.embed_query(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embedder.embed_documents(texts)

    async def aembed_query(self, text: str) -> List[float]:
        return await asyncio.to_thread(self.embed_query, text)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        return await asyncio.to_thread(self.embed_documents, texts)
