"""HLR and LLR requirement node models (:HLR / :LLR labels in Neo4j).

High-level requirements (HLRs) and low-level requirements (LLRs) are the
two primary requirement types, migrated from the ticketing system into
codegraph as first-class node types.  Both participate in the
``COMPOSES`` composition hierarchy used by ``LayerGraph``::

    Component -[:COMPOSES]-> HLR -[:COMPOSES]-> LLR -[:COMPOSES]-> TestNode

This mirrors the codegraph pattern where Namespace -[:COMPOSES]->
Class -[:COMPOSES]-> Method, so requirements and code occupy the same
``LayerGraph`` tree.  A ``LayerGraph(layer='design')`` load naturally
includes Components as root entries whose HLR children nest their LLR
children — all rendered by ``layer_graph_to_cytoscape()``.

These models extend ``CodeGraphNode`` to share serialization, registry,
and relationship-introspection infrastructure with the other codegraph
node types.

.. note::

    The ``component`` relationship on HLR references the Component model
    from the ticketing system's ``backend_migrated.models.component`` via
    dotted string.  This is intentional: Component is a project-management
    concept that the ticketing system owns, and the HLR model keeps a
    loosely-coupled reference so that both packages can co-exist in a
    combined application.  Raw Cypher queries and ``LayerGraph`` traversal
    work regardless — the string reference only affects neomodel's
    typed-relationship managers.

Identity
~~~~~~~~
HLR and LLR use a deterministic ``uid`` computed from ``name`` (the
requirement identifier like ``"AG-LLR-01 — ..."``) — the same SHA-1
hashing pattern used by ClassNode, TestNode, and other CodeGraphNode
subclasses.  ``uid`` is the ``UniqueIdProperty`` enforced by Neo4j,
so the same requirement text produces the same ``uid`` across databases
and re-ingesting the same requirement name updates the existing node
rather than duplicating it.  The legacy ``refid`` auto-generated UUID
has been removed.

This matches the identity contract documented in ``CodeGraphNode``:
``_identity_fields`` → ``_compute_uid()`` → ``uid``.

LayerGraph integration
~~~~~~~~~~~~~~~~~~~~~~
Because HLR/LLR extend ``CodeGraphNode`` and define a ``tags`` property,
they are automatically included when ``LayerGraph.from_neo4j(layer)``
or ``GraphRepository.get_by_layer(layer)`` is called.  In a "design"
layer graph, an HLR whose Component is also in the graph appears as a
child of that Component's ``CompositeEntry``; otherwise the HLR is a
root entry.  The ``COMPOSES`` edges between HLR and LLR create the
nested structure that ``layer_graph_to_cytoscape()`` renders.
    Composite HLRs (tagged ``"composite"``) nest child HLRs via the
    same ``COMPOSES`` edge, extending the hierarchy upward:
    ``CompositeHLR → HLR → LLR → TestNode``.

NOTE: Before creating or querying nodes, neomodel's database connection
must be configured (by importing ``codegraph.config`` or calling
``codegraph.persistence.connection.init_neo4j()``).
"""

from neomodel import (
    ArrayProperty,
    StructuredNode,
    StringProperty,
    UniqueIdProperty,
    RelationshipTo,
    RelationshipFrom,
)

from codegraph.models.tags import CodeGraphNode

# ══════════════════════════════════════════════════════════════════════════
# HLR — High-Level Requirement
# ══════════════════════════════════════════════════════════════════════════


