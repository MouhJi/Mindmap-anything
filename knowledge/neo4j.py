"""Optional Neo4j 5.7+ repository, using parameterized bounded queries.

Evidence is stored as separate nodes, not nested relationship properties.
Writes lock a project record, making alias resolution and chunk replacement atomic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .models import CanonicalEntity, CanonicalRelationship, Evidence, terms
from .normalization import entity_keys
from .repository import RepositoryUnavailable

EXPANSION_CYPHER = """
MATCH (center:Entity {project_id: $project_id, entity_id: $entity_id})
MATCH (center)-[r:RELATIONSHIP]-(neighbor:Entity)
WHERE r.project_id = $project_id AND neighbor.project_id = $project_id
  AND r.verified = true AND r.evidence_count > 0
  AND r.importance >= $min_importance AND r.confidence >= $min_confidence
WITH DISTINCT r, neighbor,
  CASE WHEN size($context_terms) = 0 THEN 0.0 ELSE
    toFloat(size([term IN $context_terms WHERE term IN neighbor.search_terms]))
      / size($context_terms) END AS relevance
WITH r, neighbor,
  ($iw * r.importance + $cw * r.confidence + $rw * relevance) / ($iw + $cw + $rw) AS score
WHERE $after_score IS NULL OR score < $after_score
   OR (score = $after_score AND r.relationship_id > $after_id)
