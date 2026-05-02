from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, List, Any

from langchain_core.outputs import ChatGeneration, Generation, LLMResult
from ragas.llms.base import BaseRagasLLM, InstructorBaseRagasLLM


_THOUGHT_BLOCK_RE = re.compile(r"<thought>.*?</thought>", re.DOTALL | re.IGNORECASE)
_FENCED_JSON_RE = re.compile(
    r"^\s*```(?:json)?\s*(.*?)\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
)


def _sanitize_generation_text(text: str) -> str:
    cleaned = _THOUGHT_BLOCK_RE.sub("", text).strip()
    fenced_match = _FENCED_JSON_RE.match(cleaned)
    if fenced_match:
        cleaned = fenced_match.group(1).strip()
    return cleaned


def _sanitize_llm_result(result: LLMResult) -> LLMResult:
    for batch in result.generations:
        for generation in batch:
            if isinstance(generation, ChatGeneration):
                generation.text = _sanitize_generation_text(generation.text)
                if generation.message is not None and isinstance(generation.message.content, str):
                    generation.message.content = _sanitize_generation_text(
                        generation.message.content
                    )
            elif isinstance(generation, Generation):
                generation.text = _sanitize_generation_text(generation.text)
    return result


@dataclass
class SanitizedBaseRagasLLM(BaseRagasLLM):
    inner: BaseRagasLLM
    run_config: Any = field(init=False, repr=False)
    multiple_completion_supported: bool = field(init=False, repr=False)
    cache: Optional[Any] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.run_config = getattr(self.inner, "run_config", self.run_config)
        self.multiple_completion_supported = getattr(
            self.inner,
            "multiple_completion_supported",
            False,
        )

    def set_run_config(self, run_config):
        if hasattr(self.inner, "set_run_config"):
            self.inner.set_run_config(run_config)
        self.run_config = getattr(self.inner, "run_config", run_config)

    def is_finished(self, response: LLMResult) -> bool:
        return self.inner.is_finished(response)

    def generate_text(
        self,
        prompt,
        n: int = 1,
        temperature: float = 0.01,
        stop: Optional[List[str]] = None,
        callbacks=None,
    ) -> LLMResult:
        result = self.inner.generate_text(
            prompt=prompt,
            n=n,
            temperature=temperature,
            stop=stop,
            callbacks=callbacks,
        )
        return _sanitize_llm_result(result)

    async def agenerate_text(
        self,
        prompt,
        n: int = 1,
        temperature: Optional[float] = 0.01,
        stop: Optional[List[str]] = None,
        callbacks=None,
    ) -> LLMResult:
        result = await self.inner.agenerate_text(
            prompt=prompt,
            n=n,
            temperature=temperature,
            stop=stop,
            callbacks=callbacks,
        )
        return _sanitize_llm_result(result)


@dataclass
class SanitizedInstructorLLM(InstructorBaseRagasLLM):
    inner: InstructorBaseRagasLLM

    def generate(self, prompt: str, response_model):
        result = self.inner.generate(prompt, response_model)
        return self._sanitize_model(result)

    async def agenerate(self, prompt: str, response_model):
        result = await self.inner.agenerate(prompt, response_model)
        return self._sanitize_model(result)

    @staticmethod
    def _sanitize_model(result):
        # Instructor path already returns parsed Pydantic models when successful,
        # so we just pass them through unchanged.
        return result


def sanitize_ragas_llm(inner):
    if isinstance(inner, BaseRagasLLM):
        return SanitizedBaseRagasLLM(inner)
    if isinstance(inner, InstructorBaseRagasLLM):
        return SanitizedInstructorLLM(inner)
    return inner
