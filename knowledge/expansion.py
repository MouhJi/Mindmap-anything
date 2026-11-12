"""Deterministic bounded expansion and query/revision-bound keyset cursors."""

from __future__ import annotations

import base64
import binascii
import json
import math

from .models import (
    ExpansionQuery, ExpansionResult, GraphEdge, GraphNode, GraphPolicy, Pagination,
    stable_id, terms,
)
from .repository import GraphRepository


class NodeNotFound(LookupError):
    pass


class InvalidCursor(ValueError):
    pass


class StaleCursor(ValueError):
    pass


def encode_cursor(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def decode_cursor(cursor: str) -> dict:
    try:
        if len(cursor) > 4096:
            raise ValueError
        value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError, binascii.Error, RecursionError):
        raise InvalidCursor("Malformed cursor") from None


class ExpansionService:
    def __init__(self, repository: GraphRepository, policy: GraphPolicy | None = None):
        self.repository = repository
        self.policy = policy or GraphPolicy()

    def expand(self, project_id: str, entity_id: str, **parameters) -> ExpansionResult:
        query = ExpansionQuery.model_validate({
            "project_id": project_id, "entity_id": entity_id,
            "limit": self.policy.default_expansion_limit,
            "min_importance": self.policy.default_importance_threshold,
            "min_confidence": self.policy.min_confidence, **parameters,
        })
        if query.limit > self.policy.max_expansion_limit:
            raise ValueError("Expansion limit exceeds configured maximum")
        fingerprint = stable_id("query", self.policy.fingerprint,
                                query.model_dump_json(exclude={"cursor", "limit"}))
        context_terms = terms(query.context)
        weights = (self.policy.importance_weight, self.policy.confidence_weight,
                   self.policy.context_weight if context_terms else 0.0)

        def read(store):
            center = store.get_entity(project_id, entity_id)
            if center is None:
                raise NodeNotFound("Node not found in this project")
            revision = store.revision(project_id)
            after = None
            if query.cursor:
                cursor = decode_cursor(query.cursor)
                if cursor.get("query") != fingerprint:
                    raise InvalidCursor("Cursor belongs to another query or project")
                if cursor.get("revision") != revision:
                    raise StaleCursor("Graph changed; restart expansion from its first page")
                score, identifier = cursor.get("score"), cursor.get("id")
                if (type(score) not in {int, float} or not math.isfinite(score)
                        or not 0 <= score <= 1 or not isinstance(identifier, str)):
                    raise InvalidCursor("Invalid cursor position")
                after = (score, identifier)
            candidates = store.candidates(query, context_terms, weights, after)
            if store.revision(project_id) != revision:
                raise StaleCursor("Graph changed during expansion; retry")
            has_more = len(candidates) > query.limit
            selected = candidates[:query.limit]
            nodes, edges = {}, []
            for relationship, neighbor, score in selected:
                if neighbor.entity_id != center.entity_id:
                    nodes[neighbor.entity_id] = GraphNode.from_entity(neighbor)
                edges.append(GraphEdge(
                    id=relationship.relationship_id, source=relationship.source_id,
                    target=relationship.target_id, relation_type=relationship.relation_type,
                    importance=relationship.importance, confidence=relationship.confidence,
                    evidence_count=relationship.evidence_count, ranking_score=score,
                ))
            cursor = None
            if has_more:
                edge, _, score = selected[-1]
                cursor = encode_cursor({"query": fingerprint, "revision": revision,
                                        "score": score, "id": edge.relationship_id})
            return ExpansionResult(
                center_node=GraphNode.from_entity(center), nodes=list(nodes.values()), edges=edges,
                pagination=Pagination(returned=len(edges), has_more=has_more, next_cursor=cursor),
            )

        return self.repository.read(project_id, read)

    def evidence(self, project_id: str, relationship_id: str, *, limit: int | None = None,
                 cursor: str | None = None) -> dict:
        limit = self.policy.default_expansion_limit if limit is None else limit
        if type(limit) is not int or not 1 <= limit <= self.policy.max_expansion_limit:
            raise ValueError("Invalid evidence page limit")

        def read(store):
            edge = store.get_relationship(project_id, relationship_id)
            if edge is None:
                raise NodeNotFound("Relationship not found in this project")
            revision = store.revision(project_id)
            fingerprint = stable_id("evidence", project_id, relationship_id)
            after_id = None
            if cursor:
                position = decode_cursor(cursor)
                if position.get("query") != fingerprint or not isinstance(position.get("id"), str):
                    raise InvalidCursor("Cursor belongs to another relationship")
                if position.get("revision") != revision:
                    raise StaleCursor("Graph changed; restart evidence pagination")
                after_id = position["id"]
            records = store.evidence_page(project_id, relationship_id, after_id, limit)
            if store.revision(project_id) != revision:
                raise StaleCursor("Graph changed during evidence lookup; retry")
            more, selected = len(records) > limit, records[:limit]
            next_cursor = encode_cursor({"query": fingerprint, "revision": revision,
                                         "id": selected[-1].evidence_id}) if more else None
            return {
                "relationship": edge.model_dump(mode="json"),
                "source_node": GraphNode.from_entity(store.get_entity(project_id, edge.source_id)).model_dump(mode="json"),
                "target_node": GraphNode.from_entity(store.get_entity(project_id, edge.target_id)).model_dump(mode="json"),
                "evidence": [record.model_dump(mode="json") for record in selected],
                "pagination": Pagination(returned=len(selected), has_more=more,
                                         next_cursor=next_cursor).model_dump(),
            }

        return self.repository.read(project_id, read)
