"""Offline normalization, ingestion, quality, expansion and API regressions."""

import json
from copy import deepcopy
from urllib.parse import urlencode

import pytest
from pydantic import ValidationError

from knowledge.api import GraphAPI
from knowledge.expansion import ExpansionService, InvalidCursor, NodeNotFound, StaleCursor
from knowledge.extraction import ExtractionError, StructuredExtractor
from knowledge.ingestion import KnowledgePipeline
from knowledge.models import (
    CanonicalEntity, EntityType, ExtractedEntity, ExtractedRelationship, ExtractionResult,
    GraphPolicy, SourceChunk, name_key,
)
from knowledge.normalization import EntityNormalizer
from knowledge.repository import InMemoryRepository


def entity(name, kind="Framework", **kwargs):
    return ExtractedEntity(name=name, type=kind, **kwargs)


def chunk(text, identifier="chunk-1", project="project-a", topic="FastAPI"):
    return SourceChunk(project_id=project, chunk_id=identifier, document_id="doc-1",
                       url="https://docs.example/guide", text=text, topic=topic)


def relation(source="FastAPI", target="Starlette", kind="BASED_ON", text=None, **kwargs):
    return ExtractedRelationship(
        source=source, target=target, relation_type=kind,
        evidence="FastAPI is based on Starlette." if text is None else text,
        chunk_id=kwargs.pop("chunk_id", "chunk-1"), **kwargs,
    )


def extracted(relationships=None, entities=None):
    return ExtractionResult(entities=entities or [entity("FastAPI"), entity("Starlette")],
                            relationships=relationships if relationships is not None else [relation()])


def center_id(store, name="FastAPI", project="project-a", kind=EntityType.FRAMEWORK):
    return store.find_entities(project, kind, [name_key(name)])[0].entity_id


def populate(count=8):
    store = InMemoryRepository()
    pipeline = KnowledgePipeline(store)
    for index in range(count):
        name = "Library" + str(index)
        text = f"FastAPI uses {name}."
        pipeline.ingest_chunk(chunk(text, str(index)), extracted(
            [relation(target=name, kind="USES", text=text, chunk_id=str(index),
                      importance=.80 - index * .02)],
            [entity("FastAPI"), entity(name, "Library")],
        ))
    return store, pipeline


def test_normalization_aliases_types_context_and_persistent_ids():
    store = InMemoryRepository()
    normalizer = EntityNormalizer(store)
    result, _ = normalizer.normalize("one", [
        entity("FastAPI", aliases=["Fast API", "FastAPI Framework"],
               description="Python asynchronous web framework"),
        entity("fastapi", description="Python asynchronous web framework"),
        entity("Fast API", description="Python asynchronous web framework"),
        entity("FastAPI Framework"),
        entity("React"), entity("React Native"),
        entity("Python", "Language"), entity("Python asyncio", "Library"),
        entity("React", "Library"),
    ])
    assert len({result[name_key(name)].entity_id for name in (
        "FastAPI", "fastapi", "Fast API", "FastAPI Framework",
    )}) == 1
    assert result["react native"].entity_id != center_id(store, "React", "one")
    assert result["python"].entity_id != result["python asyncio"].entity_id
    assert "react" not in result  # Ambiguous type in extraction cannot choose an endpoint.
    first = center_id(store, "FastAPI", "one")
    assert normalizer.normalize("one", [entity("fastapi")])[0]["fastapi"].entity_id == first
    assert normalizer.normalize("two", [entity("FastAPI")])[0]["fastapi"].entity_id != first
    other = InMemoryRepository()
    assert EntityNormalizer(other).normalize("one", [entity("FastAPI")])[0]["fastapi"].entity_id == first