RETURN properties(r) AS edge, properties(neighbor) AS neighbor, score
ORDER BY score DESC, r.relationship_id ASC
LIMIT $fetch_limit
"""


def _entity(properties):
    fields = CanonicalEntity.model_fields
    return CanonicalEntity.model_validate({key: value for key, value in properties.items() if key in fields})


class Neo4jRepository:
    def __init__(self, driver, *, database: str = "neo4j"):
        self.driver, self.database = driver, database

    @classmethod
    def from_env(cls):
        required = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")
        if not all(os.environ.get(name) for name in required):
            raise ValueError("Configure NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD")
        try:
            from neo4j import GraphDatabase
        except ImportError:
            raise RuntimeError('Install the project with the "graph" extra') from None
        driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(
            os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"],
        ))
        return cls(driver, database=os.environ.get("NEO4J_DATABASE", "neo4j"))

    def close(self):
        self.driver.close()

    def ensure_schema(self):
        schema = (Path(__file__).parent / "migrations/001_quality_graph.cypher").read_text(encoding="utf-8")
        with self.driver.session(database=self.database) as session:
            for statement in schema.split(";"):
                if statement.strip():
                    session.run(statement).consume()

    def read(self, project_id, operation):
        try:
            with self.driver.session(database=self.database) as session:
                return session.execute_read(lambda tx: operation(_Transaction(tx, project_id)))
        except Exception as error:
            # Preserve domain/validation errors; suppress database connection details.
            if type(error).__module__.startswith("neo4j"):
                raise RepositoryUnavailable("Graph database is unavailable") from None
            raise

    def write(self, project_id, operation):
        def transaction(tx):
            tx.run("""
                MERGE (p:KnowledgeProject {project_id: $project_id})
                ON CREATE SET p.revision = 0, p.write_lock = 0
                SET p.write_lock = p.write_lock + 1
            """, project_id=project_id).consume()
            return operation(_Transaction(tx, project_id))

        try:
            with self.driver.session(database=self.database) as session:
                return session.execute_write(transaction)
        except Exception as error:
            if type(error).__module__.startswith("neo4j"):
                raise RepositoryUnavailable("Graph database is unavailable") from None
            raise


class _Transaction:
    def __init__(self, transaction, project_id):
        self.tx, self.project_id = transaction, project_id

    def _scope(self, project_id):
        if project_id != self.project_id:
            raise ValueError("Cross-project transaction access")

    def revision(self, project_id):
        self._scope(project_id)
        record = self.tx.run("""
            MATCH (p:KnowledgeProject {project_id: $project_id}) RETURN p.revision AS revision
        """, project_id=project_id).single()
        return record["revision"] if record else 0

    def find_entities(self, project_id, entity_type, keys, *, compact=False):
        self._scope(project_id)
        records = self.tx.run("""
            UNWIND $keys AS key
            MATCH (name:EntityName {project_id: $project_id, entity_type: $entity_type,
                                   compact: $compact, key: key})<-[:HAS_NAME]-(e:Entity)
            WHERE e.project_id = $project_id
            RETURN DISTINCT properties(e) AS entity ORDER BY entity.entity_id
        """, project_id=project_id, entity_type=str(entity_type), keys=keys, compact=compact)
        return [_entity(record["entity"]) for record in records]

    def put_entity(self, entity):
        self._scope(entity.project_id)
        properties = entity.model_dump(mode="json")
        properties["search_terms"] = terms(" ".join([
            entity.canonical_name, entity.description or "", *entity.aliases,
        ]))
        names = [{"key": key, "compact": compact} for compact in (False, True)
                 for key in entity_keys(entity, compact)]
        self.tx.run("""
            MERGE (e:Entity {project_id: $project_id, entity_id: $entity_id})
            SET e += $properties
            WITH e UNWIND $names AS item
            MERGE (name:EntityName {project_id: $project_id, entity_type: $entity_type,
                                    compact: item.compact, key: item.key})
            MERGE (e)-[:HAS_NAME]->(name)
        """, project_id=entity.project_id, entity_id=entity.entity_id,
                    entity_type=str(entity.entity_type), properties=properties, names=names).consume()

    def get_entity(self, project_id, entity_id):
        self._scope(project_id)
        record = self.tx.run("""
            MATCH (e:Entity {project_id: $project_id, entity_id: $entity_id})
            RETURN properties(e) AS entity
        """, project_id=project_id, entity_id=entity_id).single()
        return _entity(record["entity"]) if record else None

    def chunk_revision(self, project_id, chunk_id):
        self._scope(project_id)
        record = self.tx.run("""
            MATCH (c:SourceChunk {project_id: $project_id, chunk_id: $chunk_id})
            RETURN c.content_hash AS hash, c.extraction_revision AS revision
        """, project_id=project_id, chunk_id=chunk_id).single()
        return (record["hash"], record["revision"]) if record else None

    def replace_chunk(self, chunk, extraction_revision):
        self._scope(chunk.project_id)
        affected = {record["id"] for record in self.tx.run("""
            MATCH (ev:Evidence {project_id: $project_id, chunk_id: $chunk_id})
            RETURN DISTINCT ev.relationship_id AS id
        """, project_id=chunk.project_id, chunk_id=chunk.chunk_id)}
        self.tx.run("""
            MATCH (ev:Evidence {project_id: $project_id, chunk_id: $chunk_id}) DELETE ev
        """, project_id=chunk.project_id, chunk_id=chunk.chunk_id).consume()
        self.tx.run("""
            MERGE (c:SourceChunk {project_id: $project_id, chunk_id: $chunk_id})
            SET c += $properties, c.extraction_revision = $revision
        """, project_id=chunk.project_id, chunk_id=chunk.chunk_id,
                    properties=chunk.model_dump(mode="json"), revision=extraction_revision).consume()
        return affected

    def put_relationship(self, edge):
        self._scope(edge.project_id)
        self.tx.run("""
            MATCH (source:Entity {project_id: $project_id, entity_id: $source_id})
            MATCH (target:Entity {project_id: $project_id, entity_id: $target_id})
            MERGE (source)-[r:RELATIONSHIP {project_id: $project_id,
                                           relationship_id: $relationship_id}]->(target)
            SET r += $properties
        """, project_id=edge.project_id, source_id=edge.source_id, target_id=edge.target_id,
                    relationship_id=edge.relationship_id, properties=edge.model_dump(mode="json")).consume()

    def put_evidence(self, evidence):
        self._scope(evidence.project_id)
        self.tx.run("""
            MERGE (ev:Evidence {project_id: $project_id, evidence_id: $evidence_id})
            SET ev += $properties
        """, project_id=evidence.project_id, evidence_id=evidence.evidence_id,
                    properties=evidence.model_dump(mode="json")).consume()

    def finish_chunk(self, project_id, chunk_id, affected, decisions):
        self._scope(project_id)
        self.tx.run("""
            UNWIND $ids AS identifier
            MATCH ()-[r:RELATIONSHIP {project_id: $project_id, relationship_id: identifier}]->()
            OPTIONAL MATCH (ev:Evidence {project_id: $project_id, relationship_id: identifier})
            WITH r, count(ev) AS n, max(ev.importance) AS importance, max(ev.confidence) AS confidence
            FOREACH (_ IN CASE WHEN n = 0 THEN [1] ELSE [] END | DELETE r)
            FOREACH (_ IN CASE WHEN n > 0 THEN [1] ELSE [] END |
              SET r.evidence_count = n, r.importance = importance, r.confidence = confidence)
        """, project_id=project_id, ids=sorted(affected)).consume()
        self.tx.run("""
            MATCH (c:SourceChunk {project_id: $project_id, chunk_id: $chunk_id})
            SET c.quality_decisions_json = $decisions
            WITH c MATCH (p:KnowledgeProject {project_id: $project_id})
            SET p.revision = p.revision + 1
        """, project_id=project_id, chunk_id=chunk_id,
                    decisions=json.dumps(decisions, ensure_ascii=False)).consume()

    def get_relationship(self, project_id, relationship_id):
        self._scope(project_id)
        record = self.tx.run("""
            MATCH (s:Entity)-[r:RELATIONSHIP {project_id: $project_id,
                                              relationship_id: $relationship_id}]->(t:Entity)
            WHERE s.project_id = $project_id AND t.project_id = $project_id
            RETURN properties(r) AS edge
        """, project_id=project_id, relationship_id=relationship_id).single()
        return CanonicalRelationship.model_validate(record["edge"]) if record else None

    def candidates(self, query, context_terms, weights, after):
        self._scope(query.project_id)
        records = self.tx.run(
            EXPANSION_CYPHER, project_id=query.project_id, entity_id=query.entity_id,
            min_importance=query.min_importance, min_confidence=query.min_confidence,
            context_terms=context_terms, iw=weights[0], cw=weights[1], rw=weights[2],
            after_score=after[0] if after else None, after_id=after[1] if after else None,
            fetch_limit=query.limit + 1,
        )
        return [(CanonicalRelationship.model_validate(record["edge"]),
                 _entity(record["neighbor"]), record["score"]) for record in records]

    def evidence_page(self, project_id, relationship_id, after_id, limit):
        self._scope(project_id)
        records = self.tx.run("""
            MATCH (ev:Evidence {project_id: $project_id, relationship_id: $relationship_id})
            WHERE $after_id IS NULL OR ev.evidence_id > $after_id
            RETURN properties(ev) AS evidence ORDER BY ev.evidence_id LIMIT $fetch_limit
        """, project_id=project_id, relationship_id=relationship_id,
                    after_id=after_id, fetch_limit=limit + 1)
        return [Evidence.model_validate(record["evidence"]) for record in records]
