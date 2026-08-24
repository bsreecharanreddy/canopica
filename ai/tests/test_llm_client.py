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
from pydantic import BaseModel

from canopica_ai.common.llm_client import OllamaClient, PromptTooLongError
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


class TestStructuredGeneration:
    """Task 3's rule-authoring copilot needs the model to return a *shape*,
    not prose. Ollama constrains decoding to a JSON schema natively
    (`format`), which is strictly stronger than asking politely in the
    prompt and validating afterwards -- these assert the schema actually
    reaches the API, since a silently-dropped `format` would degrade to
    prompt-and-hope without any visible failure."""

    class _Proposal(BaseModel):
        name: str
        new_value: float

    def test_the_pydantic_schema_is_sent_as_ollamas_format_constraint(
        self, captured_request: dict[str, Any]
    ) -> None:
        OllamaClient(Settings()).generate_structured("propose changes", self._Proposal)

        assert captured_request["json"]["format"] == self._Proposal.model_json_schema()

    def test_structured_generation_reuses_the_same_bounded_options_as_prose(
        self, captured_request: dict[str, Any]
    ) -> None:
        # Asserted against prose's own request rather than a hardcoded dict, so
        # the two cannot drift: a knob added to one path and forgotten on the
        # other fails here instead of quietly applying to only half the system.
        client = OllamaClient(Settings(ollama_temperature=0.1, ollama_num_predict=64))

        client.generate("what is the gross income test?")
        prose = dict(captured_request["json"])
        client.generate_structured("propose changes", self._Proposal)
        structured = captured_request["json"]

        assert structured["options"] == prose["options"]
        assert structured["keep_alive"] == prose["keep_alive"]

    def test_prose_generation_sends_no_format_constraint(
        self, captured_request: dict[str, Any]
    ) -> None:
        OllamaClient(Settings()).generate("what is the gross income test?")

        assert "format" not in captured_request["json"]


class TestPromptFitsTheContextWindow:
    """Measured live (2026-08-23) against llama3.2:3b, and the reason this
    guard exists at all: the same 12,186-character prompt reported
    `prompt_eval_count` of **1,026 at num_ctx=2048** and **3,105 at 4096**.
    Ollama silently discarded two thirds of it and still answered 200 OK.

    Nothing downstream could have caught that. The answer comes back
    fluent, and for the rule-authoring copilot the parameter list is at the
    *front* of the prompt -- the part truncated first -- so the model would
    have been diffing against a list it never saw, and proposing figures
    that look entirely plausible."""

    def test_the_context_size_is_sent_rather_than_left_to_the_model_default(
        self, captured_request: dict[str, Any]
    ) -> None:
        settings = Settings(ollama_num_ctx=1234)

        OllamaClient(settings).generate("what is the gross income test?")

        assert captured_request["json"]["options"]["num_ctx"] == 1234

    def test_a_prompt_that_cannot_fit_raises_instead_of_being_truncated(
        self, captured_request: dict[str, Any]
    ) -> None:
        settings = Settings(ollama_num_ctx=2048, ollama_num_predict=512)
        # Comfortably past the budget at any plausible tokens-per-character.
        oversized = "policy text. " * 4000

        with pytest.raises(PromptTooLongError, match="would be silently truncated"):
            OllamaClient(settings).generate(oversized)

        # Refused before the request, not after paying for a generation whose
        # output is worthless anyway.
        assert captured_request == {}

    def test_a_realistic_prompt_is_not_refused_by_the_guard(
        self, captured_request: dict[str, Any]
    ) -> None:
        # The measured worst case this system actually produces: the full
        # 39-parameter set plus a 6,000-character excerpt, ~10,200 characters.
        # If a routine prompt trips the guard, the guard is wrong.
        OllamaClient(Settings()).generate("x" * 10_200)

        assert captured_request["json"]["prompt"].startswith("x")


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