def test_whitespace_name_merge_requires_context_and_ambiguous_alias_stays_separate():
    store = InMemoryRepository()
    normalizer = EntityNormalizer(store)
    normalizer.normalize("p", [entity("FastAPI", description="Python asynchronous web framework")])
    separate, _ = normalizer.normalize("p", [entity("Fast API")])
    assert separate["fast api"].entity_id != center_id(store, "FastAPI", "p")
    store2 = InMemoryRepository()
    normalizer2 = EntityNormalizer(store2)
    normalizer2.normalize("p", [entity("FastAPI", description="Python asynchronous web framework")])
    merged, _ = normalizer2.normalize("p", [entity("Fast API", description="Python asynchronous web framework")])
    assert merged["fast api"].entity_id == center_id(store2, "FastAPI", "p")
    normalizer2.normalize("p", [entity("Alpha", aliases=["Shared"]), entity("Beta", aliases=["Shared"])])
    result, notes = normalizer2.normalize("p", [entity("Shared")])
    assert any("ambiguous_alias" in note for note in notes)


def test_technical_punctuation_and_qualifiers_are_preserved():
    result, _ = EntityNormalizer(InMemoryRepository()).normalize("p", [
        entity("C++", "Language"), entity("C#", "Language"), entity("C", "Language"),
        entity(".NET"), entity("NET"), entity("React"), entity("React Native"),
    ])
    assert len({value.entity_id for value in result.values()}) == 7


def test_deduplication_accumulates_provenance_and_respects_direction():
    store = InMemoryRepository()
    pipeline = KnowledgePipeline(store)
    report = pipeline.ingest_chunk(chunk("FastAPI is based on Starlette."), extracted())
    assert report.accepted_relationships == 1
    assert pipeline.ingest_chunk(chunk("FastAPI is based on Starlette."), extracted()).skipped_chunks == 1
    quote = "Starlette is the foundation of FastAPI."
    pipeline.ingest_chunk(chunk(quote, "chunk-2"), extracted([
        relation(text=quote, chunk_id="chunk-2"), relation(text=quote, chunk_id="chunk-2"),
    ]))
    assert len(store.relationships) == 1
    edge = next(iter(store.relationships.values()))
    assert edge.evidence_count == 2
    assert len(store.evidence) == 2
    assert {ev.chunk_id for ev in store.evidence.values()} == {"chunk-1", "chunk-2"}
    for ev in store.evidence.values():
        assert ev.url == "https://docs.example/guide" and ev.document_id == "doc-1"
    reverse = "Starlette is based on FastAPI."
    pipeline.ingest_chunk(chunk(reverse, "chunk-3"), extracted([
        relation("Starlette", "FastAPI", text=reverse, chunk_id="chunk-3"),
    ]))
    assert len(store.relationships) == 2
    assert len({(edge.source_id, edge.target_id) for edge in store.relationships.values()}) == 2


def test_evidence_whitespace_duplicates_do_not_inflate_support():
    store = InMemoryRepository()
    report = KnowledgePipeline(store).ingest_chunk(
        chunk("FastAPI is based on Starlette."), extracted([
            relation(), relation(text="FastAPI  is based on\nStarlette."),
        ]),
    )
    assert report.accepted_relationships == 2
    assert len(store.relationships) == len(store.evidence) == 1
    assert next(iter(store.relationships.values())).evidence_count == 1


@pytest.mark.parametrize(("quote", "kind", "source_text", "expected_reason"), [
    ("", "BASED_ON", "FastAPI is based on Starlette.", "empty_evidence"),
    ("Invented evidence", "BASED_ON", "FastAPI is based on Starlette.", "evidence_not_in_chunk"),
    ("FastAPI and Starlette are tools.", "BASED_ON", None, "predicate_not_deterministically_supported"),
    ("Starlette uses FastAPI.", "USES", None, "predicate_not_deterministically_supported"),
    ("FastAPI does not use Starlette.", "USES", None, "negated_or_contradictory_evidence"),
    ("FastAPI might use Starlette.", "USES", None, "speculative_or_conditional_evidence"),
    ("FastAPI can use Starlette.", "USES", None, "speculative_or_conditional_evidence"),
    ("If FastAPI uses Starlette, it is fast.", "USES", None, "speculative_or_conditional_evidence"),
    ("Does FastAPI use Starlette?", "USES", None, "interrogative_evidence"),
])
def test_evidence_grounding_rejects_unsupported_quotes(quote, kind, source_text, expected_reason):
    store = InMemoryRepository()
    report = KnowledgePipeline(store).ingest_chunk(
        chunk(source_text or quote), extracted([relation(kind=kind, text=quote)]),
    )
    assert report.rejected_relationships == 1
    assert expected_reason in report.decisions[0].reasons
    assert not store.relationships


