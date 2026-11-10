"""Cypher contract tests plus explicitly opt-in live Neo4j integration."""

import os
from pathlib import Path
from uuid import uuid4

import pytest

from knowledge.expansion import ExpansionService
from knowledge.ingestion import KnowledgePipeline
from knowledge.models import EntityType
from knowledge.neo4j import EXPANSION_CYPHER, Neo4jRepository, _Transaction
from tests.test_knowledge import chunk, entity, extracted, relation


def test_neo4j_expansion_is_parameterized_filtered_ranked_and_bounded():
    from knowledge.models import ExpansionQuery
    class Transaction:
        def __init__(self):
            self.calls = []
        def run(self, query, **parameters):
            self.calls.append((query, parameters))
            return []
    transaction = Transaction()
    scoped = _Transaction(transaction, "private-project")
    request = ExpansionQuery(project_id="private-project", entity_id="node-'injection",
                             limit=5, min_confidence=.75, min_importance=.6)
    assert scoped.candidates(request, ["async"], (.6, .4, .2), None) == []
    query, params = transaction.calls[0]
    assert "LIMIT $fetch_limit" in query and params["fetch_limit"] == 6
    assert "ORDER BY score DESC, r.relationship_id ASC" in query
    assert "r.verified = true" in query
    assert "neighbor.project_id = $project_id" in query
    assert "node-'injection" not in query
    assert params["entity_id"] == "node-'injection"
    with pytest.raises(ValueError):
        scoped.get_entity("other-project", "node")


def test_schema_preserves_separate_evidence_and_scoped_uniqueness():
    import knowledge
    path = Path(knowledge.__file__).parent / "migrations/001_quality_graph.cypher"
    schema = path.read_text(encoding="utf-8")
    assert "(n.project_id, n.entity_id) IS UNIQUE" in schema
    assert "(r.project_id, r.relationship_id) IS UNIQUE" in schema
    assert "(n.project_id, n.evidence_id) IS UNIQUE" in schema


@pytest.mark.skipif(os.getenv("GRAPH_TEST_NEO4J") != "1", reason="Live Neo4j unavailable/unconfigured; set GRAPH_TEST_NEO4J=1 and NEO4J_* to opt in")
def test_live_neo4j_idempotent_ingestion_evidence_expansion_and_isolation():
    pytest.importorskip("neo4j", reason="Neo4j driver not installed")
    repository = Neo4jRepository.from_env()
    project_id = "test-quality-" + uuid4().hex
    try:
        repository.driver.verify_connectivity()
        repository.ensure_schema()
        pipeline = KnowledgePipeline(repository)
        original = chunk("FastAPI is based on Starlette.", project=project_id)
        first = pipeline.ingest_chunk(original, extracted())
        assert first.accepted_relationships == 1
        assert pipeline.ingest_chunk(original, extracted()).skipped_chunks == 1
        pipeline.ingest_chunk(original, extracted(), force=True)
        quote = "FastAPI uses Pydantic."
        pipeline.ingest_chunk(chunk(quote, "pydantic", project_id), extracted(
            [relation(target="Pydantic", kind="USES", text=quote, chunk_id="pydantic")],
            [entity("FastAPI"), entity("Pydantic", "Library")],
        ))
        pipeline.ingest_chunk(chunk(original.text, "second", project_id), extracted([
            relation(chunk_id="second"),
        ]))
        center = repository.read(project_id, lambda tx: tx.find_entities(
            project_id, EntityType.FRAMEWORK, ["fastapi"],
        ))[0]
        service = ExpansionService(repository)
        expanded = service.expand(project_id, center.entity_id)
        assert len(expanded.edges) == 2
        assert expanded.edges[0].relation_type == "BASED_ON"
        details = service.evidence(project_id, expanded.edges[0].id)
        assert len(details["evidence"]) == 2
        assert details["relationship"]["evidence_count"] == 2
        from knowledge.expansion import NodeNotFound
        with pytest.raises(NodeNotFound):
            service.expand("different-project", center.entity_id)
        pipeline.ingest_chunk(chunk("Nothing is asserted here.", project=project_id), extracted(relationships=[]))
        pipeline.ingest_chunk(chunk("Nothing is asserted here.", "second", project_id), extracted(relationships=[]))
        assert len(service.expand(project_id, center.entity_id).edges) == 1
    finally:
        # Only this test's unique namespace is removed; never touch another project.
        with repository.driver.session(database=repository.database) as session:
            session.run("MATCH (n) WHERE n.project_id = $project_id DETACH DELETE n", project_id=project_id).consume()
        repository.close()
