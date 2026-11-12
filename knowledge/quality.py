"""Deterministic evidence checks, conservative predicate support and scoring."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .evidence import EvidenceMatcher
from .models import (
    CanonicalEntity, Decision, ExtractedRelationship, GraphPolicy, RelationType, SourceChunk,
    name_key, terms,
)

PREDICATES = {
    RelationType.BASED_ON: r"(?:is |are )?(?:based on|built on|builds upon)",
    RelationType.USES: r"(?:uses?|using)",
    RelationType.DEPENDS_ON: r"(?:depends? on|relies? on)",
    RelationType.SUPPORTS: r"supports?",
    RelationType.IMPLEMENTS: r"implements?",
    RelationType.EXTENDS: r"extends?",
    RelationType.INTEGRATES_WITH: r"integrates? with",
    RelationType.PART_OF: r"(?:is |are )?part of",
    RelationType.PROVIDES: r"provides?",
    RelationType.REQUIRES: r"requires?",
    RelationType.MENTIONS: r"mentions?",
    RelationType.EXAMPLE_OF: r"(?:is |are )?(?:an? )?example of",
}
BASE_IMPORTANCE = {
    RelationType.BASED_ON: .9, RelationType.USES: .8, RelationType.DEPENDS_ON: .9,
    RelationType.SUPPORTS: .85, RelationType.IMPLEMENTS: .85, RelationType.EXTENDS: .8,
    RelationType.INTEGRATES_WITH: .75, RelationType.PART_OF: .8,
    RelationType.PROVIDES: .8, RelationType.REQUIRES: .85,
    RelationType.MENTIONS: .15, RelationType.EXAMPLE_OF: .3,
}
NEGATION = re.compile(r"\b(?:not|never|without|cannot|can't|doesn't|don't|isn't|aren't|no longer|false|incorrect)\b", re.I)
SPECULATION = re.compile(r"\b(?:may|might|could|can|possibly|perhaps|should|would|whether|if)\b", re.I)
INCIDENTAL = re.compile(r"\b(?:in (?:an? |the )?(?:example|tutorial)|for (?:illustration|demonstration)|example (?:code|snippet))\b", re.I)


def normalized_quote(value: str) -> str:
    return " ".join(value.split())


def _name_spans(text: str, entity: CanonicalEntity) -> list[tuple[int, int]]:
    result = []
    for name in [entity.canonical_name, *entity.aliases]:
        pattern = r"(?<!\w)" + re.escape(name_key(name)).replace(r"\ ", r"\s+") + r"(?!\w)"
        result.extend(match.span() for match in re.finditer(pattern, name_key(text)))
    return result


def _names(entity: CanonicalEntity) -> set[str]:
    names = {name_key(name) for name in [entity.canonical_name, *entity.aliases]}
    return names | {f"`{name}`" for name in names}


def _coordinated_names(value: str, known: set[str]) -> set[str]:
    if value in known:
        return {value}
    # Parse coordination only inside an already delimited subject or object.
    if value.count(" and ") != 1:
        return set()
    first, last = value.split(" and ")
    members = [*first.removesuffix(",").split(", "), last]
    return set(members) if all(member in known for member in members) else set()


def predicate_supported(
    evidence: str, source: CanonicalEntity, target: CanonicalEntity, relation_type: RelationType,
    *, entities: Iterable[CanonicalEntity] = (), allow_example_context: bool = False,
) -> tuple[bool, str]:
    quote = name_key(evidence)
    if not _name_spans(quote, source) or not _name_spans(quote, target):
        return False, "predicate_not_deterministically_supported"
    if "?" in quote:
        return False, "interrogative_evidence"
    if NEGATION.search(quote):
        return False, "negated_or_contradictory_evidence"
    if SPECULATION.search(quote):
        return False, "speculative_or_conditional_evidence"

    quote = quote.removesuffix(".")
    if allow_example_context:
        quote = re.sub(r" in (?:an? example|its examples)$", "", quote)
    source_names, target_names = _names(source), _names(target)
    known = source_names | target_names
    for entity in entities:
        known.update(_names(entity))
    predicate = {
        RelationType.USES: r"uses?",
        RelationType.BASED_ON: r"(?:(?:is|are) (?:based on|built on)|builds upon)",
    }.get(relation_type, PREDICATES[relation_type])

    # Match full endpoint groups. Mere order around a verb is insufficient.
    patterns = [(predicate, source_names, target_names, "explicit_directed_predicate")]
    if relation_type == RelationType.BASED_ON:
        patterns.append((
            r"(?:is |are )?(?:the )?foundation of", target_names, source_names,
            "explicit_inverse_predicate",
        ))
    for verb, left, right, reason in patterns:
        for match in re.finditer(r"\b(?:" + verb + r")\b", quote):
            subjects = _coordinated_names(quote[:match.start()].rstrip(), known)
            objects = _coordinated_names(quote[match.end():].lstrip(), known)
            if subjects & left and objects & right and (len(subjects) == 1 or len(objects) == 1):
                return True, reason
    return False, "predicate_not_deterministically_supported"


def contradictory_context(text: str, source: CanonicalEntity, target: CanonicalEntity,
                          relation_type: RelationType) -> bool:
    for clause in re.split(r"(?<=[.!?;])\s+|\s+(?:but|whereas|while)\s+", text):
        lowered = name_key(clause)
        if not NEGATION.search(lowered):
            continue
        sources, targets = _name_spans(clause, source), _name_spans(clause, target)
        for predicate in re.finditer(r"\b" + PREDICATES[relation_type] + r"\b", lowered):
            if any(a[1] <= predicate.start() and predicate.end() <= b[0]
                   for a in sources for b in targets):
                return True
    return False


class QualityEvaluator:
    def __init__(self, policy: GraphPolicy):
        self.policy = policy

    def evaluate(self, relation: ExtractedRelationship, chunk: SourceChunk | None,
                 source: CanonicalEntity | None, target: CanonicalEntity | None, *,
                 matcher: EvidenceMatcher | None = None,
                 entities: Iterable[CanonicalEntity] = (),
                 strict: bool = False) -> Decision:
        decision = Decision(chunk_id=relation.chunk_id, source=relation.source,
                            target=relation.target, relation_type=relation.relation_type,
                            accepted=False, reasons=[])
        if chunk is None or chunk.chunk_id != relation.chunk_id:
            decision.reasons.append("missing_chunk")
        if source is None or target is None:
            decision.reasons.append("unknown_or_ambiguous_entity")
        if not relation.evidence.strip():
            decision.reasons.append("empty_evidence")
        if decision.reasons:
            return decision
        if source.project_id != chunk.project_id or target.project_id != chunk.project_id:
            decision.reasons.append("project_mismatch")
            return decision
        if matcher is None or matcher.text != chunk.text:
            matcher = EvidenceMatcher(chunk.text)
        match = matcher.find(relation.evidence, allow_whitespace=not strict)
        if match is None:
            decision.reasons.append("evidence_not_in_chunk")
            return decision
        quote = normalized_quote(match.prose)
        supported, reason = predicate_supported(
            quote, source, target, relation.relation_type, entities=entities,
            allow_example_context=not strict,
        )
        decision.reasons.append(reason)
        if not supported:
            return decision
        if not match.complete:
            decision.reasons = ["unsupported_relationship", "evidence_not_complete_direct_assertion"]
            return decision
        if contradictory_context(chunk.text, source, target, relation.relation_type) or any(
            contradictory_context(sentence.prose, source, target, relation.relation_type)
            for sentence in matcher.sentences if sentence.span.text != sentence.prose
        ):
            decision.reasons.append("contradictory_source_context")
            return decision
        relevance = bool(set(terms(chunk.topic)) & set(terms(
            source.canonical_name + " " + target.canonical_name,
        )))
        decision.importance = min(1.0, round(BASE_IMPORTANCE[relation.relation_type] + .05 * relevance, 6))
        if INCIDENTAL.search(quote):
            decision.importance *= .5
        # Model estimates may lower deterministic scores, never overrule grounding.
        if relation.importance is not None:
            decision.importance = min(decision.importance, relation.importance)
        decision.confidence = min(.9, relation.confidence) if relation.confidence is not None else .9
        decision.accepted = decision.confidence >= self.policy.min_confidence
        decision.reasons.append("trusted" if decision.accepted else "below_confidence_threshold")
        return decision