def test_missing_chunk_unknown_entity_and_invalid_type():
    pipeline = KnowledgePipeline(InMemoryRepository())
    report = pipeline.ingest_chunk(chunk("FastAPI is based on Starlette."), extracted([
        relation(chunk_id="missing"), relation(source="Unknown"),
    ]))
    assert report.rejected_relationships == 2
    assert "missing_chunk" in report.decisions[0].reasons
    assert "unknown_or_ambiguous_entity" in report.decisions[1].reasons
    with pytest.raises(ValidationError):
        relation(kind="EVERY_POSSIBLE_PHRASE")


def test_contradictory_source_context_is_flagged_even_for_a_positive_quote():
    source = "FastAPI uses Starlette. FastAPI does not use Starlette."
    report = KnowledgePipeline(InMemoryRepository()).ingest_chunk(
        chunk(source), extracted([relation(kind="USES", text="FastAPI uses Starlette.")]),
    )
    assert not report.decisions[0].accepted
    assert "contradictory_source_context" in report.decisions[0].reasons


def test_ingestion_revalidates_constructed_models_and_rejects_unsafe_source_urls():
    invalid = extracted().model_copy(update={
        "relationships": [relation().model_copy(update={"confidence": float("nan")})],
    })
    with pytest.raises(ValidationError):
        KnowledgePipeline(InMemoryRepository()).ingest_chunk(
            chunk("FastAPI is based on Starlette."), invalid,
        )
    with pytest.raises(ValidationError):
        SourceChunk(project_id="p", chunk_id="c", document_id="d", text="",
                    url="javascript:alert(1)")


@pytest.mark.parametrize("value", [-.1, 1.01, float("nan"), float("inf"), True, "0.9"])
def test_malformed_scores_are_rejected(value):
    with pytest.raises(ValidationError):
        relation(importance=value)
    with pytest.raises(ValidationError):
        relation(confidence=value)


def test_importance_confidence_independent_low_importance_is_retained():
    store = InMemoryRepository()
    pipeline = KnowledgePipeline(store)
    quote = "FastAPI mentions Starlette in its examples."
    report = pipeline.ingest_chunk(chunk(quote), extracted([relation(kind="MENTIONS", text=quote)]))
    assert report.accepted_relationships == 1
    decision = report.decisions[0]
    assert decision.importance < .6 and decision.confidence >= .75
    service = ExpansionService(store)
    assert service.expand("project-a", center_id(store)).edges == []
    assert len(service.expand("project-a", center_id(store), min_importance=0.0).edges) == 1
    weak = relation(confidence=.5)
    report = pipeline.ingest_chunk(chunk("FastAPI is based on Starlette.", "weak"), extracted([weak.model_copy(update={"chunk_id": "weak"})]))
    assert report.rejected_relationships == 1
    assert report.decisions[0].importance > .8 and report.decisions[0].confidence == .5
    assert len(store.relationships) == 1


def test_example_context_reduces_importance_without_reducing_evidence_confidence():
    store = InMemoryRepository()
    quote = "FastAPI uses Starlette in an example."
    decision = KnowledgePipeline(store).ingest_chunk(
        chunk(quote), extracted([relation(kind="USES", text=quote)]),
    ).decisions[0]
    assert decision.accepted and decision.confidence == .9
    assert decision.importance < .6
    assert len(store.relationships) == 1


def test_chunk_update_removes_stale_evidence_without_deleting_other_support():
    store = InMemoryRepository()
    pipeline = KnowledgePipeline(store)
    pipeline.ingest_chunk(chunk("FastAPI is based on Starlette."), extracted())
    pipeline.ingest_chunk(chunk("FastAPI is based on Starlette.", "two"), extracted([
        relation(chunk_id="two"),
    ]))
    pipeline.ingest_chunk(chunk("No relationship is stated here."), extracted(relationships=[]))
    assert len(store.relationships) == 1 and len(store.evidence) == 1
    assert next(iter(store.relationships.values())).evidence_count == 1
    pipeline.ingest_chunk(chunk("No relationship is stated here.", "two"), extracted(relationships=[]))
    assert not store.relationships and not store.evidence


