"""Repository for MemberNode persistence."""

from codegraph.models.member import MemberNode


class MemberRepository:
    """CRUD operations for :class:`MemberNode` backed by neomodel."""

    def save(self, node: MemberNode) -> MemberNode:
        return node.save()

    def get(self, qualified_name: str) -> MemberNode | None:
        return MemberNode.nodes.get_or_none(qualified_name=qualified_name)

    def find_by_layer(self, layer: str) -> list[MemberNode]:
        return list(MemberNode.nodes.filter(layer=layer))

    def bulk_save(self, nodes: list[MemberNode]) -> list[MemberNode]:
        return [node.save() for node in nodes]

    def delete_all_design_layer(self) -> int:
        nodes = list(MemberNode.nodes.filter(layer="design"))
        count = len(nodes)
        for n in nodes:
            n.delete()
        return count

    def delete_by_qualified_name(self, qualified_name: str) -> bool:
        node = MemberNode.nodes.get_or_none(qualified_name=qualified_name)
        if node:
            node.delete()
            return True
        return False
