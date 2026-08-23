"""Unit tests for the shared LLM client's request construction.

No real Ollama and no network: `httpx.post` is swapped for a capturing
stub, so these assert on the exact request body this client builds from
its own settings -- the thing that actually determines generation cost and
determinism -- rather than on a live model's (slow, non-deterministic)
output, which `test_policy_qa.py`'s e2e tests already cover.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from canopica_ai.common.llm_client import OllamaClient
from canopica_ai.config import Settings


@pytest.fixture
def captured_request(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_post(url: str, *, json: dict[str, Any], timeout: float) -> httpx.Response:
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return httpx.Response(
            200, json={"response": "grounded answer citing 273.9(a)"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    return captured


class TestGenerationOptions:
    """Every knob that bounds generation cost is settings-driven, so CI and
    a real deployment can tune it without a code change."""

    def test_temperature_and_output_cap_are_sent_from_settings(
        self, captured_request: dict[str, Any]
    ) -> None:
        settings = Settings(ollama_temperature=0.1, ollama_num_predict=64)

        OllamaClient(settings).generate("what is the gross income test?")

        options = captured_request["json"]["options"]
        assert options["temperature"] == 0.1
        assert options["num_predict"] == 64

    def test_keep_alive_is_sent_so_the_model_is_not_reloaded_between_calls(
        self, captured_request: dict[str, Any]
    ) -> None:
        settings = Settings(ollama_keep_alive="3m")

        OllamaClient(settings).generate("what is the gross income test?")

        assert captured_request["json"]["keep_alive"] == "3m"

    def test_request_timeout_comes_from_settings(
        self, captured_request: dict[str, Any]
    ) -> None:
        settings = Settings(ollama_timeout_seconds=17.0)

        OllamaClient(settings).generate("what is the gross income test?")

        assert captured_request["timeout"] == 17.0


class TestGenerationDefaults:
    """The defaults are the ones that ship, so they're worth pinning: a
    grounded policy answer should be reproducible and bounded, not creative
    and open-ended."""

    def test_default_temperature_is_low_enough_for_grounded_answers(self) -> None:
        # Measured live (2026-08-23): at Ollama's own 0.8 default the same
        # question produced 115 vs 294 tokens across two runs, and dropped
        # the citation entirely on one of three real questions -- which
        # costs a whole retry generation, or an abstention.
        assert Settings().ollama_temperature <= 0.3

    def test_output_is_capped_so_one_runaway_answer_cannot_hang_a_request(self) -> None:
        settings = Settings()
        assert settings.ollama_num_predict > 0
        # Generous enough that a normal answer finishes on its own (real
        # answers measured at 47-73 tokens) -- this is a backstop against
        # pathological runaway, not the mechanism that keeps answers short.
        assert settings.ollama_num_predict >= 256
