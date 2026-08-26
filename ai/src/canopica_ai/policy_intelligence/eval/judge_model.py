"""A `DeepEvalBaseLLM` adapter over OpenRouter (Task 7 plan; design doc
§2.6, revised): the local `llama3.2:3b` judge was measured live
(2026-08-24) to be both too slow (minutes per metric call) and outright
unreliable (a single generation exceeded a 240s timeout and crashed the
run) to serve as a CI-blocking eval judge -- see `run_eval.py`'s own
module docstring for the exact measurement. This is a deliberate,
documented correction to the design doc's original "no OpenRouter key
needed, $0 posture" constraint: that constraint is right for the
*generation* model under test (`canopica_ai.common.llm_client.OllamaClient`,
unchanged, still local), which is what a real user's traffic hits. A judge
never serves user traffic -- it's a bounded, CI-only evaluation step -- so
the same self-hosting requirement doesn't carry over, and a fast, capable
model matters more here than a self-hosted one.

Pinned to a specific model rather than OpenRouter's own `openrouter/free`
auto-router: live-probed (2026-08-24), that router can select *any*
free-tier model that claims to support the request's feature set,
including `nvidia/nemotron-3.5-content-safety:free` -- a safety
classifier, not a general instruct model, which silently ignored a real
prompt and returned "User Safety: safe" instead of the requested JSON.
`nvidia/nemotron-3-ultra-550b-a55b:free` was verified live instead: two
consecutive real calls (a plain chat completion, a `response_format:
json_schema` structured call) both succeeded cleanly, while
`google/gemma-4-31b-it:free` and `z-ai/glm-5.2:free` both hit a real 429
("temporarily rate-limited upstream... shared pool") on the very first
call in the same probe -- a concrete, live reason to prefer this model
over those, not a guess.

**Moved off that model, and off OpenRouter's `:free` tier entirely,
2026-08-26** -- see `config.py`'s `openrouter_judge_model` field for the
real evidence (two full eval runs lost the same night to free-tier
capacity exhaustion), the live price/compatibility comparison across
four paid candidates, and why DeepSeek V3 won on cost with Claude Haiku
4.5 kept as a proven fallback. This class's own retry logic
(`_RETRYABLE_ERROR_CODES`, `_MAX_ATTEMPTS`) stays unchanged and still
applies -- paid routing removes the *free-tier* failure mode
specifically, not the general case for retrying a transient upstream
error.
"""

from __future__ import annotations

import json
import time

import httpx
from deepeval.models.base_model import DeepEvalBaseLLM
from pydantic import BaseModel

from canopica_ai.common.llm_client import OpenRouterNotConfiguredError
from canopica_ai.config import Settings

# Not consulted anywhere -- `Settings.openrouter_judge_model` (config.py)
# is the real, live default; this constant predates that field and was
# already dead code before 2026-08-26's model change touched it. Kept in
# sync rather than deleted, since deleting code this change didn't make
# unused isn't this change's call to make (CLAUDE.md's scoped-changes
# convention) -- flagged here for whoever next has reason to remove it.
DEFAULT_JUDGE_MODEL = "deepseek/deepseek-chat"

_OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"

