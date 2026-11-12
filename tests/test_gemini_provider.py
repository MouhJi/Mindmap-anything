import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from knowledge import provider
from knowledge.provider import GeminiProvider, GeminiSettings


class Answer(BaseModel):
    label: str


class ApiError(Exception):
    def __init__(self, code, message=""):
        self.code = code
        self.message = message


def response(text='{"label":"FastAPI"}', *, usage=None, finish_reason="STOP"):
    return SimpleNamespace(text=text, usage_metadata=usage,
                           candidates=[SimpleNamespace(finish_reason=finish_reason)])


@pytest.fixture
def make_provider(monkeypatch):
    def create(generate_content, **overrides):
        calls = []

        async def request(**kwargs):
            calls.append(kwargs)
            return await generate_content()

        async def aclose():
            calls.append("async close")

        client = SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=request), aclose=aclose),
            close=lambda: calls.append("close"),
        )
        monkeypatch.setattr(provider, "_connect", lambda settings: (client, ApiError))
        settings = dict(api_key="unit-key", model="unit-model", max_attempts=1) | overrides
        return GeminiProvider(GeminiSettings(**settings)), calls

    return create


async def complete(adapter):
    return await adapter.generate_structured(
        messages=[{"role": "system", "content": "Use the supplied data."},
                  {"role": "user", "content": "FastAPI"}],
        response_schema=Answer,
    )