def test_provider_schema_validation_unchanged_chunk_cache_and_no_inference_on_expansion():
    calls = []
    def provider(**request):
        calls.append(request)
        return extracted().model_dump_json()
    extractor = StructuredExtractor(provider, provider_version="test-provider/model-v1")
    store = InMemoryRepository()
    pipeline = KnowledgePipeline(store)
    document = chunk("FastAPI is based on Starlette.")
    pipeline.ingest_chunk(document, extractor=extractor)
    pipeline.ingest_chunk(document, extractor=extractor)
    ExpansionService(store).expand("project-a", center_id(store))
    assert len(calls) == 1
    assert "relationships" in calls[0]["schema"]["properties"]
    assert json.loads(calls[0]["messages"][1]["content"])["source_text"] == document.text
    pipeline.ingest_chunk(document, extractor=StructuredExtractor(provider, provider_version="v2"))
    assert len(calls) == 2
    with pytest.raises(ExtractionError):
        StructuredExtractor(lambda **kw: '{"bad": true}', provider_version="test").extract(document)
    wrong = extracted([relation(chunk_id="another")]).model_dump(mode="json")
    with pytest.raises(ExtractionError):
        StructuredExtractor(lambda **kw: wrong, provider_version="test").extract(document)


def test_default_expansion_limits_order_filters_and_nonduplicating_pages():
    store, _ = populate()
    service = ExpansionService(store)
    center = center_id(store)
    first = service.expand("project-a", center)
    assert len(first.edges) == 5 and first.pagination.has_more
    assert [edge.importance for edge in first.edges] == sorted([edge.importance for edge in first.edges], reverse=True)
    second = service.expand("project-a", center, cursor=first.pagination.next_cursor)
    assert len(second.edges) == 3 and not second.pagination.has_more
    assert not {edge.id for edge in first.edges} & {edge.id for edge in second.edges}
    assert len({node.id for node in first.nodes}) == len(first.nodes)
    assert service.expand("project-a", center, min_importance=.79).pagination.returned == 1
    assert service.expand("project-a", center, min_confidence=.95).edges == []
    assert service.expand("project-a", center) == first
    for parameters in ({"limit": 0}, {"limit": 51}, {"min_confidence": float("nan")}):
        with pytest.raises(ValueError):
            service.expand("project-a", center, **parameters)


def test_contextual_ranking_and_stable_tie_breaking():
    store, pipeline = populate(3)
    quote = "FastAPI supports Async/Await."
    pipeline.ingest_chunk(chunk(quote, "async"), extracted(
        [relation(target="Async/Await", kind="SUPPORTS", text=quote, chunk_id="async", importance=.75)],
        [entity("FastAPI"), entity("Async/Await", "Concept")],
    ))
    service = ExpansionService(store)
    result = service.expand("project-a", center_id(store), context="async await")
    assert result.nodes[0].label == "Async/Await"
    assert result.edges[0].target == result.nodes[0].id


def test_equal_scores_use_stable_edge_ids_for_pagination():
    store = InMemoryRepository()
    pipeline = KnowledgePipeline(store)
    for index in range(6):
        text = f"FastAPI uses Library{index}."
        pipeline.ingest_chunk(chunk(text, str(index)), extracted(
            [relation(target=f"Library{index}", kind="USES", text=text, chunk_id=str(index))],
            [entity("FastAPI"), entity(f"Library{index}", "Library")],
        ))
    service = ExpansionService(store)
    first = service.expand("project-a", center_id(store), limit=3)
    second = service.expand("project-a", center_id(store), limit=3, cursor=first.pagination.next_cursor)
    identifiers = [edge.id for edge in first.edges + second.edges]
    assert identifiers == sorted(identifiers) and len(set(identifiers)) == 6


def test_project_isolation_missing_nodes_and_cursor_scope():
    store, pipeline = populate(7)
    service, center = ExpansionService(store), center_id(store)
    cursor = service.expand("project-a", center).pagination.next_cursor
    with pytest.raises(NodeNotFound):
        service.expand("project-b", center)
    with pytest.raises(InvalidCursor):
        service.expand("project-a", center, cursor=cursor, min_importance=.5)
    with pytest.raises(InvalidCursor):
        service.expand("project-a", center, cursor="not-json")
    pipeline.ingest_chunk(chunk("FastAPI uses NewLibrary.", "new"), extracted(
        [relation(target="NewLibrary", kind="USES", text="FastAPI uses NewLibrary.", chunk_id="new")],
        [entity("FastAPI"), entity("NewLibrary", "Library")],
    ))
    with pytest.raises(StaleCursor):
        service.expand("project-a", center, cursor=cursor)


