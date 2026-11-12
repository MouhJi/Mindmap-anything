"""Validated contracts; scores are heuristics, never calibrated probabilities."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field, field_validator, model_validator
from urllib.parse import urlsplit

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Score = Annotated[float, Field(ge=0, le=1, strict=True, allow_inf_nan=False)]


def stable_id(prefix: str, *parts: str) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return prefix + "_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def name_key(name: str) -> str:
    """Case/whitespace only: keep C++, C#, .NET, and qualifiers distinct."""
    return " ".join(unicodedata.normalize("NFC", name).casefold().split())


def terms(text: str) -> list[str]:
    return sorted(set(re.findall(r"[\w+#.]+", text.casefold())) - {
        "a", "an", "the", "is", "of", "and", "for", "to", "in", "with", "on", "as",
    })


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, revalidate_instances="always")


class EntityType(StrEnum):
    FRAMEWORK = "Framework"
    LIBRARY = "Library"
    LANGUAGE = "Language"
    CONCEPT = "Concept"
    API = "API"
    METHOD = "Method"
    ALGORITHM = "Algorithm"
    PROTOCOL = "Protocol"
    TOOL = "Tool"
    FORMAT = "Format"
    SERVICE = "Service"


class RelationType(StrEnum):
    BASED_ON = "BASED_ON"
    USES = "USES"
    DEPENDS_ON = "DEPENDS_ON"
    SUPPORTS = "SUPPORTS"
    IMPLEMENTS = "IMPLEMENTS"
    EXTENDS = "EXTENDS"
    INTEGRATES_WITH = "INTEGRATES_WITH"
    PART_OF = "PART_OF"
    PROVIDES = "PROVIDES"
    REQUIRES = "REQUIRES"
    MENTIONS = "MENTIONS"
    EXAMPLE_OF = "EXAMPLE_OF"


class SourceChunk(Model):
    """Extraction input; SectionChunk.as_source_chunk() supplies this contract."""

    project_id: Identifier
    chunk_id: Identifier
    document_id: Identifier
    url: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
    text: str
    topic: str = ""

    @field_validator("url")
    @classmethod
    def documentation_url(cls, value):
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("Source URL must be HTTP(S)")
        return value

    @computed_field
    @property
    def content_hash(self) -> str:
        return stable_id("chunk", self.document_id, self.url, self.text, self.topic)


class ExtractedEntity(Model):
    name: Name
    type: EntityType
    description: str | None = None
    aliases: list[Name] = Field(default_factory=list, max_length=100)


class ExtractedRelationship(Model):
    source: Name
    target: Name
    relation_type: RelationType
    description: str | None = None
    evidence: Annotated[str, StringConstraints(max_length=20000)]
    chunk_id: Identifier
    importance: Score | None = None
    confidence: Score | None = None


class ExtractionResult(Model):
    entities: list[ExtractedEntity] = Field(default_factory=list, max_length=500)
    relationships: list[ExtractedRelationship] = Field(default_factory=list, max_length=2000)


class CanonicalEntity(Model):
    project_id: Identifier
    entity_id: Identifier
    canonical_name: Name
    entity_type: EntityType
    aliases: list[Name] = Field(default_factory=list)
    description: str | None = None


class Evidence(Model):
    evidence_id: Identifier
    project_id: Identifier
    relationship_id: Identifier
    chunk_id: Identifier
    document_id: Identifier
    url: str
    text: str
    content_hash: str
    importance: Score
    confidence: Score
    policy_version: str


class CanonicalRelationship(Model):
    project_id: Identifier
    relationship_id: Identifier
    source_id: Identifier
    target_id: Identifier
    relation_type: RelationType
    importance: Score
    confidence: Score
    evidence_count: int = Field(ge=1)
    verified: bool = True


class Decision(Model):
    chunk_id: str
    source: str
    target: str
    relation_type: str
    accepted: bool
    reasons: list[str]
    importance: Score = 0.0
    confidence: Score = 0.0


class IngestionReport(Model):
    processed_chunks: int = 0
    skipped_chunks: int = 0
    accepted_relationships: int = 0
    rejected_relationships: int = 0
    decisions: list[Decision] = Field(default_factory=list)
    normalization_notes: list[str] = Field(default_factory=list)


class GraphPolicy(Model):
    min_confidence: Score = 0.75
    default_importance_threshold: Score = 0.60
    default_expansion_limit: int = Field(default=5, ge=1, strict=True)
    max_expansion_limit: int = Field(default=50, ge=1, le=500, strict=True)
    importance_weight: Score = 0.6
    confidence_weight: Score = 0.4
    context_weight: Score = 0.2
    version: Identifier = "deterministic-v1"

    @model_validator(mode="after")
    def coherent(self):
        if self.default_expansion_limit > self.max_expansion_limit:
            raise ValueError("default expansion limit exceeds maximum")
        if self.importance_weight + self.confidence_weight <= 0:
            raise ValueError("ranking weights must have a positive sum")
        return self

    @property
    def fingerprint(self) -> str:
        return stable_id("policy", self.model_dump_json())


class ExpansionQuery(Model):
    project_id: Identifier
    entity_id: Identifier
    limit: int = Field(ge=1, strict=True)
    min_importance: Score
    min_confidence: Score
    context: Annotated[str, StringConstraints(max_length=1000)] = ""
    cursor: Annotated[str, StringConstraints(max_length=4096)] | None = None


class GraphNode(Model):
    id: str
    label: str
    type: EntityType

    @classmethod
    def from_entity(cls, entity: CanonicalEntity):
        return cls(id=entity.entity_id, label=entity.canonical_name, type=entity.entity_type)


class GraphEdge(Model):
    id: str
    source: str
    target: str
    relation_type: RelationType
    importance: Score
    confidence: Score
    evidence_count: int
    ranking_score: Score


class Pagination(Model):
    returned: int
    has_more: bool
    next_cursor: str | None = None


class ExpansionResult(Model):
    center_node: GraphNode
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    pagination: Pagination
