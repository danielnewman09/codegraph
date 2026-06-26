"""Component node model (:Component label in Neo4j).

Migrated from the ticketing system's ``backend_migrated.models.component``.

Represents a logical subsystem or module of a project (e.g.,
"backend calculation engine", "frontend UI"). Connects to code-level
nodes via GROUPS relationships to indicate which code belongs to
which project component. Extends CodeGraphNode to share serialization,
registry, and relationship introspection infrastructure.
"""

from neomodel import (
    StructuredNode, StringProperty, ArrayProperty,
    RelationshipTo, RelationshipFrom,
)

from codegraph.models.tags import CodeGraphNode


class Component(StructuredNode, CodeGraphNode):
    """Project-management grouping node — :Component label in Neo4j.

    Represents a logical subsystem or module of a project (e.g.,
    "backend calculation engine", "frontend UI"). Connects to code-level
    nodes via GROUPS relationships to indicate which code belongs to
    which project component.

    Components form a self-referential hierarchy via COMPOSES edges
    (the same edge type used by HLR → LLR and Namespace → Class),
    linking to languages via WRITTEN_IN, dependencies via DEPENDS_ON,
    requirements via COMPOSES, and code-level namespaces/classes via GROUPS.

    Attributes:
        name: Short name of the component (e.g. 'calculation_engine'),
            inherited from CodeGraphNode.
        refid: Unique identifier, inherited from CodeGraphNode. Serves
            as the primary lookup key. Convention: use a hierarchical
            path like 'backend::calculation_engine'.
        source: Project name, inherited from CodeGraphNode.
        description: Human-readable description of the component.
        namespace: Code-level namespace this component maps to
            (e.g. 'calculation_engine::').
    """

    # --- Description ---
    description = StringProperty(default="")
    namespace = StringProperty(default="",
        help_text="Code-level namespace this component maps to "
                  "(e.g. 'calculation_engine::').")

    # --- Workflow tags ---
    tags = ArrayProperty(StringProperty(), default=list,
        help_text="Workflow tags: 'declared', 'scaffolded', 'passing', 'failing'.")

    # --------------------------------------------------------------------
    # Relationships
    # --------------------------------------------------------------------

    # Self-referential hierarchy
    children = RelationshipTo(
        'codegraph_project.models.component.Component', 'COMPOSES')
    parent = RelationshipFrom(
        'codegraph_project.models.component.Component', 'COMPOSES')

    # Language
    language = RelationshipTo(
        'codegraph_project.models.language.Language', 'WRITTEN_IN')

    # Dependencies
    dependencies = RelationshipTo(
        'codegraph_project.models.dependency.Dependency', 'DEPENDS_ON')

    # Code-level connections
    namespaces = RelationshipTo(
        'codegraph.models.namespace.NamespaceNode', 'GROUPS')
    classes = RelationshipTo(
        'codegraph.models.compound.ClassNode', 'GROUPS')

    # Requirements
    requirements = RelationshipTo(
        'codegraph_requirements.models.requirement.HLR', 'COMPOSES')

    # Project membership
    project = RelationshipFrom(
        'codegraph_project.models.project.ProjectMeta', 'COMPOSES')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "name", "description", "namespace", "tags",
    }