def test_evidence_details_pagination_and_isolation():
    store = InMemoryRepository()
    pipeline = KnowledgePipeline(store)
    for index in range(3):
        identifier = str(index)
        pipeline.ingest_chunk(chunk("FastAPI is based on Starlette.", identifier), extracted([
            relation(chunk_id=identifier),
        ]))
    service = ExpansionService(store)
    edge_id = next(iter(store.relationships.values())).relationship_id
    first = service.evidence("project-a", edge_id, limit=2)
    second = service.evidence("project-a", edge_id, limit=2, cursor=first["pagination"]["next_cursor"])
    assert len(first["evidence"]) == 2 and len(second["evidence"]) == 1
    assert not {item["evidence_id"] for item in first["evidence"]} & {item["evidence_id"] for item in second["evidence"]}
    with pytest.raises(NodeNotFound):
        service.evidence("project-b", edge_id)


def test_failed_write_rolls_back_and_generic_heading_entities_are_excluded():
    store = InMemoryRepository()
    def fail(transaction):
        transaction.put_entity(CanonicalEntity(project_id="p", entity_id="a", canonical_name="A", entity_type="Tool"))
        raise RuntimeError("rollback")
    with pytest.raises(RuntimeError):
        store.write("p", fail)
    assert not store.entities
    result, notes = EntityNormalizer(store).normalize("p", [entity("Introduction", "Concept"), entity("Next", "Concept")])
    assert not result and len(notes) == 2


def request(app, path, params=None, method="GET"):
    response = []
    data = b"".join(app({"REQUEST_METHOD": method, "PATH_INFO": path,
                         "QUERY_STRING": urlencode(params or {})},
                        lambda status, headers: response.append((status, headers))))
    return int(response[0][0].split()[0]), json.loads(data)


def test_wsgi_api_validates_limits_projects_evidence_and_errors():
    store, _ = populate()
    app = GraphAPI(ExpansionService(store))
    path = f"/api/graph/nodes/{center_id(store)}/expand"
    status, result = request(app, path, {"project_id": "project-a"})
    assert status == 200 and len(result["edges"]) == 5
    assert request(app, path, {"project_id": "other"})[0] == 404
    for params in ({}, {"project_id": "project-a", "limit": "51"},
                   {"project_id": "project-a", "min_confidence": "NaN"},
                   {"project_id": "project-a", "unexpected": "x"}):
        assert request(app, path, params)[0] == 422
    assert request(app, path, method="POST")[0] == 405
    assert request(app, "/api/graph/config")[1]["default_expansion_limit"] == 5
    edge_path = "/api/graph/edges/" + result["edges"][0]["id"] + "/evidence"
    status, details = request(app, edge_path, {"project_id": "project-a"})
    assert status == 200 and details["evidence"][0]["text"].startswith("FastAPI uses")


def test_wsgi_pagination_uses_same_filters_and_reports_graph_changes():
    store, pipeline = populate()
    app = GraphAPI(ExpansionService(store))
    path = f"/api/graph/nodes/{center_id(store)}/expand"
    _, first = request(app, path, {"project_id": "project-a"})
    cursor = first["pagination"]["next_cursor"]
    status, second = request(app, path, {"project_id": "project-a", "cursor": cursor})
    assert status == 200 and len(second["edges"]) == 3
    assert not {edge["id"] for edge in first["edges"]} & {edge["id"] for edge in second["edges"]}
    assert request(app, path, {"project_id": "project-a", "cursor": cursor, "context": "changed"})[0] == 422
    pipeline.ingest_chunk(chunk("FastAPI is based on Starlette.", "new"), extracted([
        relation(chunk_id="new"),
    ]))
    assert request(app, path, {"project_id": "project-a", "cursor": cursor})[0] == 409
