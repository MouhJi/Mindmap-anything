"""Incremental ingestion: normalization, grounding, audit, evidence and edge upserts."""

from __future__ import annotations

from .evidence import EvidenceMatcher
from .extraction import GROUNDING_VERSION, StructuredExtractor
from .models import (
    CanonicalEntity, CanonicalRelationship, Evidence, ExtractionResult, GraphPolicy,
    IngestionReport, SourceChunk, name_key, stable_id,
)
from .normalization import EntityNormalizer
from .quality import QualityEvaluator, _name_spans, normalized_quote
from .repository import GraphRepository


class KnowledgePipeline:
    def __init__(self, repository: GraphRepository, policy: GraphPolicy | None = None):
        self.repository = repository
        self.policy = policy or GraphPolicy()

    def ingest_chunk(self, chunk: SourceChunk, result: ExtractionResult | None = None, *,
                     extractor: StructuredExtractor | None = None, force: bool = False
                     ) -> IngestionReport:
        chunk = SourceChunk.model_validate(chunk)
        if result is not None:
            result = ExtractionResult.model_validate(result)
        if result is None and extractor is None:
            raise ValueError("Supply validated extraction data or a configured provider adapter")
        if result is not None and extractor is not None:
            raise ValueError("Supply either extraction data or an extractor, not both")
        version = (stable_id("provided", result.model_dump_json()) if result is not None
                   else extractor.version)
        revision = stable_id("revision", version, self.policy.fingerprint, GROUNDING_VERSION)
        current = self.repository.read(chunk.project_id, lambda store: store.chunk_revision(
            chunk.project_id, chunk.chunk_id,
        ))
        if not force and current == (chunk.content_hash, revision):
            return IngestionReport(skipped_chunks=1)
        if result is None:
            # LLM calls happen outside retryable database transactions.
            result = extractor.extract(chunk)

        def write(store):
            if not force and store.chunk_revision(chunk.project_id, chunk.chunk_id) == (
                chunk.content_hash, revision,
            ):
                return IngestionReport(skipped_chunks=1)
            report = IngestionReport(processed_chunks=1)
            affected = store.replace_chunk(chunk, revision)
            # Entity mentions must occur in this source, not just an LLM response.
            grounded = []
            for entity in result.entities:
                probe = CanonicalEntity(
                    project_id=chunk.project_id, entity_id="probe", canonical_name=entity.name,
                    entity_type=entity.type, aliases=entity.aliases,
                )
                if _name_spans(chunk.text, probe):
                    grounded.append(entity)
                else:
                    report.normalization_notes.append("entity_not_in_chunk:" + entity.name)
            resolved, notes = EntityNormalizer(store).normalize(chunk.project_id, grounded)
            report.normalization_notes.extend(notes)
            evaluator = QualityEvaluator(self.policy)
            matcher = EvidenceMatcher(chunk.text)
            for relation in result.relationships:
                source, target = resolved.get(name_key(relation.source)), resolved.get(name_key(relation.target))
                evidence_chunk = chunk if relation.chunk_id == chunk.chunk_id else None
                decision = evaluator.evaluate(
                    relation, evidence_chunk, source, target, matcher=matcher,
                    entities=resolved.values(),
                )
                report.decisions.append(decision)
                if not decision.accepted:
                    report.rejected_relationships += 1
                    continue
                identifier = stable_id("rel", chunk.project_id, source.entity_id,
                                       relation.relation_type, target.entity_id)
                edge = CanonicalRelationship(
                    project_id=chunk.project_id, relationship_id=identifier,
                    source_id=source.entity_id, target_id=target.entity_id,
                    relation_type=relation.relation_type, importance=decision.importance,
                    confidence=decision.confidence, evidence_count=1,
                )
                match = matcher.find(relation.evidence, allow_whitespace=True)
                assert match is not None
                # Stable across retries and repeated extraction of the same quote.
                evidence = Evidence(
                    evidence_id=stable_id("ev", identifier, chunk.chunk_id, chunk.content_hash,
                                          normalized_quote(match.span.text)),
                    project_id=chunk.project_id, relationship_id=identifier,
                    chunk_id=chunk.chunk_id, document_id=chunk.document_id, url=chunk.url,
                    text=match.span.text, content_hash=chunk.content_hash,
                    importance=decision.importance, confidence=decision.confidence,
                    policy_version=self.policy.version,
                )
                store.put_relationship(edge)
                store.put_evidence(evidence)
                affected.add(identifier)
                report.accepted_relationships += 1
            store.finish_chunk(chunk.project_id, chunk.chunk_id, affected,
                               [decision.model_dump(mode="json") for decision in report.decisions])
            return report

        return self.repository.write(chunk.project_id, write)
