"""Canonical inventory and deterministic reconciliation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable

from codegraph_index.contracts import (
    ChangeSet,
    EntityRef,
    IndexDelta,
    IndexFinding,
    RelationshipRef,
)


@dataclass(frozen=True, slots=True)
class Inventory:
    """Source-scoped persisted identity inventory."""

    entities: dict[str, EntityRef] = field(default_factory=dict)
    relationships: frozenset[RelationshipRef] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entities", dict(self.entities))
        object.__setattr__(self, "relationships", frozenset(self.relationships))

    def keys(self) -> frozenset[str]:
        return frozenset(self.entities)


def _fingerprint(node) -> str:
    from codegraph.models.descriptors import PropertyRegistry

    properties = PropertyRegistry.properties_of(type(node))
    data = {
        name: getattr(node, name, None)
        for name in properties
        if name not in {"uid", "canonical_key", "element_id", "tags"}
    }
    return json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))


def _validate_key(key: str, *, context: str) -> None:
    from codegraph.identity import CanonicalIdentity

    try:
        CanonicalIdentity.from_key(key)
    except Exception as exc:
        raise ValueError(f"{context} has invalid canonical key {key!r}") from exc


def inventory_from_graph(graph, *, source: str | None = None) -> Inventory:
    """Build a canonical inventory from a ``LayerGraph`` object."""
    entities: dict[str, EntityRef] = {}
    relationships: set[RelationshipRef] = set()
    visited: set[str] = set()

    def visit(entry) -> None:
        node = entry.node
        key = getattr(node, "canonical_key", "") or ""
        node_source = getattr(node, "source", "") or ""
        if source is not None and node_source != source:
            return
        if not key:
            raise ValueError(f"{type(node).__name__} has no canonical_key")
        _validate_key(key, context=type(node).__name__)
        entity = EntityRef(
            canonical_key=key,
            node_type=type(node).__name__,
            source=node_source,
            fingerprint=_fingerprint(node),
        )
        existing = entities.get(key)
        if existing is not None and existing != entity:
            raise ValueError(f"ambiguous canonical entity {key!r}")
        entities[key] = entity
        if key in visited:
            return
        visited.add(key)
        for relation_type, target_key, target_type in entry.references:
            _validate_key(
                target_key,
                context=f"{type(node).__name__} {key!r} relationship {relation_type!r}",
            )
            relationships.add(
                RelationshipRef(
                    source_key=key,
                    relationship_type=relation_type,
                    target_key=target_key,
                )
            )
        for type_children in entry.children.values():
            for child in type_children.values():
                child_key = getattr(child.node, "canonical_key", "") or ""
                if child_key:
                    _validate_key(
                        child_key,
                        context=f"{type(node).__name__} {key!r} composition",
                    )
                    relationships.add(
                        RelationshipRef(
                            source_key=key,
                            relationship_type="COMPOSES",
                            target_key=child_key,
                        )
                    )
                visit(child)

    for entry in graph.entries.values():
        visit(entry)
    return Inventory(entities, frozenset(relationships))


def inventory_from_repository(repository, *, source: str, edge_loader=None) -> Inventory:
    """Read an exact source-scoped inventory from a graph repository.

    ``GraphRepository.get_by_source`` returns a presentation graph: it adds
    one-hop neighbours and stores both incoming and outgoing edge descriptors.
    That is useful for exploration, but it cannot be used for reconciliation
    because it can manufacture reverse relationship references.  This helper
    deliberately uses the repository's exact source query and outgoing-edge
    contract instead.
    """
    if edge_loader is None:
        edge_loader = repository.get_all_edges_outgoing

    entities: dict[str, EntityRef] = {}
    relationships: set[RelationshipRef] = set()
    for node in repository.find_all_by_source(source):
        key = getattr(node, "canonical_key", "") or ""
        node_source = getattr(node, "source", "") or ""
        if not key:
            raise ValueError(f"{type(node).__name__} has no canonical_key")
        _validate_key(key, context=type(node).__name__)
        entity = EntityRef(
            canonical_key=key,
            node_type=type(node).__name__,
            source=node_source,
            fingerprint=_fingerprint(node),
        )
        existing = entities.get(key)
        if existing is not None and existing != entity:
            raise ValueError(f"ambiguous canonical entity {key!r}")
        entities[key] = entity
        for edge in edge_loader(node):
            target_key = getattr(edge, "target_key", "") or ""
            if target_key:
                _validate_key(
                    target_key,
                    context=f"{type(node).__name__} {key!r} relationship {edge.relation_type!r}",
                )
                relationships.add(
                    RelationshipRef(
                        source_key=key,
                        relationship_type=edge.relation_type,
                        target_key=target_key,
                    )
                )
    return Inventory(entities, frozenset(relationships))


def delta_between(incoming: Inventory, persisted: Inventory) -> IndexDelta:
    """Classify entity and relationship changes without mutating storage."""
    entity_created = []
    entity_matched = []
    entity_changed = []
    entity_deleted = []
    for key, current in incoming.entities.items():
        previous = persisted.entities.get(key)
        if previous is None:
            entity_created.append(current)
        elif previous == current:
            entity_matched.append(current)
        else:
            entity_changed.append(current)
    for key, previous in persisted.entities.items():
        if key not in incoming.entities:
            entity_deleted.append(previous)

    relation_created = sorted(incoming.relationships - persisted.relationships, key=repr)
    relation_matched = sorted(incoming.relationships & persisted.relationships, key=repr)
    relation_deleted = sorted(persisted.relationships - incoming.relationships, key=repr)
    return IndexDelta(
        entities=ChangeSet(
            created=tuple(entity_created),
            matched=tuple(entity_matched),
            changed=tuple(entity_changed),
            deleted=tuple(entity_deleted),
        ),
        relationships=ChangeSet(
            created=tuple(relation_created),
            matched=tuple(relation_matched),
            deleted=tuple(relation_deleted),
        ),
    )


def delta_from_graph(graph, *, source: str) -> IndexDelta:
    """Return an extraction delta where all incoming identities are created."""
    incoming = inventory_from_graph(graph, source=source)
    return IndexDelta(
        entities=ChangeSet(created=tuple(incoming.entities.values())),
        relationships=ChangeSet(created=tuple(incoming.relationships)),
    )
