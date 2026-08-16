"""File node model (:File label in Neo4j).

FileNode is the target of ``DEFINED_IN`` relationships from compounds
(ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode) and members
(MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode).

    (any compound|member)-[:DEFINED_IN]->(FileNode)
"""

from codegraph.models.descriptors import (
    Property,
    Relationship,
    UniqueId,
)

from codegraph.models.tags import CodeGraphNode


class FileNode(CodeGraphNode):
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
        include_guard: Exact macro used by a C/C++ header's conventional
            ``#ifndef`` / ``#define`` guard. Empty for files without one.
        include_directives: Ordered include spellings as written after
            ``#include`` (for example ``<vector>`` or ``"widget.hpp"``).
            An empty string is an explicit group separator.
        start_line: First line of the inclusive owned source span (1).
        end_line: Last line of the inclusive owned source span (line count).
        namespace_leading_blank_lines: Blank lines between a top-level C++
            namespace open and its first definition.
        namespace_trailing_blank_lines: Blank lines between the final
            definition and the corresponding namespace close.
        guard_leading_blank_lines: Blank lines between the final declaration
            or namespace close and a closing ``#endif``.
        source: Name of the project this file belongs to
            (e.g. ``"codegraph"``, ``"llvm"``). Inherited from CodeGraphNode.
    """

    # --- Identity ---
    uid = UniqueId()
    refid = Property(
        str, default="", index=True,
        help_text="External reference ID from the source system (e.g. Doxygen).",
    )

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("path",)

    # --- File metadata ---
    qualified_name = Property(
        str, default="", index=True,
        help_text="Qualified name for display/serialization. Mirrors path for files.",
    )
    path = Property(str, default="")
    language = Property(str, default="")
    include_guard = Property(str, default="")
    include_directives = Property(list, default=[])
    namespace_leading_blank_lines = Property(int, default=0)
    namespace_trailing_blank_lines = Property(int, default=0)
    guard_leading_blank_lines = Property(int, default=0)
    start_line = Property(
        int, default=0,
        help_text="First line of the inclusive source span this file owns "
                  "(always 1 for a read file), 1-based.",
    )
    end_line = Property(
        int, default=0,
        help_text="Last line of the inclusive source span this file owns "
                  "(total line count), 1-based. 0 when the file is unreadable.",
    )
    tags = Property(list, default=[])
    kind = Property(str, default="file")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "path", "source"}

    # --- Relationships ---
    #  • INCLUDES — this file → other FileNode (#include)
    includes = Relationship('INCLUDES', direction='OUTGOING',
                            target_class='codegraph.models.file.FileNode')

    def markdown_is_heading(self) -> bool:
        """FileNode renders as a note — no heading."""
        return False

    def _compute_qualified_name(self) -> str:
        """Files use ``path`` as their qualified name."""
        return self.path or self.name or ""
