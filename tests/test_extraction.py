import asyncio
import json
from pathlib import Path

import pytest

from knowledge.chunking import SectionChunk
from knowledge.extraction import SYSTEM_PROMPT, StructuredExtractor
from knowledge.extraction_batch import _read_chunks, run_batch
from knowledge.provider import ProviderMetrics, ProviderTimeoutError, StructuredCompletion


class StubProvider:
    model = "test-model"
    version = "test-model/config-v1"

    def __init__(self, response):
        self.response = response
        self.calls = []

    async def generate_structured(self, *, messages, response_schema, generation_schema):
        self.calls.append((messages, generation_schema))
        context = json.loads(messages[1]["content"])
        response = self.response(context) if callable(self.response) else self.response
        if isinstance(response, Exception):
            raise response
        return StructuredCompletion(response_schema.model_validate(response), metrics())


def metrics(success=True):
    return ProviderMetrics(provider="stub", model="test-model", latency_ms=3, attempts=1,
                           success=success, input_tokens=11, output_tokens=5 if success else None)


def chunk(text, chunk_id="chunk-1", **changes):
    fields = dict(project_id="p", chunk_id=chunk_id, document_id="d",
                  url="https://example.com/docs", text=text, topic="Technical Details",
                  document_title="Framework Documentation", section_title="Technical Details",
                  heading_path=["Framework Documentation", "Technical Details"], start_char=0,
                  end_char=len(text), token_count=len(text))
    return SectionChunk(**(fields | changes))


def entity(name, **changes):
    return {"name": name, "type": "Library"} | changes


def edge(quote, **changes):
    return {"source": "FastAPI", "target": "Starlette", "relation_type": "BASED_ON",
            "chunk_id": "chunk-1", "evidence": quote} | changes


def response(*edges, entities=None):
    if entities is None:
        entities = [entity("FastAPI", type="Framework"), entity("Starlette")]
    return {"entities": entities, "relationships": list(edges)}


def extract(provider, source):
    extractor = StructuredExtractor(provider, provider_version=provider.version)
    return asyncio.run(extractor.extract_async(source))


def test_explicit_relationship_with_verbatim_evidence_and_prompt_context():
    text = "FastAPI is based on Starlette."
    source = chunk(text)
    provider = StubProvider(response(edge(text)))
    outcome = extract(provider, source)
    assert [e.name for e in outcome.result.entities] == ["FastAPI", "Starlette"]
    assert len(outcome.result.relationships) == 1
    relation = outcome.result.relationships[0]
    assert (relation.source, relation.relation_type, relation.target) == (
        "FastAPI", "BASED_ON", "Starlette",
    )
    assert relation.evidence == text and relation.chunk_id == source.chunk_id
    check = outcome.relationship_checks[0]
    assert check.schema_valid and check.evidence_text_matched
    assert check.semantically_supported and check.accepted
    messages, schema = provider.calls[0]
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1]["role"] == "user"
    context = json.loads(messages[1]["content"])
    assert context["source_text"] == text and context["document_title"] == source.document_title
    assert context["heading_path"] == source.heading_path and context["source_url"] == source.url
    assert schema["required"] == ["entities", "relationships"]


@pytest.mark.parametrize(("text", "candidate", "entities", "reason"), [
    pytest.param("FastAPI is a Python framework.\nStarlette is an ASGI toolkit.",
                 edge("FastAPI is a Python framework.\nStarlette is an ASGI toolkit."), None,
                 "predicate_not_deterministically_supported", id="unconnected-statements"),
    pytest.param("Framework A does not depend on Library B.",
                 edge("Framework A does not depend on Library B.", source="Framework A",
                      target="Library B", relation_type="DEPENDS_ON"),
                 [entity("Framework A"), entity("Library B")],
                 "negated_or_contradictory_evidence", id="negation"),
    pytest.param("FastAPI, Django and Flask are mentioned in this tutorial.",
                 edge("FastAPI, Django and Flask are mentioned in this tutorial.",
                      target="Django", relation_type="DEPENDS_ON"),
                 [entity("FastAPI"), entity("Django"), entity("Flask")],
                 "predicate_not_deterministically_supported", id="co-occurrence"),
    pytest.param("Django is a Python framework. The `sqlparse` package formats SQL.",
                 edge("Django is a Python framework. The `sqlparse` package formats SQL.",
                      source="Django", target="sqlparse", relation_type="DEPENDS_ON"),
                 [entity("Django"), entity("sqlparse")],
                 "predicate_not_deterministically_supported", id="external-knowledge-trap"),
    pytest.param("FastAPI is based on Starlette.",
                 edge("FastAPI is based on Starlette.", source="Starlette", target="FastAPI"), None,
                 "predicate_not_deterministically_supported", id="reversed-direction"),
    pytest.param("FastAPI might use Starlette.",
                 edge("FastAPI might use Starlette.", relation_type="USES"), None,
                 "speculative_or_conditional_evidence", id="hypothetical"),
    pytest.param("If FastAPI uses Starlette.",
                 edge("FastAPI uses Starlette.", relation_type="USES"),
                 None, "evidence_not_complete_direct_assertion", id="cropped-conditional"),
    pytest.param("FastAPI mentions Django uses Starlette.",
                 edge("FastAPI mentions Django uses Starlette.", relation_type="USES"), None,
                 "predicate_not_deterministically_supported", id="wrong-subject"),
    pytest.param("```text\nFastAPI is based on Starlette.\n```",
                 edge("FastAPI is based on Starlette."),
                 None, "evidence_not_complete_direct_assertion", id="code-as-evidence"),
    pytest.param("FastAPI is based on Starlette.\n\nFastAPI is not based on Starlette.",
                 edge("FastAPI is based on Starlette."), None, "contradictory_source_context",
                 id="contradictory-context"),
])
def test_no_unsupported_facts(text, candidate, entities, reason):
    outcome = extract(StubProvider(response(candidate, entities=entities)), chunk(text))
    assert outcome.result.relationships == []
    check = outcome.relationship_checks[0]
    assert check.schema_valid and check.evidence_text_matched
    assert not check.semantically_supported and not check.accepted
    assert reason in check.reasons


