"""ProjectMeta node model (:ProjectMeta label in Neo4j).

Migrated from the ticketing system's ``backend_migrated.models.project``.

Singleton node storing project-level settings — name, description, and
working directory. Extends CodeGraphNode to share serialization,
registry, and relationship introspection infrastructure.

The singleton is identified by ``refid = "project"``.
"""

from codegraph.models.descriptors import Property, Relationship
from codegraph.models.tags import CodeGraphNode


class ProjectMeta(CodeGraphNode):
    """Project-level metadata node — :ProjectMeta label in Neo4j.

    Singleton node that stores project-wide settings.  The singleton
    instance is identified by ``refid = "project"``, which serves as
    the unique lookup key.

    ProjectMeta COMPOSES Components — the project owns its top-level
    components in the same way that a Component COMPOSES sub-components
    or HLRs.

    Attributes:
        name: Project name (e.g. 'calculator-engine'), inherited from
            CodeGraphNode.
        refid: Fixed as ``'project'`` — unique lookup key for the
            singleton. Inherited from CodeGraphNode.
        source: Project source identifier, inherited from CodeGraphNode.
        description: Human-readable project description.
        working_directory: Filesystem path where the project lives
            (e.g. '/home/user/dev/calculator-engine').
    """

    # --- Project metadata ---
    kind = Property(str, default="project")
    qualified_name = Property(
        str, default="", index=True,
        help_text="Qualified name for display/serialization. Mirrors name.",
    )
    description = Property(str, default="",
        help_text="Human-readable project description.")
    working_directory = Property(str, default="",
        help_text="Filesystem path where the project lives "
                  "(e.g. '/home/user/dev/calculator-engine').")

    # --- Workflow tags ---
    tags = Property(list, default=list,
        help_text="Workflow tags: 'scaffolded', 'passing', 'failing'.")

    # --- Relationships ----------------------------------------------------
    components = Relationship('COMPOSES', direction='OUTGOING',
                              target_class='codegraph_project.models.component.Component')

    # --- Serialization contract ---
    _llm_fields: set[str] = {
        "name", "description", "working_directory", "tags",
    }

    # ------------------------------------------------------------------
    # Singleton helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_singleton(cls) -> "ProjectMeta":
        """Return the singleton ProjectMeta node, creating it if absent."""
        try:
            node = cls.nodes.get(refid="project")
        except cls.DoesNotExist:
            node = cls(refid="project", name="", description="",
                       working_directory="").save()
        return node

    @classmethod
    def update_singleton(cls, *, name: str = "", description: str = "",
                         working_directory: str = "") -> "ProjectMeta":
        """Update the singleton ProjectMeta node, creating it if absent."""
        node = cls.get_singleton()
        node.name = name
        node.description = description
        node.working_directory = working_directory
        return node.save()
