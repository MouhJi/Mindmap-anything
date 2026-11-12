"""Storage contract and an indexed in-memory implementation for offline use/tests."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from threading import RLock
from typing import Callable, Protocol, TypeVar

from .models import CanonicalEntity, CanonicalRelationship, EntityType, Evidence, SourceChunk, terms
from .normalization import entity_keys

T = TypeVar("T")


class RepositoryUnavailable(RuntimeError):
    pass


class GraphRepository(Protocol):
    def read(self, project_id: str, operation: Callable) -> T: ...
    def write(self, project_id: str, operation: Callable) -> T: ...


def rank(importance: float, confidence: float, search_terms: list[str],
         context_terms: list[str], weights: tuple[float, float, float]) -> float:
    iw, cw, rw = weights
    relevance = len(set(search_terms) & set(context_terms)) / len(context_terms) if context_terms else 0
    return (iw * importance + cw * confidence + rw * relevance) / (iw + cw + rw)


class InMemoryRepository:
    """Reference repository, not a durable substitute for Neo4j.

    All lookups and neighborhood candidates are project-scoped and indexed.
    Transactions roll back on failure. Query results are detached model copies.
    """

    def __init__(self):
        self.entities = {}
        self.relationships = {}
        self.evidence = {}
        self.chunks = {}
        self.audits = {}
        self.names = defaultdict(set)
        self.adjacency = defaultdict(set)
        self.edge_evidence = defaultdict(set)
        self.chunk_evidence = defaultdict(set)
        self.revisions = defaultdict(int)
        self._lock = RLock()

    def read(self, project_id, operation):
        with self._lock:
            return operation(self)

    def write(self, project_id, operation):
        with self._lock:
            # The reference store is for small offline graphs. Neo4j uses real
            # transactions, avoiding these full-memory rollback snapshots.
            snapshot = deepcopy({key: value for key, value in vars(self).items() if key != "_lock"})
            try:
                return operation(self)
            except Exception:
                vars(self).update(snapshot)
                raise

    def revision(self, project_id):
        return self.revisions[project_id]

    def find_entities(self, project_id, entity_type, keys, *, compact=False):
        ids = set()
        for key in keys:
            ids.update(self.names[(project_id, entity_type, compact, key)])
        return [self.entities[(project_id, identifier)].model_copy(deep=True)
                for identifier in sorted(ids)]

    def put_entity(self, entity):
        self.entities[(entity.project_id, entity.entity_id)] = entity.model_copy(deep=True)
        for compact in (False, True):
            for key in entity_keys(entity, compact):
                self.names[(entity.project_id, entity.entity_type, compact, key)].add(entity.entity_id)

    def get_entity(self, project_id, entity_id):
        entity = self.entities.get((project_id, entity_id))
        return entity.model_copy(deep=True) if entity else None

    def chunk_revision(self, project_id, chunk_id):
        stored = self.chunks.get((project_id, chunk_id))
        return (stored[0].content_hash, stored[1]) if stored else None

    def replace_chunk(self, chunk, extraction_revision):
        affected = set()
        for evidence_id in list(self.chunk_evidence[(chunk.project_id, chunk.chunk_id)]):
            evidence = self.evidence.pop((chunk.project_id, evidence_id))
            self.edge_evidence[(chunk.project_id, evidence.relationship_id)].discard(evidence_id)
            affected.add(evidence.relationship_id)
        self.chunk_evidence[(chunk.project_id, chunk.chunk_id)].clear()
        self.chunks[(chunk.project_id, chunk.chunk_id)] = (chunk.model_copy(deep=True), extraction_revision)
        return affected

    def put_relationship(self, relationship):
        key = (relationship.project_id, relationship.relationship_id)
        self.relationships[key] = relationship.model_copy(deep=True)
        for entity_id in (relationship.source_id, relationship.target_id):
            self.adjacency[(relationship.project_id, entity_id)].add(relationship.relationship_id)

    def put_evidence(self, evidence):
        self.evidence[(evidence.project_id, evidence.evidence_id)] = evidence.model_copy(deep=True)
        self.edge_evidence[(evidence.project_id, evidence.relationship_id)].add(evidence.evidence_id)
        self.chunk_evidence[(evidence.project_id, evidence.chunk_id)].add(evidence.evidence_id)

    def finish_chunk(self, project_id, chunk_id, affected, decisions):
        for identifier in affected:
            key = (project_id, identifier)
            relationship = self.relationships.get(key)
            if not relationship:
                continue
            records = [self.evidence[(project_id, ev)] for ev in self.edge_evidence[key]]
            if not records:
                del self.relationships[key]
                for node in (relationship.source_id, relationship.target_id):
                    self.adjacency[(project_id, node)].discard(identifier)
            else:
                relationship.evidence_count = len(records)
                relationship.importance = max(record.importance for record in records)
                relationship.confidence = max(record.confidence for record in records)
        self.audits[(project_id, chunk_id)] = deepcopy(decisions)
        self.revisions[project_id] += 1

    def get_relationship(self, project_id, relationship_id):
        relationship = self.relationships.get((project_id, relationship_id))
        return relationship.model_copy(deep=True) if relationship else None

    def candidates(self, query, context_terms, weights, after):
        rows = []
        for identifier in self.adjacency[(query.project_id, query.entity_id)]:
            edge = self.relationships[(query.project_id, identifier)]
            if (not edge.verified or edge.importance < query.min_importance
                    or edge.confidence < query.min_confidence):
                continue
            neighbor_id = edge.target_id if edge.source_id == query.entity_id else edge.source_id
            neighbor = self.entities[(query.project_id, neighbor_id)]
            search = terms(" ".join([neighbor.canonical_name, neighbor.description or "", *neighbor.aliases]))
            score = rank(edge.importance, edge.confidence, search, context_terms, weights)
            if after and not (score < after[0] or (score == after[0] and identifier > after[1])):
                continue
            rows.append((edge.model_copy(deep=True), neighbor.model_copy(deep=True), score))
        rows.sort(key=lambda row: (-row[2], row[0].relationship_id))
        return rows[:query.limit + 1]

    def evidence_page(self, project_id, relationship_id, after_id, limit):
        identifiers = sorted(self.edge_evidence[(project_id, relationship_id)])
        return [self.evidence[(project_id, identifier)].model_copy(deep=True)
                for identifier in identifiers if not after_id or identifier > after_id][:limit + 1]
