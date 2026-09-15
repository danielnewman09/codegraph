"""Repository-owned persistence for extracted LayerGraphs."""

from __future__ import annotations

from codegraph_index.inventory import Inventory, inventory_from_graph, inventory_from_repository


class RepositoryPersistence:
    """Persist through an injected Codegraph backend repository.

    The indexing package never constructs Cypher or SQL. Backend-specific
    operations remain behind Codegraph's ``GraphRepository`` interface.
    """

    def __init__(self, backend):
        self.backend = backend

    @property
    def repository(self):
        return self.backend.graph

    def inventory(self, source: str) -> Inventory:
        return inventory_from_repository(
            self.repository,
            source=source,
            edge_loader=self.backend.get_all_edges_outgoing,
        )

    def apply(self, graph, delta) -> None:
        if delta.entities.ambiguous or delta.relationships.ambiguous:
            raise ValueError("ambiguous indexing findings must be resolved before persistence")
        self.backend.bulk_save(graph)
        for relationship in delta.relationships.deleted:
            source = self.repository.find_by_key(relationship.source_key)
            target = self.repository.find_by_key(relationship.target_key)
            if source is not None and target is not None:
                self.backend.disconnect(source, relationship.relationship_type, target)
        stale_keys = sorted(
            entity.canonical_key
            for entity in delta.entities.deleted
            if entity.source
        )
        for key in stale_keys:
            self.repository.delete_by_key(key)


class InMemoryPersistence:
    """Small repository-neutral persistence double for service tests."""

    def __init__(self):
        self.graphs: dict[str, object] = {}

    def inventory(self, source: str) -> Inventory:
        graph = self.graphs.get(source)
        if graph is None:
            return Inventory()
        return inventory_from_graph(graph, source=source)

    def apply(self, graph, delta) -> None:
        if delta.entities.ambiguous or delta.relationships.ambiguous:
            raise ValueError("ambiguous indexing findings must be resolved before persistence")
        source = next(
            (getattr(entry.node, "source", "") for entry in graph.entries.values()),
            "",
        )
        self.graphs[source] = graph
