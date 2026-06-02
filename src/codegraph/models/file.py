"""File node model (:File label in Neo4j).

FileNode is the target of ``DEFINED_IN`` relationships from compounds
(ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode) and members
(MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode).

    (any compound|member)-[:DEFINED_IN]->(FileNode)
"""

from neomodel import StructuredNode, StringProperty, UniqueIdProperty

from codegraph.models.tags import LlmSerializable


class FileNode(StructuredNode, LlmSerializable):
    """A source file in the codebase."""

    refid = UniqueIdProperty()
    name = StringProperty(default="")
    path = StringProperty(default="")
    language = StringProperty(default="")
    source = StringProperty(default="")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "path"}
