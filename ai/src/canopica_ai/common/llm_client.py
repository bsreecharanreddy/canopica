"""LLM generation abstraction shared by every AI capability that calls a
generation model -- Task 2's Policy Q&A today, Tasks 3/5/6 later. Every call
site here takes an `LlmClient`, never talks to Ollama directly, so Task 9 can
add a second (`OpenRouterTieredClient`) implementation behind the same
interface without touching any of them.
"""

from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import BaseModel

from canopica_ai.config import Settings


class LlmResponse(BaseModel):
    text: str


class LlmClient(Protocol):
    def generate(self, prompt: str) -> LlmResponse: ...


class OllamaClient:
    """The sole `LlmClient` implementation until Task 9's tiered
    OpenRouter-backed one lands behind the same interface."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()

    def generate(self, prompt: str) -> LlmResponse:
        settings = self._settings
        response = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.ollama_generation_model,
                "prompt": prompt,
                "stream": False,
                # Every value here is settings-driven and measured -- see
                # canopica_ai.config.Settings for why each one is what it is.
                "options": {
                    "temperature": settings.ollama_temperature,
                    "num_predict": settings.ollama_num_predict,
                },
                "keep_alive": settings.ollama_keep_alive,
            },
            timeout=settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        text: str = response.json()["response"]
        return LlmResponse(text=text)