def test_configuration_requires_key_and_model(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with pytest.raises(provider.ProviderConfigurationError, match="GEMINI_API_KEY.*GEMINI_MODEL"):
        GeminiSettings.from_env()
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    monkeypatch.setenv("GEMINI_MODEL", "unit-model")
    with pytest.raises(provider.ProviderConfigurationError, match="GEMINI_API_KEY"):
        GeminiSettings.from_env()


@pytest.mark.parametrize(("variable", "value"), [
    ("GEMINI_MODEL", "https://invalid/model"), ("LLM_TEMPERATURE", "3"),
    ("LLM_TIMEOUT_SECONDS", "inf"), ("LLM_MAX_CONCURRENT_REQUESTS", "0"),
    ("LLM_MAX_ATTEMPTS", "6"),
])
def test_configuration_rejects_invalid_values(monkeypatch, variable, value):
    monkeypatch.setenv("GEMINI_API_KEY", "unit-key")
    monkeypatch.setenv("GEMINI_MODEL", "unit-model")
    monkeypatch.setenv(variable, value)
    with pytest.raises(provider.ProviderConfigurationError, match=variable) as info:
        GeminiSettings.from_env()
    assert "unit-key" not in str(info.value)


def test_valid_completion_includes_usage_and_closes_clients(make_provider):
    async def generate():
        return response(usage=SimpleNamespace(prompt_token_count=12, candidates_token_count=4))

    adapter, calls = make_provider(generate)

    async def run():
        async with adapter:
            return await complete(adapter)

    completion = asyncio.run(run())
    assert completion.value == Answer(label="FastAPI")
    assert completion.metrics.success and completion.metrics.attempts == 1
    assert completion.metrics.latency_ms >= 0
    assert (completion.metrics.input_tokens, completion.metrics.output_tokens) == (12, 4)
    assert calls[0]["config"]["response_json_schema"] == Answer.model_json_schema()
    assert calls[0]["config"]["response_mime_type"] == "application/json"
    assert calls[0]["config"]["system_instruction"] == "Use the supplied data."
    assert calls[0]["contents"] == [{"role": "user", "parts": [{"text": "FastAPI"}]}]
    assert calls[1:] == ["async close", "close"]


@pytest.mark.parametrize(("text", "finish", "error_type", "message"), [
    ("", "STOP", provider.ProviderResponseError, "empty"),
    ("{", "STOP", provider.ProviderResponseError, "invalid JSON"),
    ('{"label":"FastAPI","score":NaN}', "STOP", provider.ProviderResponseError, "invalid JSON"),
    ('{"label":12}', "STOP", provider.ProviderSchemaValidationError, "schema"),
    ('{"label":"FastAPI"}', "MAX_TOKENS", provider.ProviderResponseError, "finish"),
])
def test_invalid_responses_are_typed(make_provider, text, finish, error_type, message):
    async def generate():
        return response(text, finish_reason=finish)

    adapter, calls = make_provider(generate, max_attempts=3)
    with pytest.raises(error_type, match=message) as info:
        asyncio.run(complete(adapter))
    assert len(calls) == info.value.metrics.attempts == 1
    assert not info.value.metrics.success and info.value.metrics.input_tokens is None


@pytest.mark.parametrize(("fault", "error_type"), [
    (ApiError(401, "unit-key"), provider.ProviderAuthenticationError),
    (ApiError(400, "API key not valid. unit-key"), provider.ProviderAuthenticationError),
    (ApiError(404), provider.ProviderConfigurationError),
    (ApiError(400, "The input token count exceeds the maximum"),
     provider.ProviderContextWindowError),
    (ApiError(429), provider.ProviderRateLimitError),
    (ApiError(503), provider.ProviderTemporaryError),
    (httpx.ReadTimeout("unit-key"), provider.ProviderTimeoutError),
])
def test_error_propagation_redacts_sdk_details(make_provider, fault, error_type):
    async def generate():
        raise fault

    adapter, _ = make_provider(generate)
    with pytest.raises(error_type) as info:
        asyncio.run(complete(adapter))
    assert "unit-key" not in str(info.value)
    assert info.value.metrics.attempts == 1 and not info.value.metrics.success


def test_timeout_cancels_hanging_request(make_provider):
    async def generate():
        await asyncio.Event().wait()

    adapter, _ = make_provider(generate, timeout_seconds=0.01)
    with pytest.raises(provider.ProviderTimeoutError):
        asyncio.run(complete(adapter))


@pytest.mark.parametrize("recovers", [True, False])
def test_rate_limit_backoff_is_bounded(make_provider, monkeypatch, recovers):
    sleeps = []

    async def pause(seconds):
        sleeps.append(seconds)

    async def generate():
        if recovers and len(sleeps) == 2:
            return response()
        raise ApiError(429)

    monkeypatch.setattr(provider.asyncio, "sleep", pause)
    adapter, calls = make_provider(generate, max_attempts=3)
    if recovers:
        assert asyncio.run(complete(adapter)).metrics.attempts == 3
    else:
        with pytest.raises(provider.ProviderRateLimitError) as info:
            asyncio.run(complete(adapter))
        assert info.value.metrics.attempts == 3
    assert sleeps == [0.5, 1.0] and len(calls) == 3


def test_concurrency_is_bounded(make_provider):
    active = peak = 0

    async def generate():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return response()

    adapter, calls = make_provider(generate, max_concurrent_requests=2)

    async def run():
        await asyncio.gather(*(complete(adapter) for _ in range(5)))

    asyncio.run(run())
    assert peak == 2 and len(calls) == 5


def test_sdk_serializes_extraction_schema_and_system_instruction(monkeypatch):
    genai = pytest.importorskip("google.genai")
    from knowledge.extraction import SYSTEM_PROMPT, StructuredExtractor
    from knowledge.models import SourceChunk

    client_class = genai.Client
    requests = []
    quote = "FastAPI is based on Starlette."
    completion = {
        "entities": [{"name": "FastAPI", "type": "Framework"},
                     {"name": "Starlette", "type": "Library"}],
        "relationships": [{"source": "FastAPI", "target": "Starlette", "relation_type": "BASED_ON",
                           "evidence": quote, "chunk_id": "example"}],
    }

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": json.dumps(completion)}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 17, "candidatesTokenCount": 7},
        })

    def connect(**kwargs):
        kwargs["http_options"]["httpx_async_client"] = httpx.AsyncClient(
            transport=httpx.MockTransport(respond), trust_env=False,
        )
        return client_class(**kwargs)

    monkeypatch.setattr(genai, "Client", connect)

    async def run():
        settings = GeminiSettings(api_key="fake-key", model="unit-model")
        async with GeminiProvider(settings) as adapter:
            extractor = StructuredExtractor(adapter, provider_version=adapter.version)
            source = SourceChunk(project_id="p", document_id="doc", chunk_id="example",
                                 url="https://example.com/docs", text=quote)
            return await extractor.extract_async(source)

    outcome = asyncio.run(run())
    assert [r.evidence for r in outcome.result.relationships] == [quote]
    assert (outcome.metrics.input_tokens, outcome.metrics.output_tokens) == (17, 7)
    request, = requests
    assert request.url.host == "generativelanguage.googleapis.com"
    assert request.headers["x-goog-api-key"] == "fake-key"
    body = json.loads(request.content)
    assert body["systemInstruction"]["parts"] == [{"text": SYSTEM_PROMPT}]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    schema = body["generationConfig"]["responseJsonSchema"]
    assert schema["required"] == ["entities", "relationships"]
    assert all("maxItems" not in items for items in schema["properties"].values())
    assert "BASED_ON" in schema["$defs"]["RelationType"]["enum"]
    relationship = schema["$defs"]["ExtractedRelationship"]
    assert set(relationship["properties"]) == {"source", "target", "relation_type", "evidence",
                                               "chunk_id"}