class HLR(StructuredNode, CodeGraphNode):
    """High-level requirement node — :HLR label in Neo4j.

    An HLR captures a top-level system requirement.  It composes into
    one or more :LLR nodes via ``COMPOSES`` edges and may belong to a
    :Component via ``COMPOSES`` (incoming).

    The ``COMPOSES`` edge is the same relationship type used by
    NamespaceNode → ClassNode → MethodNode in the codegraph layer.
    This means HLRs and LLRs participate in the ``LayerGraph`` nesting
    structure: an HLR is a ``CompositeEntry`` root, and its LLRs are
    nested children — rendered identically to namespace/class/member
    trees by ``layer_graph_to_cytoscape()``.

    Attributes:
        name: Short label for the requirement (inherited from CodeGraphNode).
            Used as the identity field for deterministic uid computation.
        description: Full requirement text.
        tags: Provenance tags — ``["design"]``, ``["as-built"]``, etc.
    """

    # Prevent pytest from collecting this class as a test case
    __test__ = False

    # --- Identity (deterministic uid from qualified_name) ------------
    _identity_fields: tuple[str, ...] = ("qualified_name",)
    uid = UniqueIdProperty()

    # --- Qualified name ----------------------------------------------------
    # Dot-delimited path derived from the incoming component and parent_hlr
    # relationships, concatenated with ``name``:
    #
    #   component.name + "." + parent_hlr.qualified_name + "." + self.name
    #
    # If no component or parent_hlr, the corresponding segment is omitted.
    # This mirrors how ClassNode uses ``namespace::ClassName`` — HLR/LLR use
    # dot-delimited paths because requirements are not C++ symbols.
    qualified_name = StringProperty(
        default="", index=True,
        help_text="Dot-delimited qualified name derived from component/parent "
                  "relationships and name. Used as the identity field for "
                  "deterministic uid computation.",
    )

    # --- Requirement text -------------------------------------------------------
    description = StringProperty(
        required=True,
        help_text="Full requirement text.",
    )

    # --- Tags & provenance ----------------------------------------------------
    tags = ArrayProperty(
        StringProperty(),
        default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency', 'scaffold'.",
    )

    # --- Relationships ----------------------------------------------------------
    #
    #  • COMPOSES (outgoing) — HLR → LLR
    #    Each HLR composes into one or more low-level requirements.
    #    This is the same COMPOSES edge type used by Namespace →
    #    Class → Method in the codegraph.
    #
    #  • COMPOSES (incoming) — Component → HLR
    #    The project component this requirement belongs to.
    #
    #  • COMPOSES (outgoing) — HLR → CompoundNode
    #    The design-graph nodes (classes, interfaces, enums) that this
    #    requirement composes.
    #
    #  • COMPOSES (outgoing) — HLR → HLR (composite nesting)
    #    A composite/technical HLR composes one or more child HLRs,
    #    creating a multi-level requirement hierarchy:
    #
    #        CompositeHLR -[:COMPOSES]-> HLR -[:COMPOSES]-> LLR -[:COMPOSES]-> TestNode
    #
    #    Composite HLRs carry the ``"composite"`` tag to distinguish
    #    them from per-compound HLRs.  The LayerGraph system renders
    #    these as nested CompositeEntry trees, the same way it renders
    #    Namespace → Class → Method nesting.
    #
    #  • COMPOSES (incoming) — HLR → HLR (parent composite)
    #    The parent composite HLR that this HLR is nested under, if any.
    # --------------------------------------------------------------------------

    llrs = RelationshipTo(
        "codegraph_requirements.models.requirement.LLR", "COMPOSES"
    )
    component = RelationshipFrom(
        "codegraph_project.models.component.Component", "COMPOSES"
    )
    design_compounds = RelationshipTo(
        "codegraph.models.compound.CompoundNode", "COMPOSES"
    )
    # Composite HLR nesting: a composite HLR owns child HLRs
    sub_hlrs = RelationshipTo(
        "codegraph_requirements.models.requirement.HLR", "COMPOSES"
    )
    parent_hlr = RelationshipFrom(
        "codegraph_requirements.models.requirement.HLR", "COMPOSES"
    )

    #  • DEPENDS_ON (outgoing) — HLR → HLR
    #    This HLR's functionality relies on the depended-on HLR being
    #    satisfied.  Distinct from COMPOSES (which expresses parent-child
    #    decomposition, not dependency).  Enables dependency-aware design
    #    ordering, impact analysis, and context assembly.
    depends_on_hlrs = RelationshipTo(
        "codegraph_requirements.models.requirement.HLR", "DEPENDS_ON"
    )
    #  • DEPENDS_ON (incoming) — HLR → HLR
    #    Other HLRs that depend on this one.  Used for reverse traversal
    #    (impact analysis: "who depends on this HLR?").
    depended_on_by_hlrs = RelationshipFrom(
        "codegraph_requirements.models.requirement.HLR", "DEPENDS_ON"
    )

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "name", "description", "tags"}

    _markdown_keyword = "HLR"

    def markdown_body_type(self) -> str | None:
        """HLR has no method/attribute body section."""
        return None

    @classmethod
    def from_llm_dict(cls, data: dict) -> "HLR":
        """Construct an HLR from an LLM tool-call dict.

        The LLM returns HLR data without ``layer`` or ``name`` —
        those are filled with design-time defaults.
        ``uid`` is computed deterministically from ``qualified_name`` on save.
        If ``qualified_name`` is not provided, it defaults to ``name``.

        Args:
            data: Raw HLR dict from the LLM.  Typically just
                ``{"description": "..."}``.

        Returns:
            An HLR instance ready for persistence.
        """
        normalised = dict(data)
        normalised.setdefault("name", "")
        normalised.setdefault("tags", ["design"])
        # If qualified_name not provided, derive from name
        if not normalised.get("qualified_name"):
            normalised["qualified_name"] = normalised.get("name", "")
        normalised.pop("refid", None)
        normalised.pop("source", None)
        normalised.pop("type", None)
        normalised.pop("edges", None)
        normalised.pop("layer", None)  # legacy field, replaced by tags
        return cls(**normalised)

    def format(self, include_component: bool = False, component_name: str = "") -> str:
        """Format this HLR as a human-readable line for agent prompts.

        Args:
            include_component: Whether to include component name.
            component_name: Component name to include (if provided).

        Returns:
            Formatted string like ``"HLR The system shall..."``.
        """
        comp = f" [Component: {component_name}]" if include_component and component_name else ""
        return f"HLR{comp}: {self.description}"


