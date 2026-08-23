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
        response = httpx.post(
            f"{self._settings.ollama_base_url}/api/generate",
            json={
                "model": self._settings.ollama_generation_model,
                "prompt": prompt,
                "stream": False,
            },
            # Empirically measured (2026-08-23) against this dev machine's
            # real CPU-bound generation, sharing a host with OpenSearch/
            # Keycloak/portal-api: successful /api/generate calls routinely
            # took 1m10s-1m44s; a 120s timeout actually cut one off at
            # exactly 2m0s (Ollama logged it as a 500 once the client gave
            # up). 240s keeps real headroom above the observed worst case
            # rather than being a guessed round number.
            timeout=240.0,
        )
        response.raise_for_status()
        text: str = response.json()["response"]
        return LlmResponse(text=text)
