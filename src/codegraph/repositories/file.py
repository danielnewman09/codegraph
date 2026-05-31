"""Repository for FileNode persistence."""

from codegraph.models.file import FileNode


class FileRepository:
    """CRUD operations for :class:`FileNode` backed by neomodel."""

    def save(self, node: FileNode) -> FileNode:
        return node.save()

    def get(self, refid: str) -> FileNode | None:
        return FileNode.nodes.get_or_none(refid=refid)

    def bulk_save(self, nodes: list[FileNode]) -> list[FileNode]:
        return [node.save() for node in nodes]
