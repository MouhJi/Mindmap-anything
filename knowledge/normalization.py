"""Conservative incremental normalization against an indexed entity registry."""

from __future__ import annotations

from typing import Protocol

from .models import CanonicalEntity, ExtractedEntity, EntityType, name_key, stable_id, terms

NON_ENTITIES = frozenset({
    "previous", "next", "back to top", "edit this page", "share", "copy page",
    "table of contents", "introduction", "overview", "in a hurry?",
})


class EntityRegistry(Protocol):
    def find_entities(self, project_id: str, entity_type: EntityType,
                      keys: list[str], *, compact: bool = False) -> list[CanonicalEntity]: ...

    def put_entity(self, entity: CanonicalEntity) -> None: ...


def entity_keys(entity: CanonicalEntity, compact: bool = False) -> list[str]:
    keys = {name_key(name) for name in [entity.canonical_name, *entity.aliases]}
    return sorted({key.replace(" ", "") for key in keys} if compact else keys)


def context_agrees(left: str | None, right: str | None) -> bool:
    a, b = set(terms(left or "")), set(terms(right or ""))
    return len(a & b) >= 2 and len(a & b) / max(1, len(a | b)) >= 0.7


class EntityNormalizer:
    def __init__(self, registry: EntityRegistry):
        self.registry = registry

    def normalize(self, project_id: str, extracted: list[ExtractedEntity]
                  ) -> tuple[dict[str, CanonicalEntity], list[str]]:
        resolved: dict[str, CanonicalEntity] = {}
        ambiguous: set[str] = set()
        notes: list[str] = []
        # Deterministic batch order; prefer compact labels over qualified aliases.
        for item in sorted(extracted, key=lambda entity: (
            len(entity.name.split()), len(entity.name), name_key(entity.name), entity.name,
        )):
            key = name_key(item.name)
            if key in NON_ENTITIES:
                notes.append("excluded_navigation_or_generic_heading:" + key)
                continue
            names = [item.name, *item.aliases]
            keys = sorted({name_key(name) for name in names
                           if name_key(name) not in NON_ENTITIES})
            candidates = self.registry.find_entities(project_id, item.type, keys)
            # A shared *third* alias is not proof that two new names are the
            # same entity. Require a direct name match or an explicit alias
            # matching the existing canonical name.
            supported = [candidate for candidate in candidates if (
                key in entity_keys(candidate)
                or name_key(candidate.canonical_name) in {name_key(alias) for alias in item.aliases}
            )]
            if candidates and not supported:
                notes.append("shared_alias_collision_kept_separate:" + key)
            candidates = supported
            if len(candidates) > 1:
                # A bridge alias must not union existing, potentially unrelated entities.
                exact = [candidate for candidate in candidates
                         if name_key(candidate.canonical_name) == key]
                candidates = exact if len(exact) == 1 else []
                notes.append("ambiguous_alias_kept_separate:" + key)
            if not candidates:
                compact = self.registry.find_entities(
                    project_id, item.type, [key.replace(" ", "")], compact=True,
                )
                supported = [candidate for candidate in compact
                             if context_agrees(candidate.description, item.description)]
                if len(supported) == 1:
                    candidates = supported
            if candidates:
                canonical = candidates[0].model_copy(deep=True)
                canonical.aliases = sorted(set(canonical.aliases + names) - {
                    canonical.canonical_name,
                })
                if not canonical.description and item.description:
                    canonical.description = item.description
            else:
                canonical = CanonicalEntity(
                    project_id=project_id, entity_id=stable_id("ent", project_id, item.type, key),
                    canonical_name=item.name, entity_type=item.type,
                    aliases=sorted(set(item.aliases) - {item.name}), description=item.description,
                )
            self.registry.put_entity(canonical)
            for name in names:
                lookup = name_key(name)
                if lookup in resolved and resolved[lookup].entity_id != canonical.entity_id:
                    ambiguous.add(lookup)
                resolved[lookup] = canonical
        for lookup in ambiguous:
            resolved.pop(lookup, None)
            notes.append("ambiguous_endpoint:" + lookup)
        return resolved, notes
