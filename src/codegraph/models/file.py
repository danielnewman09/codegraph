"""File node model (:File label in Neo4j)."""

from neomodel import StructuredNode, StringProperty, UniqueIdProperty


class FileNode(StructuredNode):
    """A source file in the codebase."""

    refid = UniqueIdProperty()
    name = StringProperty(default="")
    path = StringProperty(default="")
    language = StringProperty(default="")
    source = StringProperty(default="")