# ══════════════════════════════════════════════════════════════════════════
# LLR — Low-Level Requirement
# ══════════════════════════════════════════════════════════════════════════


class LLR(StructuredNode, CodeGraphNode):
    """Low-level requirement node — :LLR label in Neo4j.

    An LLR is a concrete, testable requirement derived from an HLR.
    Connected to its parent HLR via an incoming ``COMPOSES`` edge (the
    same edge type used for Namespace → Class in the codegraph layer).

    Component membership is inferred transitively through the parent
    HLR's ``COMPOSES`` relationship — LLR does not carry its own
    ``BELONGS_TO`` edge.

    Attributes:
        name: Short label for the requirement (inherited from CodeGraphNode).
            Used as the identity field for deterministic uid computation.
        description: Full requirement text.
        tags: Provenance tags — ``["design"]``, ``["as-built"]``, etc.
    """

    # Prevent pytest from collecting this class as a test case
    __test__ = False

    # --- Identity (deterministic uid from qualified_name) ------------
    _identity_fields: tuple[str, ...] = ("qualified_name",)
    uid = UniqueIdProperty()

    # --- Qualified name ----------------------------------------------------
    # Dot-delimited path derived from the parent HLR's qualified_name
    # concatenated with ``name``:
    #
    #   hlr.qualified_name + "." + self.name
    #
    # If no parent HLR is connected, falls back to just ``name``.
    qualified_name = StringProperty(
        default="", index=True,
        help_text="Dot-delimited qualified name derived from parent HLR "
                  "and name. Used as the identity field for deterministic "
                  "uid computation.",
    )

    # --- Requirement text -------------------------------------------------------
    description = StringProperty(
        required=True,
        help_text="Full requirement text.",
    )

    # --- Tags & provenance ----------------------------------------------------
    tags = ArrayProperty(
        StringProperty(),
        default=list,
        help_text="Provenance tags: 'design', 'as-built', 'dependency', 'scaffold'.",
    )

    # --- Relationships ----------------------------------------------------------
    #
    #  • COMPOSES (incoming) — HLR → LLR
    #    The parent high-level requirement.
    #
    #  • COMPOSES (outgoing) — LLR → TestNode
    #    An LLR composes its test nodes (verification methods).
    #
    #  • COMPOSES (outgoing) — LLR → CompoundNode
    #    Design nodes composed by this LLR.
    # --------------------------------------------------------------------------

    hlr = RelationshipFrom(
        "codegraph_requirements.models.requirement.HLR", "COMPOSES"
    )
    verification_methods = RelationshipTo(
        "codegraph.models.test.TestNode", "COMPOSES"
    )
    design_compounds = RelationshipTo(
        "codegraph.models.compound.CompoundNode", "COMPOSES"
    )

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "name", "description", "tags"}

    _markdown_keyword = "LLR"

    def markdown_body_type(self) -> str | None:
        """LLR has no method/attribute body section."""
        return None

    @classmethod
    def from_llm_dict(cls, data: dict) -> "LLR":
        """Construct an LLR from an LLM tool-call dict.

        The LLM returns LLR data without ``name`` or ``tags`` —
        those are filled with design-time defaults.
        ``uid`` is computed deterministically from ``qualified_name`` on save.
        If ``qualified_name`` is not provided, it defaults to ``name``.

        Args:
            data: Raw LLR dict from the LLM.  Typically
                ``{"description": "..."}``.

        Returns:
            An LLR instance ready for persistence.
        """
        normalised = dict(data)
        normalised.setdefault("name", "")
        normalised.setdefault("tags", ["design"])
        # If qualified_name not provided, derive from name
        if not normalised.get("qualified_name"):
            normalised["qualified_name"] = normalised.get("name", "")
        normalised.pop("refid", None)
        normalised.pop("source", None)
        normalised.pop("type", None)
        normalised.pop("edges", None)
        normalised.pop("layer", None)  # legacy field, replaced by tags
        normalised.pop("component_id", None)  # not a neomodel property on LLR
        return cls(**normalised)

    def format(self, hlr_id: str = "", verifications: list | None = None) -> str:
        """Format this LLR (and optional verifications) for agent prompts.

        Args:
            hlr_id: Optional HLR identifier for the prefix line.
            verifications: List of ``(TestNode, assertions, steps)``
                tuples as returned by verification loading helpers.

        Returns:
            Multi-line formatted string.
        """
        prefix = f"LLR {hlr_id}: " if hlr_id else "LLR: "
        lines = [f"{prefix}{self.description}"]
        if verifications:
            lines.append("  Verifications:")
            for test_node, assertions, steps in verifications:
                lines.append(
                    test_node.format(conditions=assertions, actions=steps)
                )
        else:
            lines.append("  (No verification stubs)")
        lines.append("")
        return "\n".join(lines)
