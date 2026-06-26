"""Dependency node model (:Dependency label in Neo4j).

Migrated from the ticketing system's ``backend_migrated.models.dependency``.

Represents a third-party library that components depend on
(e.g., boost::asio 1.82, requests 2.31). Extends CodeGraphNode to share
serialization, registry, and relationship introspection infrastructure.
"""

from neomodel import (
    StructuredNode, StringProperty, BooleanProperty, ArrayProperty,
    RelationshipFrom,
)

from codegraph.models.tags import CodeGraphNode


class Dependency(StructuredNode, CodeGraphNode):
    """External library dependency node — :Dependency label in Neo4j.

    Represents a third-party library that components depend on
    (e.g., boost::asio 1.82, requests 2.31). Linked to components
    via DEPENDS_ON relationships.

    Attributes:
        name: Dependency name (e.g. 'boost', 'requests'), inherited from
            CodeGraphNode.
        refid: Unique identifier, inherited from CodeGraphNode. Convention:
            '{manager_name}::{name}' (e.g. 'conan::boost', 'pip::requests').
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
    version = StringProperty(default="",
        help_text="Pinned version string (e.g. '1.82.0', '2.31.0').")
    github_url = StringProperty(default="",
        help_text="Repository URL for the dependency.")
    is_dev = BooleanProperty(default=False,
        help_text="True if this is a dev-only dependency (not shipped in production).")

    # --- Manager linkage ---
    manager_name = StringProperty(default="",
        help_text="Name of the package manager (e.g. 'pip', 'conan', 'npm').")

    # --- Doxygen indexing config ---
    index_file_patterns = StringProperty(default="*.h *.hpp",
        help_text="File glob patterns for Doxygen indexing.")
    index_subdir = StringProperty(default="",
        help_text="Subdirectory within the dependency to index.")
    index_exclude_patterns = StringProperty(default="",
        help_text="File patterns to exclude from indexing.")
    index_recursive = BooleanProperty(default=True,
        help_text="Whether to index recursively.")

    # --- Workflow tags ---
    tags = ArrayProperty(StringProperty(), default=list,
        help_text="Workflow tags: 'registered', 'missing', 'integrated', "
                  "'indexed', 'passing', 'failing'.")

    # --- Reverse relationships -------------------------------------------------
    components = RelationshipFrom(
        'codegraph_project.models.component.Component', 'DEPENDS_ON')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "name", "version", "manager_name", "github_url", "is_dev", "tags",
    }
