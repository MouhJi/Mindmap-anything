"""Opt-in test that sends one small structured request to the Gemini API."""

import asyncio
import os
import pytest

from knowledge.extraction import CandidateExtraction, _generation_schema
from knowledge.provider import GeminiProvider, GeminiSettings


def test_live_gemini_structured_completion():
    if os.getenv("GRAPH_TEST_GEMINI") != "1":
        pytest.skip("Set GRAPH_TEST_GEMINI=1 to make a real Gemini API request")
    if not all(os.getenv(name, "").strip() for name in ("GEMINI_API_KEY", "GEMINI_MODEL")):
        pytest.skip("GEMINI_API_KEY and GEMINI_MODEL are required for the live smoke test")

    async def run():
        settings = GeminiSettings.from_env().model_copy(update={"max_attempts": 1})
        async with GeminiProvider(settings) as adapter:
            result = await adapter.generate_structured(
                messages=[{"role": "user", "content": "Return empty entities and relationships arrays."}],
                response_schema=CandidateExtraction,
                generation_schema=_generation_schema(),
            )
        assert result.value.entities == result.value.relationships == []
        assert result.metrics.success and result.metrics.attempts == 1
        assert result.metrics.model == settings.model and result.metrics.latency_ms > 0
        print(result.metrics.model_dump_json())

    asyncio.run(run())
