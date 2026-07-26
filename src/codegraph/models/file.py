"""File node model (:File label in Neo4j).

FileNode is the target of ``DEFINED_IN`` relationships from compounds
(ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode) and members
(MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode).

    (any compound|member)-[:DEFINED_IN]->(FileNode)
"""

from neomodel import (
    StructuredNode, StringProperty, UniqueIdProperty,
    ArrayProperty, RelationshipTo,
)

from codegraph.models.tags import CodeGraphNode


class FileNode(StructuredNode, CodeGraphNode):
    """A source file in the codebase.

    Attributes:
        refid: External reference ID from the source system (e.g. Doxygen
            refid).  Regular indexed StringProperty.
        uid: Deterministic SHA-1 hash of the file ``path`` — the
            cross-codebase-stable unique key.
        name: The basename of the file (e.g. ``"widget.h"``).
        path: The absolute or project-relative path to the file
            (e.g. ``"/src/widget.h"``) — used as the identity-field input.
        language: The programming language of the file as a lowercase string
            (e.g. ``"cpp"``, ``"python"``, ``"java"``).
        source: Name of the project this file belongs to
            (e.g. ``"codegraph"``, ``"llvm"``). Inherited from CodeGraphNode.
    """

    # --- Identity ---
    uid = UniqueIdProperty()
    refid = StringProperty(
        default="", index=True,
        help_text="External reference ID from the source system (e.g. Doxygen).",
    )

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("path",)

    # --- File metadata ---
    qualified_name = StringProperty(
        default="", index=True,
        help_text="Qualified name for display/serialization. Mirrors path for files.",
    )
    path = StringProperty(default="")
    language = StringProperty(default="")
    tags = ArrayProperty(StringProperty(), default=[])
    kind = StringProperty(default="file")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "path", "source"}

    # --- Relationships ---
    #  • INCLUDES — this file → other FileNode (#include)
    includes = RelationshipTo('codegraph.models.file.FileNode', 'INCLUDES')

    def markdown_is_heading(self) -> bool:
        """FileNode renders as a note — no heading."""
        return False

    def _compute_qualified_name(self) -> str:
        """Files use ``path`` as their qualified name."""
        return self.path or self.name or ""
