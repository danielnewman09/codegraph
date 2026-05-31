"""Repository for CompoundNode persistence."""

from codegraph.models.compound import CompoundNode
from codegraph.models.member import MemberNode


class CompoundRepository:
    """CRUD operations for :class:`CompoundNode` backed by neomodel."""

    def save(self, node: CompoundNode) -> CompoundNode:
        """Persist a compound."""
        return node.save()

    def get(self, qualified_name: str) -> CompoundNode | None:
        """Look up by qualified_name. Returns None if not found."""
        return CompoundNode.nodes.get_or_none(qualified_name=qualified_name)

    def find_by_layer(self, layer: str) -> list[CompoundNode]:
        """Return all compounds in a given layer."""
        return list(CompoundNode.nodes.filter(layer=layer))

    def bulk_save(self, nodes: list[CompoundNode]) -> list[CompoundNode]:
        """Persist multiple compounds."""
        return [node.save() for node in nodes]

    def delete_all_design_layer(self) -> int:
        """Remove all design-layer compounds. Returns count deleted."""
        nodes = list(CompoundNode.nodes.filter(layer="design"))
        count = len(nodes)
        for n in nodes:
            n.delete()
        return count

    def delete_by_qualified_name(self, qualified_name: str) -> bool:
        """Delete a single compound by qualified_name. Returns True if found."""
        node = CompoundNode.nodes.get_or_none(qualified_name=qualified_name)
        if node:
            node.delete()
            return True
        return False

    def connect_member(self, compound_qn: str, member_qn: str) -> None:
        """Create a COMPOSES edge from compound to member."""
        c = CompoundNode.nodes.get(qualified_name=compound_qn)
        m = MemberNode.nodes.get(qualified_name=member_qn)
        c.members.connect(m)

    def connect_base(self, child_qn: str, parent_qn: str) -> None:
        """Create a GENERALIZES edge from child to parent compound."""
        child = CompoundNode.nodes.get(qualified_name=child_qn)
        parent = CompoundNode.nodes.get(qualified_name=parent_qn)
        child.base.connect(parent)

    def get_members(self, qualified_name: str) -> list[MemberNode]:
        """Return all members owned by this compound via COMPOSES."""
        c = CompoundNode.nodes.get(qualified_name=qualified_name)
        return list(c.members.all())
