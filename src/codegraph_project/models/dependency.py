"""Dependency node model (:Dependency label in Neo4j).

Migrated from the ticketing system's ``backend_migrated.models.dependency``.

Represents a third-party library that components depend on
(e.g., boost::asio 1.82, requests 2.31). Extends CodeGraphNode to share
serialization, registry, and relationship introspection infrastructure.
"""

from codegraph.models.descriptors import Property, Relationship
from codegraph.models.tags import CodeGraphNode


class Dependency(CodeGraphNode):
    """External library dependency node — :Dependency label in Neo4j.

    Represents a third-party library that components depend on
    (e.g., boost::asio 1.82, requests 2.31). Linked to components
    via DEPENDS_ON relationships.

    Attributes:
        name: Dependency name (e.g. 'boost', 'requests'), inherited from
            CodeGraphNode.
        uid: Auto-generated unique identifier, computed from identity fields.
            Inherited from CodeGraphNode. Convention:
            '{manager_name}::{qualified_name}' (e.g. 'conan::boost',
            'pip::requests').
        source: Project name, inherited from CodeGraphNode.
        version: Pinned version string (e.g. '1.82.0', '2.31.0').
        github_url: Repository URL for the dependency.
        is_dev: True if this is a dev-only dependency (not shipped in
            production).
        manager_name: Name of the package manager (e.g. 'pip', 'conan', 'npm').
        index_file_patterns: File glob patterns for Doxygen indexing.
        index_subdir: Subdirectory within the dependency to index.
        index_exclude_patterns: File patterns to exclude from indexing.
        index_recursive: Whether to index recursively.
    """

    # --- Dependency metadata ---
    kind = Property(str, default="dependency")
    qualified_name = Property(
        str, default="", index=True,
        help_text="Qualified name for display/serialization. Mirrors name.",
    )
    version = Property(str, default="",
        help_text="Pinned version string (e.g. '1.82.0', '2.31.0').")
    github_url = Property(str, default="",
        help_text="Repository URL for the dependency.")
    is_dev = Property(bool, default=False,
        help_text="True if this is a dev-only dependency (not shipped in production).")

    # --- Manager linkage ---
    manager_name = Property(str, default="",
        help_text="Name of the package manager (e.g. 'pip', 'conan', 'npm').")

    # --- Doxygen indexing config ---
    index_file_patterns = Property(str, default="*.h *.hpp",
        help_text="File glob patterns for Doxygen indexing.")
    index_subdir = Property(str, default="",
        help_text="Subdirectory within the dependency to index.")
    index_exclude_patterns = Property(str, default="",
        help_text="File patterns to exclude from indexing.")
    index_recursive = Property(bool, default=True,
        help_text="Whether to index recursively.")

    # --- Workflow tags ---
    tags = Property(list, default=list,
        help_text="Workflow tags: 'registered', 'missing', 'integrated', "
                  "'indexed', 'passing', 'failing'.")

    # --- Reverse relationships -------------------------------------------------
    components = Relationship('DEPENDS_ON', direction='INCOMING',
                              target_class='codegraph_project.models.component.Component')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "name", "version", "manager_name", "github_url", "is_dev", "tags",
    }