# Hit for real (2026-08-24): a clean 8-question eval run got through every
# question's retrieval and generation, then died on the judge's very first
# call -- OpenRouter's free-tier Nvidia backend returned a 502 "Service
# temporarily overloaded", nothing wrong with this project's own request.
# A CI-blocking gate has no business flaking on a transient free-tier
# capacity blip, so a genuinely retryable upstream error gets a few short
# attempts before this raises for real. 429/503 are the same class of
# "try again shortly" signal OpenRouter's own docs use elsewhere in this
# codebase's live probes (judge_model module docstring above).
# 404 is here despite reading like "no such model", and that is a reversal
# of this file's own earlier call the same day (2026-08-25). It cost a
# second CI run (`32811993194`) to overturn: the 404 landed after 24m39s,
# on `contextual_recall`, with all eight questions' retrieval and
# generation already done and judge calls already succeeding against this
# very model in that very run. Three live probes then ruled out the
# textbook reading -- the pinned model is in OpenRouter's public model
# list, a plain chat call returns 200, and a call with the exact
# `json_schema` shape DeepEval sends also returns 200. What remains is
# OpenRouter's behaviour for a `:free` variant with no provider endpoint
# free at that instant, which is transient. Retrying is safe *because* the
# raised error now carries OpenRouter's own explanation (below): a model
# that genuinely does not exist fails on the first call and says so,
# instead of costing 25 minutes of finished work.
#
# 3 attempts / 2s base backoff was too short a window for this specific
# failure in practice, not just in theory: the identical 502 "Service
# temporarily overloaded" from Nvidia's free-tier backend killed a run on
# 2026-08-24 *and* 2026-08-26 (the second time after all 12 questions had
# already answered and judged cleanly -- ~50 minutes of real work lost to
# ~6 seconds of total retry window). 5 attempts / 3s base gives ~30s of
# window (3+6+9+12s between attempts) before giving up -- still bounded,
# not a retry-forever loop, but sized to the sustained-overload duration
# actually observed rather than a guess.
_RETRYABLE_ERROR_CODES = frozenset({404, 429, 502, 503})
_MAX_ATTEMPTS = 5
_RETRY_BACKOFF_SECONDS = 3.0
_HTTP_OK = 200


def _parses_as_json_object(content: str) -> bool:
    """Whether DeepEval will be able to load this response.

    Deliberately mirrors the leniency of DeepEval's own `trimAndLoadJson`
    (`deepeval/metrics/utils.py`) -- first `{` to last `}`, then
    `json.loads` -- rather than validating strictly against the requested
    schema. Being *stricter* here than the consumer would reject responses
    DeepEval would happily have accepted, turning a working run into a
    retry storm; the only question worth asking is the one DeepEval is
    about to ask itself.
    """
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end < start:
        return False
    try:
        json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return False
    return True


