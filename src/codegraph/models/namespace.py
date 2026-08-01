"""Namespace node model (:Namespace label in Neo4j)."""

from codegraph.models.descriptors import (
    Property,
    Relationship,
    UniqueId,
)

from codegraph.models.tags import CodeGraphNode


class NamespaceNode(CodeGraphNode):
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

    qualified_name = Property(
        str, default="", index=True,
        help_text="Human-readable fully-qualified name. Indexed for lookup; "
                  "the unique key is `uid`.",
    )
    uid = UniqueId()
    kind = Property(str, default="namespace")
    tags = Property(list, default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency'.")
    component_id = Property(int)
    description = Property(str, default="")

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "name", "kind", "tags", "description"}

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # ── COMPOSES relationships ────────────────────────────────────
    classes = Relationship('COMPOSES', direction='OUTGOING',
                           target_class='codegraph.models.compound.ClassNode')
    interfaces = Relationship('COMPOSES', direction='OUTGOING',
                              target_class='codegraph.models.compound.InterfaceNode')
    enums = Relationship('COMPOSES', direction='OUTGOING',
                         target_class='codegraph.models.compound.EnumNode')
    unions = Relationship('COMPOSES', direction='OUTGOING',
                          target_class='codegraph.models.compound.UnionNode')
    concepts = Relationship('COMPOSES', direction='OUTGOING',
                            target_class='codegraph.models.compound.ConceptNode')
    modules = Relationship('COMPOSES', direction='OUTGOING',
                           target_class='codegraph.models.compound.ModuleNode')
    functions = Relationship('COMPOSES', direction='OUTGOING',
                             target_class='codegraph.models.member.FunctionNode')
    defines = Relationship('COMPOSES', direction='OUTGOING',
                           target_class='codegraph.models.member.DefineNode')
    namespaces = Relationship('COMPOSES', direction='OUTGOING', target_class='NamespaceNode')
    parent_namespace = Relationship('COMPOSES', direction='INCOMING', target_class='NamespaceNode')

    tests       = Relationship('COMPOSES', direction='OUTGOING',
                               target_class='codegraph.models.test.TestNode')
