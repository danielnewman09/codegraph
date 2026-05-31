"""Repository for NamespaceNode persistence."""

from codegraph.models.namespace import NamespaceNode
from codegraph.models.compound import CompoundNode


class NamespaceRepository:
    """CRUD operations for :class:`NamespaceNode` backed by neomodel."""

    def save(self, node: NamespaceNode) -> NamespaceNode:
        return node.save()

    def get(self, qualified_name: str) -> NamespaceNode | None:
        return NamespaceNode.nodes.get_or_none(qualified_name=qualified_name)

    def find_by_layer(self, layer: str) -> list[NamespaceNode]:
        return list(NamespaceNode.nodes.filter(layer=layer))

    def bulk_save(self, nodes: list[NamespaceNode]) -> list[NamespaceNode]:
        return [node.save() for node in nodes]

    def connect_compound(self, namespace_qn: str, compound_qn: str) -> None:
        """Create a COMPOSES edge from namespace to compound."""
        ns = NamespaceNode.nodes.get(qualified_name=namespace_qn)
        c = CompoundNode.nodes.get(qualified_name=compound_qn)
        ns.compounds.connect(c)
