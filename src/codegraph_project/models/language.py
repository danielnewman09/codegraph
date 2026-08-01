"""Language node model (:Language label in Neo4j).

Migrated from the ticketing system's ``backend_migrated.models.language``.

Represents a programming language (e.g., C++ 20, Python 3.12)
used by components in the project. Extends CodeGraphNode to share
serialization, registry, and relationship introspection infrastructure.
"""

from codegraph.models.descriptors import Property, Relationship
from codegraph.models.tags import CodeGraphNode


class Language(CodeGraphNode):
    """Programming language node — :Language label in Neo4j.

    Represents a programming language (e.g., C++ 20, Python 3.12)
    used by components in the project.

    Attributes:
        name: Language name (e.g. 'C++', 'Python'), inherited from CodeGraphNode.
        uid: Auto-generated unique identifier, computed from identity fields.
            Inherited from CodeGraphNode. Convention: language short name
            (e.g. 'python', 'cpp-20').
        source: Project name, inherited from CodeGraphNode.
        version: Language version string (e.g. '20', '3.12'). Empty if
            unspecified.
    """

    # --- Language-specific ---
    kind = Property(str, default="language")
    qualified_name = Property(
        str, default="", index=True,
        help_text="Qualified name for display/serialization. Mirrors name.",
    )
    version = Property(str, default="",
        help_text="Language version (e.g. '20', '3.12'). Empty if unspecified.")

    # --- Workflow tags ---
    tags = Property(list, default=list,
        help_text="Workflow tags: 'detected', 'configured'.")

    # --- Reverse relationships -------------------------------------------------
    components = Relationship('WRITTEN_IN', direction='INCOMING',
                              target_class='codegraph_project.models.component.Component')

    # --- Serialization contract ---
    _llm_fields: set[str] = {"name", "version", "tags"}