@pytest.mark.parametrize(("text", "changes", "reason"), [
    ("Next\nPrevious\nBack to top", {}, "nontechnical_navigation"),
    ("# Heading only\n\n## Another heading", {}, "heading_only"),
    ("FastAPI is based on Starlette.", {"extraction_eligible": False,
                                      "eligibility_reasons": ["oversized"]}, "oversized"),
])
def test_skipped_chunks_return_empty_and_make_no_requests(text, changes, reason):
    provider = StubProvider(response(edge(text)))
    outcome = extract(provider, chunk(text, **changes))
    assert not outcome.result.entities and not outcome.result.relationships
    assert outcome.skip_reasons == [reason]
    assert not provider.calls and outcome.metrics is None


def test_empty_provider_result_is_a_success():
    provider = StubProvider(response(entities=[]))
    outcome = extract(provider, chunk("This is documentation without graph concepts."))
    assert outcome.result.entities == outcome.result.relationships == []
    assert outcome.metrics.success and len(provider.calls) == 1


def test_rejected_candidates_are_retained_without_discarding_valid_rows():
    text = "FastAPI is based on Starlette."
    no_quote = edge(text)
    del no_quote["evidence"]
    candidates = [no_quote, edge(""), edge("FastAPI is based on  Starlette."),
                  edge(text, target="Django"), edge(text, relation_type="RELATED_TO"),
                  edge(text, chunk_id="another"), "not an object", edge(text)]
    outcome = extract(StubProvider(response(*candidates)), chunk(text))
    assert [c.candidate for c in outcome.relationship_checks] == candidates
    assert len(outcome.result.relationships) == 1
    checks = outcome.relationship_checks
    for check, reason in zip(checks, ["empty_evidence", "empty_evidence", "evidence_not_in_chunk",
                                      "unknown_or_ambiguous_entity", "invalid_relation_type",
                                      "missing_chunk", "malformed_output", "trusted"], strict=True):
        assert reason in check.reasons
    assert not checks[0].schema_valid and not checks[2].evidence_text_matched
    assert checks[4].evidence_text_matched and not checks[4].schema_valid


def test_entities_are_grounded_and_duplicate_names_are_handled_conservatively():
    text = "FastAPI is based on Starlette."
    entities = [entity("FastAPI", type="Framework", description="Invented", aliases=["Django"]),
                entity("fastapi", type="Framework"), entity("Starlette"),
                entity("Pydantic", aliases=["Starlette"]), entity("Starlette", type="Protocol"),
                entity("  ")]
    outcome = extract(StubProvider(response(edge(text), entities=entities)), chunk(text))
    assert outcome.raw_entities == 6
    assert [e.model_dump() for e in outcome.result.entities] == [
        {"name": "FastAPI", "type": "Framework", "description": None, "aliases": []},
    ]
    assert not outcome.result.relationships
    assert "unknown_or_ambiguous_entity" in outcome.relationship_checks[0].reasons


def test_schema_and_text_match_do_not_override_graph_policy():
    text = "FastAPI is based on Starlette."
    outcome = extract(StubProvider(response(edge(text, confidence=0.5))), chunk(text))
    check = outcome.relationship_checks[0]
    assert check.schema_valid and check.evidence_text_matched and check.semantically_supported
    assert not check.accepted and "below_confidence_threshold" in check.reasons


