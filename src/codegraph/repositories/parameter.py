"""Repository for ParameterNode persistence."""

from codegraph.models.parameter import ParameterNode


class ParameterRepository:
    """CRUD operations for :class:`ParameterNode` backed by neomodel."""

    def save(self, node: ParameterNode) -> ParameterNode:
        return node.save()

    def find_by_member_refid(self, member_refid: str) -> list[ParameterNode]:
        return list(ParameterNode.nodes.filter(member_refid=member_refid))

    def bulk_save(self, nodes: list[ParameterNode]) -> list[ParameterNode]:
        return [node.save() for node in nodes]
