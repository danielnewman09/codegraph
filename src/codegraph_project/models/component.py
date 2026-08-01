"""Component node model (:Component label in Neo4j).

Migrated from the ticketing system's ``backend_migrated.models.component``.

Represents a logical subsystem or module of a project (e.g.,
"backend calculation engine", "frontend UI"). Connects to code-level
nodes via GROUPS relationships to indicate which code belongs to
which project component. Extends CodeGraphNode to share serialization,
registry, and relationship introspection infrastructure.
"""

from codegraph.models.descriptors import Property, Relationship
from codegraph.models.tags import CodeGraphNode


class Component(CodeGraphNode):
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
        uid: Auto-generated unique identifier, computed from identity fields.
            Inherited from CodeGraphNode. Convention: use a hierarchical
            path like 'backend::calculation_engine'.
        source: Project name, inherited from CodeGraphNode.
        description: Human-readable description of the component.
        namespace: Code-level namespace this component maps to
            (e.g. 'calculation_engine::').
    """

    # --- Description ---
    kind = Property(str, default="component")
    description = Property(str, default="")
    qualified_name = Property(
        str, default="", index=True,
        help_text="Qualified name for display/serialization. Mirrors name for components.",
    )
    namespace = Property(str, default="",
        help_text="Code-level namespace this component maps to "
                  "(e.g. 'calculation_engine::').")

    # --- Workflow tags ---
    tags = Property(list, default=list,
        help_text="Workflow tags: 'declared', 'scaffolded', 'passing', 'failing'.")

    # --------------------------------------------------------------------
    # Relationships
    # --------------------------------------------------------------------

    # Self-referential hierarchy
    children = Relationship('COMPOSES', direction='OUTGOING',
                            target_class='codegraph_project.models.component.Component')
    parent = Relationship('COMPOSES', direction='INCOMING',
                          target_class='codegraph_project.models.component.Component')

    # Language
    language = Relationship('WRITTEN_IN', direction='OUTGOING',
                            target_class='codegraph_project.models.language.Language')

    # Dependencies
    dependencies = Relationship('DEPENDS_ON', direction='OUTGOING',
                                target_class='codegraph_project.models.dependency.Dependency')

    # Code-level connections
    namespaces = Relationship('GROUPS', direction='OUTGOING',
                              target_class='codegraph.models.namespace.NamespaceNode')
    classes = Relationship('GROUPS', direction='OUTGOING',
                           target_class='codegraph.models.compound.ClassNode')

    # Requirements
    requirements = Relationship('COMPOSES', direction='OUTGOING',
                                target_class='codegraph_requirements.models.requirement.HLR')

    # Project membership
    project = Relationship('COMPOSES', direction='INCOMING',
                           target_class='codegraph_project.models.project.ProjectMeta')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "qualified_name", "name", "description", "namespace", "tags",
    }

    _markdown_keyword = "Component"

    def markdown_body_type(self) -> str | None:
        """Component has no method/attribute body section."""
        return None
