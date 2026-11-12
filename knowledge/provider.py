"""Structured completion contract and the optional Gemini Developer API adapter."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Generic, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from .models import stable_id

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class ProviderMetrics(BaseModel):
    provider: str
    model: str
    latency_ms: float
    attempts: int
    success: bool
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class StructuredCompletion(Generic[T]):
    value: T
    metrics: ProviderMetrics


class StructuredProvider(Protocol):
    model: str
    version: str

    async def generate_structured(
        self, *, messages: list[dict[str, str]], response_schema: type[T],
        generation_schema: dict | None = None,
    ) -> StructuredCompletion[T]: ...


class ProviderError(RuntimeError):
    metrics: ProviderMetrics | None = None


class ProviderConfigurationError(ProviderError):
    pass


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderTemporaryError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass


class ProviderContextWindowError(ProviderResponseError):
    pass


class ProviderSchemaValidationError(ProviderResponseError):
    pass


class GeminiSettings(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, allow_inf_nan=False)

    api_key: SecretStr = Field(min_length=1)
    model: str = Field(pattern=r"^(?:models/)?[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    temperature: float = Field(default=0.0, ge=0, le=2)
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_concurrent_requests: int = Field(default=2, ge=1)
    max_attempts: int = Field(default=3, ge=1, le=5)

    @field_validator("api_key")
    @classmethod
    def nonblank_key(cls, key: SecretStr) -> SecretStr:
        if not key.get_secret_value().strip():
            raise ValueError("API key must be nonblank")
        return key

    @classmethod
    def from_env(cls) -> GeminiSettings:
        names = {
            "api_key": "GEMINI_API_KEY",
            "model": "GEMINI_MODEL",
            "temperature": "LLM_TEMPERATURE",
            "timeout_seconds": "LLM_TIMEOUT_SECONDS",
            "max_concurrent_requests": "LLM_MAX_CONCURRENT_REQUESTS",
            "max_attempts": "LLM_MAX_ATTEMPTS",
        }
        values = {field: os.environ[var].strip() for field, var in names.items()
                  if var in os.environ}
        try:
            return cls.model_validate(values)
        except ValidationError as error:
            fields = ", ".join(names[item["loc"][0]] for item in error.errors())
            raise ProviderConfigurationError(f"Missing or invalid settings: {fields}") from None


def _connect(settings: GeminiSettings):
    try:
        from google import genai
        from google.genai.errors import APIError
    except ImportError:
        raise ProviderConfigurationError(
            'Install the Gemini SDK with pip install ".[llm]"',
        ) from None
    # Let the adapter own retry timing and attempt counts.
    client = genai.Client(
        api_key=settings.api_key.get_secret_value(), vertexai=False,
        http_options={"retry_options": {"attempts": 1}},
    )
    return client, APIError


def _api_error(error) -> ProviderError:
    code = error.code
    message = (error.message or "").casefold()
    invalid_key = code == 400 and re.search(r"api.key.{0,40}(?:not valid|invalid|expired)", message)
    if code in (401, 403) or invalid_key:
        return ProviderAuthenticationError("Gemini rejected the API credentials or permissions")
    if code == 429:
        return ProviderRateLimitError("Gemini rate or quota limit reached")
    if code in (408, 504):
        return ProviderTimeoutError("Gemini request timed out")
    if code == 404:
        return ProviderConfigurationError("Configured Gemini model is unavailable for this request")
    if code in (400, 413) and (
        code == 413 or re.search(r"input token (?:count|limit)|context (?:length|window)", message)
    ):
        return ProviderContextWindowError("Gemini rejected the request size or input context")
    if code is not None and 500 <= code < 600:
        return ProviderTemporaryError("Gemini service temporarily failed")
    return ProviderResponseError(f"Gemini rejected the structured request (HTTP {code})")


def _finite_number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


class GeminiProvider:
    """Use one adapter per async session. Configuration contains no model default."""

    def __init__(self, settings: GeminiSettings):
        self.settings = settings
        self.model = settings.model
        self.version = stable_id("gemini", self.model, str(settings.temperature))
        self._client, self._api_error_type = _connect(settings)
        self._slots = asyncio.Semaphore(settings.max_concurrent_requests)

    async def __aenter__(self) -> GeminiProvider:
        return self

    async def __aexit__(self, *exc) -> None:
        try:
            await self._client.aio.aclose()
        finally:
            self._client.close()

    async def generate_structured(
        self, *, messages: list[dict[str, str]], response_schema: type[T],
        generation_schema: dict | None = None,
    ) -> StructuredCompletion[T]:
        system_instruction = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        config = {
            "system_instruction": system_instruction,
            "temperature": self.settings.temperature,
            "response_mime_type": "application/json",
            "response_json_schema": (response_schema.model_json_schema()
                                     if generation_schema is None else generation_schema),
        }
        contents = [{"role": m["role"], "parts": [{"text": m["content"]}]}
                    for m in messages if m["role"] != "system"]
        started = perf_counter()
        for attempt in range(1, self.settings.max_attempts + 1):
            usage = None
            try:
                async with self._slots, asyncio.timeout(self.settings.timeout_seconds):
                    response = await self._client.aio.models.generate_content(
                        model=self.model, contents=contents, config=config,
                    )
                usage = response.usage_metadata
                response_text = response.text
                if not response_text or not response_text.strip():
                    raise ProviderResponseError("Gemini returned an empty structured response")
                finish = response.candidates[0].finish_reason if response.candidates else None
                if finish not in (None, "STOP"):
                    raise ProviderResponseError("Gemini did not finish the structured response")
                try:
                    # Pydantic's JSON parser permits non-finite numbers. Preserve only
                    # candidates that can also be represented in ordinary JSONL artifacts.
                    json.loads(response_text, parse_constant=_finite_number,
                               parse_float=_finite_number)
                except (ValueError, RecursionError):
                    raise ProviderResponseError("Gemini returned invalid JSON") from None
                value = response_schema.model_validate_json(response_text)
            except self._api_error_type as error:
                failure = _api_error(error)
            except (TimeoutError, httpx.TimeoutException):
                failure = ProviderTimeoutError("Gemini request timed out")
            except httpx.TransportError:
                failure = ProviderTemporaryError("Could not communicate with Gemini")
            except ValidationError as error:
                if error.errors()[0]["type"] == "json_invalid":
                    failure = ProviderResponseError("Gemini returned invalid JSON")
                else:
                    failure = ProviderSchemaValidationError(
                        "Gemini response failed schema validation",
                    )
            except ProviderResponseError as error:
                failure = error
            except ValueError:
                failure = ProviderResponseError("Gemini SDK could not process the request")
            else:
                failure = None

            transient = isinstance(failure, (
                ProviderRateLimitError, ProviderTimeoutError, ProviderTemporaryError,
            ))
            if transient and attempt < self.settings.max_attempts:
                await asyncio.sleep(0.5 * 2 ** (attempt - 1))
                continue
            metrics = ProviderMetrics(
                provider="gemini", model=self.model, latency_ms=(perf_counter() - started) * 1000,
                attempts=attempt, success=failure is None,
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=getattr(usage, "candidates_token_count", None),
            )
            logger.info("Gemini completion %s", metrics.model_dump_json())
            if failure is not None:
                failure.metrics = metrics
                raise failure from None
            return StructuredCompletion(value, metrics)
        raise AssertionError("Gemini attempt loop exhausted without an outcome")
