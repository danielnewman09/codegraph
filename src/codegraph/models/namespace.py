"""Namespace node model (:Namespace label in Neo4j)."""

from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, ArrayProperty,
    UniqueIdProperty, RelationshipTo, RelationshipFrom,
)

from codegraph.models.tags import CodeGraphNode


class NamespaceNode(StructuredNode, CodeGraphNode):
    """A namespace entity — namespace, package, or module.

    Attributes:
        qualified_name: Human-readable fully-qualified name (indexed).
        uid: Deterministic SHA-1 hash — the cross-codebase-stable unique key.
        kind: Namespace kind (defaults to "namespace").
        tags: Provenance tags (e.g. ["design"], ["as-built"]).
            Multiple tags allowed.
        component_id: Component identifier for grouping.
        description: Human-readable description of the namespace.
    """

    qualified_name = StringProperty(
        default="", index=True,
        help_text="Human-readable fully-qualified name. Indexed for lookup; "
                  "the unique key is `uid`.",
    )
    uid = UniqueIdProperty()
    kind = StringProperty(default="namespace")
    tags = ArrayProperty(StringProperty(), default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency'.")
    component_id = IntegerProperty()
    description = StringProperty(default="")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "name", "kind", "tags", "description"}

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # ── COMPOSES relationships ────────────────────────────────────
    classes = RelationshipTo('codegraph.models.compound.ClassNode', 'COMPOSES')
    interfaces = RelationshipTo('codegraph.models.compound.InterfaceNode', 'COMPOSES')
    enums = RelationshipTo('codegraph.models.compound.EnumNode', 'COMPOSES')
    unions = RelationshipTo('codegraph.models.compound.UnionNode', 'COMPOSES')
    concepts = RelationshipTo('codegraph.models.compound.ConceptNode', 'COMPOSES')
    modules = RelationshipTo('codegraph.models.compound.ModuleNode', 'COMPOSES')
    functions = RelationshipTo('codegraph.models.member.FunctionNode', 'COMPOSES')
    defines = RelationshipTo('codegraph.models.member.DefineNode', 'COMPOSES')
    namespaces = RelationshipTo('NamespaceNode', 'COMPOSES')
    parent_namespace = RelationshipFrom('NamespaceNode', 'COMPOSES')

    tests       = RelationshipTo('codegraph.models.test.TestNode', 'COMPOSES')
