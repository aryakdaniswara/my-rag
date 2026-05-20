from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import logging
import re

from generation.sources import build_public_sources

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    answer: str
    context: str
    sources: List[Dict[str, Any]] = None
    metadata: Dict[str, Any] = None
    confidence_score: Optional[float] = None
    raw_response: Optional[str] = None

    def __post_init__(self):
        if self.sources is None:
            self.sources = []
        if self.metadata is None:
            self.metadata = {}


class LLM:
    """Local LLM wrapper supporting vLLM and HuggingFace."""

    def __init__(
        self,
        # These values are fallback defaults only; the pipeline injects
        # config-driven runtime settings in normal app execution.
        endpoint: str = "http://localhost:8000/v1",
        model_name: str = "llama-3-8b",
        max_tokens: int = 512,
        temperature: float = 0.0,
        reasoning_effort: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ):
        self.endpoint = endpoint
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.system_prompt = system_prompt
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from openai import OpenAI

                # Increased timeout to 300s to accommodate local model loading/inference
                self._client = OpenAI(
                    base_url=self.endpoint, 
                    api_key="dummy",
                    timeout=300.0
                )
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")
        return self._client

    def _resolve_think_value(self) -> Optional[Any]:
        if self.reasoning_effort is None:
            return None

        value = str(self.reasoning_effort).strip().lower()
        if value in {"none", "off", "false", "0"}:
            return "none"
        if value in {"true", "on", "1"}:
            return "high"
        if value in {"low", "medium", "high"}:
            return value
        return self.reasoning_effort

    def _chat_request_kwargs(
        self,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        kwargs = {
            "model": self.model_name,
            "messages": [],
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": self.temperature,
        }
        reasoning_effort = self._resolve_think_value()
        if reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort
        return kwargs

    def _format_context(
        self,
        retrieved_docs: Optional[List[Any]] = None,
        context: Optional[str] = None,
    ) -> str:
        if retrieved_docs:
            context_parts = []
            for doc in retrieved_docs:
                pdf = doc.metadata.get("pdf_url")
                page = doc.metadata.get("page_url")
                scraped = doc.metadata.get("scraped_at", "N/A")
                date_str = scraped.split("T")[0] if "T" in scraped else scraped

                url_part = f"{pdf}" if pdf else ""
                if page:
                    url_part = f"{url_part} | {page}" if url_part else page

                citation = f"Source [{url_part} (Scraped: {date_str})]"
                context_parts.append(f"{citation}: {doc.text}")

            return "\n\n".join(context_parts)

        return context or "No context provided."

    def _build_messages(
        self,
        prompt: str,
        formatted_context: str,
    ) -> List[Dict[str, str]]:
        from generation.prompts import DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT

        system_template = self.system_prompt or DEFAULT_SYSTEM_PROMPT
        system_content = system_template.format(context=formatted_context)
        user_content = DEFAULT_USER_PROMPT.format(question=prompt)
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    def generate(
        self,
        prompt: str,
        retrieved_docs: Optional[List[Any]] = None,
        context: Optional[str] = None,
    ) -> GenerationResult:
        formatted_context = self._format_context(
            retrieved_docs=retrieved_docs,
            context=context,
        )

        try:
            request_kwargs = self._chat_request_kwargs()
            request_kwargs["messages"] = self._build_messages(
                prompt=prompt,
                formatted_context=formatted_context,
            )
            request_kwargs["stream"] = False
            response = self.client.chat.completions.create(**request_kwargs)
            raw_content = response.choices[0].message.content or ""
            clean_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
            answer = clean_content

            sources = build_public_sources(retrieved_docs)

            return GenerationResult(
                answer=answer,
                context=formatted_context,
                sources=sources,
                confidence_score=None,
                raw_response=raw_content,
            )
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return GenerationResult(
                answer="Error generating response",
                context=formatted_context,
                sources=[],
                confidence_score=None,
            )

    def generate_stream(
        self,
        prompt: str,
        retrieved_docs: Optional[List[Any]] = None,
        context: Optional[str] = None,
    ):
        """Yield tokens as they are generated by the LLM."""
        formatted_context = self._format_context(
            retrieved_docs=retrieved_docs,
            context=context,
        )

        try:
            request_kwargs = self._chat_request_kwargs()
            request_kwargs["messages"] = self._build_messages(
                prompt=prompt,
                formatted_context=formatted_context,
            )
            request_kwargs["stream"] = True
            stream = self.client.chat.completions.create(**request_kwargs)
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            yield f"\n[Error: {e}]"

    def batch_generate(
        self, prompts: List[str], contexts: Optional[List[str]] = None
    ) -> List[GenerationResult]:
        if contexts is None:
            contexts = [None] * len(prompts)

        results = []
        for prompt, ctx in zip(prompts, contexts):
            results.append(self.generate(prompt, context=ctx))
        return results