def test_provider_error_propagates_as_a_typed_error():
    provider = StubProvider(ProviderTimeoutError("timeout"))
    with pytest.raises(ProviderTimeoutError):
        extract(provider, chunk("FastAPI is based on Starlette."))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_batch_audit_resume_and_context_invalidation(tmp_path):
    text = "FastAPI is based on Starlette."
    source = chunk(text)
    failing = chunk("Starlette is an ASGI toolkit.", "timeout")
    skipped = chunk("## Heading only", "skip")
    rows = [source, skipped, failing, source]
    path, output = tmp_path / "chunks.jsonl", tmp_path / "output"

    def write_input():
        path.write_text("\n".join([*(c.model_dump_json() for c in rows), "{broken json"]),
                        encoding="utf-8")

    write_input()
    failure = ProviderTimeoutError("untrusted provider details")
    failure.metrics = metrics(False)
    recovered = False

    def provide(context):
        if context["chunk_id"] == "timeout":
            return response(entities=[]) if recovered else failure
        return response(edge(text), edge("not a real quote"))

    provider = StubProvider(provide)

    def run():
        return asyncio.run(run_batch(path, output, provider=provider, batch_size=1, concurrency=1))

    stats = run()
    assert len(provider.calls) == 2
    assert stats["processed_chunks"] == stats["eligible_chunks"] == 2
    assert stats["successful_chunks"] == stats["failed_chunks"] == stats["skipped_chunks"] == 1
    assert stats["invalid_input_rows"] == 2
    assert stats["accepted_relationships"] == stats["rejected_relationships"] == 1
    assert stats["evidence_match_rate"] == 0.5
    assert stats["provider_requests"] == 2 and stats["input_tokens"] == 22
    assert stats["output_tokens"] == 5
    accepted, = read_rows(output / "extracted_relationships.jsonl")
    assert accepted["evidence"] == text and accepted["chunk_id"] == source.chunk_id
    assert accepted["source_url"] == source.url and accepted["document_id"] == source.document_id
    assert accepted["semantically_supported"] and accepted["model"] == provider.model
    rejected, = read_rows(output / "rejected_relationships.jsonl")
    assert rejected["candidate"]["evidence"] == "not a real quote"
    assert rejected["reasons"] == ["evidence_not_in_chunk"]
    failures = read_rows(output / "extraction_failures.jsonl")
    assert failures[0]["error_type"] == "ProviderTimeoutError"
    assert [f["reason"] for f in failures[1:]] == ["duplicate_chunk_id", "malformed_chunk"]
    assert "untrusted provider details" not in json.dumps(failures)

    recovered = True
    assert run()["cached_chunks"] == 1
    assert len(provider.calls) == 3
    stats = run()
    assert stats["cached_chunks"] == 2 and stats["provider_requests"] == 0
    assert stats["input_tokens"] is None and stats["output_tokens"] is None
    assert len(read_rows(output / "extracted_relationships.jsonl")) == 1
    rows[0] = source.model_copy(update={"heading_path": ["Changed context"]})
    write_input()
    assert run()["cached_chunks"] == 1
    assert len(provider.calls) == 4
    provider.version = "test-model/config-v2"
    assert run()["cached_chunks"] == 0
    assert len(provider.calls) == 6


def test_batch_limit_and_selected_ids(tmp_path):
    text = "FastAPI is based on Starlette."
    chunks = [chunk(text, chunk_id) for chunk_id in ("first", "second", "third")]
    path = tmp_path / "chunks.jsonl"
    path.write_text("\n".join(c.model_dump_json() for c in chunks), encoding="utf-8")
    provider = StubProvider(response(entities=[]))
    stats = asyncio.run(run_batch(path, tmp_path / "limit", provider=provider, limit=1))
    assert stats["eligible_chunks"] == 3 and stats["processed_chunks"] == 1
    stats = asyncio.run(run_batch(path, tmp_path / "ids", provider=provider, chunk_ids=["third"]))
    assert stats["processed_chunks"] == 1
    requested = [json.loads(call[0][1]["content"])["chunk_id"] for call in provider.calls]
    assert requested == ["first", "third"]


def test_saved_fastapi_export_uses_the_existing_section_schema():
    dataset = (Path(__file__).resolve().parents[1] / "evaluation" / "real_world" /
               "chunking_results" / "chunks.jsonl")
    chunks, failures = _read_chunks(dataset)
    assert not failures and chunks
    _, dependencies = next((line, c) for line, c in chunks
                           if c.url == "https://fastapi.tiangolo.com/" and
                           c.section_title == "Dependencies")
    assert dependencies.extraction_eligible and dependencies.document_title
    quote = "FastAPI depends on Pydantic and Starlette."
    names = ("Pydantic", "Starlette")
    candidates = [edge(quote, target=name, relation_type="DEPENDS_ON",
                       chunk_id=dependencies.chunk_id) for name in names]
    entities = [entity(name) for name in ("FastAPI", *names)]
    outcome = extract(StubProvider(response(*candidates, entities=entities)), dependencies)
    assert [(r.target, r.evidence) for r in outcome.result.relationships] == [
        (name, quote) for name in names
    ]
