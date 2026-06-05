"""File node model (:File label in Neo4j).

FileNode is the target of ``DEFINED_IN`` relationships from compounds
(ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode) and members
(MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode).

    (any compound|member)-[:DEFINED_IN]->(FileNode)
"""

from neomodel import StructuredNode, StringProperty, UniqueIdProperty

from codegraph.models.tags import CodeGraphNode


class FileNode(StructuredNode, CodeGraphNode):
    """A source file in the codebase.

    Attributes:
        refid: Auto-generated unique identifier. Acts as the primary key
            for looking up files in Neo4j and as the ``target_uid`` in
            DEFINED_IN edges from compounds and members. Overrides
            CodeGraphNode.refid as UniqueIdProperty.
        name: The basename of the file (e.g. ``"widget.h"``).
        path: The absolute or project-relative path to the file
            (e.g. ``"/src/widget.h"``).
        language: The programming language of the file as a lowercase string
            (e.g. ``"cpp"``, ``"python"``, ``"java"``).
        source: Name of the project this file belongs to
            (e.g. ``"codegraph"``, ``"llvm"``). Inherited from CodeGraphNode.
    """

    # --- Identity ---
    refid = UniqueIdProperty()

    # --- File metadata ---
    path = StringProperty(default="")
    language = StringProperty(default="")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "path", "source"}