class OpenRouterJudgeModel(DeepEvalBaseLLM):  # type: ignore[no-untyped-call]
    """Temperature 0: a judge's job is consistent grading, not creative
    variance -- the same reasoning the (since-removed) local-Ollama judge
    used, and DeepEval's own first-party model wrappers default to the
    same for exactly this reason.

    `# type: ignore` on the class line and on `load_model` below: deepeval
    ships without a `py.typed` marker fully honoring strict mode --
    `DeepEvalBaseLLM.__init_subclass__` itself is untyped, and its
    abstract `load_model` is declared to return `DeepEvalBaseLLM` even
    though DeepEval's own real subclasses (e.g. `OllamaModel`) don't
    return one either. Narrow, targeted ignores rather than a blanket
    per-module override, so a real future type error in this file isn't
    silently swallowed along with these two known-noisy ones.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or Settings()
        if not settings.openrouter_api_key:
            raise OpenRouterNotConfiguredError(
                "CANOPICA_OPENROUTER_API_KEY is not set -- required for the eval-suite "
                "judge model (ai/.env locally, the OPENROUTER_API_KEY repo secret in CI)"
            )
        self._api_key = settings.openrouter_api_key
        self._model_name = settings.openrouter_judge_model
        self._timeout_seconds = settings.openrouter_timeout_seconds
        super().__init__(self._model_name)

    def load_model(self) -> str:  # type: ignore[override]
        return self._model_name

    def generate(
        self, prompt: str, schema: type[BaseModel] | None = None, *args: object, **kwargs: object
    ) -> str:
        body: dict[str, object] = {
            "model": self._model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            }
        for attempt in range(_MAX_ATTEMPTS):
            response = httpx.post(
                _OPENROUTER_CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
                timeout=self._timeout_seconds,
            )
            is_last_attempt = attempt == _MAX_ATTEMPTS - 1
            # OpenRouter represents an upstream provider error two different
            # ways, confirmed live on two separate occasions -- a 200 with an
            # `error` key in the body (2026-08-24's 502 "Service temporarily
            # overloaded"), and a genuine non-2xx HTTP status (2026-08-25's
            # real 404). `raise_for_status()` only ever sees the second shape
            # -- the first still returns 200, so it reaches the `"error" not
            # in payload` check below untouched. Both are handled here,
            # against the same `_RETRYABLE_ERROR_CODES`, so neither shape can
            # silently skip the retry this gate exists for.
            if response.status_code != _HTTP_OK:
                if response.status_code not in _RETRYABLE_ERROR_CODES or is_last_attempt:
                    # Wrapped as RuntimeError rather than left as the raw
                    # httpx.HTTPStatusError, so a caller sees one exception
                    # type from this adapter regardless of which of
                    # OpenRouter's two error shapes actually fired -- the
                    # 200-with-error-body branch below already raises
                    # RuntimeError for the same reason.
                    # The body, not just the status line. OpenRouter states
                    # the actual reason only there, and two very different
                    # causes share the same 404 status -- "no such model"
                    # versus "no provider endpoint free right now". Without
                    # it, run `32811993194`'s failure was unattributable
                    # from the CI log and took three live probes to
                    # diagnose after the fact.
                    raise RuntimeError(
                        f"OpenRouter judge call failed: HTTP {response.status_code} "
                        f"{response.reason_phrase}: {response.text}"
                    )
                time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            payload = response.json()
            if "error" not in payload:
                content: str = payload["choices"][0]["message"]["content"]
                # A *third* shape of "the upstream provider returned
                # garbage", after the 200-with-error-body and the real
                # non-2xx above -- and the one that reads least like an
                # error, because everything about the HTTP exchange
                # succeeded. Hit for real in run `32935635062`: all 8
                # questions answered, then a judge call for
                # `contextual_precision` came back 200 with a body that
                # was not JSON, and DeepEval's `trimAndLoadJson` raised
                # `ValueError: Evaluation LLM outputted an invalid JSON`
                # -- discarding 19 minutes of completed work over one bad
                # response out of roughly a dozen.
                #
                # Retrying is the right response for the same reason it is
                # for the 404 documented above, not merely by analogy to
                # it: `response_format: json_schema` with `strict: true` is
                # already being sent, so a non-JSON body means the
                # free-tier provider that served *this* attempt ignored it.
                # OpenRouter routes `:free` requests to whichever provider
                # endpoint is available at that instant, so the next
                # attempt is a genuinely different roll rather than a
                # deterministic repeat of the same one -- which is also why
                # `temperature: 0` does not make this pointless.
                if schema is None or _parses_as_json_object(content):
                    return content
                if is_last_attempt:
                    # The body verbatim: which provider ignored the schema,
                    # and whether it returned prose, a refusal, or truncated
                    # JSON, is the whole diagnosis, and is not recoverable
                    # from the CI log otherwise.
                    raise RuntimeError(
                        f"OpenRouter judge returned no loadable JSON for schema "
                        f"{schema.__name__} after {_MAX_ATTEMPTS} attempts: {content!r}"
                    )
                time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            error = payload["error"]
            if error.get("code") not in _RETRYABLE_ERROR_CODES or is_last_attempt:
                raise RuntimeError(f"OpenRouter judge call failed: {error}")
            time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
        raise AssertionError("unreachable: the loop above always returns or raises")

    async def a_generate(
        self, prompt: str, schema: type[BaseModel] | None = None, *args: object, **kwargs: object
    ) -> str:
        # This class only implements the synchronous path (httpx.post, not
        # an async client) -- every metric in run_eval.py is constructed
        # with async_mode=False for the same reason, matching this
        # class's real blocking behavior instead of claiming a
        # concurrency it can't provide.
        return self.generate(prompt, schema=schema)

    def get_model_name(self) -> str:
        return self._model_name
