"""Implementation node model — :Implementation label in Neo4j.

Stores the full source code body and its vector embedding separately
from the parent method/function/compound node, so that lightweight
queries do not pull large text or embedding data.

Connected via HAS_IMPLEMENTATION from MethodNode, FunctionNode,
DefineNode, and CompoundNode types.
"""

from __future__ import annotations

from neomodel import (
    StructuredNode, StringProperty, ArrayProperty, FloatProperty,
    UniqueIdProperty,
)

from codegraph.models.tags import CodeGraphNode


class ImplementationNode(StructuredNode, CodeGraphNode):
    """Source code implementation body and its embedding — Neo4j label ``:Implementation``.

    Connected from MethodNode, FunctionNode, DefineNode, or any CompoundNode
    via a HAS_IMPLEMENTATION relationship. The implementation text and its
    vector embedding are kept on a separate node so that:

    - Lightweight queries (listing, counting, ``serialize()``) do not pull
      potentially large source text or embedding vectors.
    - LayerGraph construction skips implementation nodes by design.

    To retrieve implementation data, traverse the relationship explicitly:

        impl_nodes = method.implementation_ref.all()
        if impl_nodes:
            source_code = impl_nodes[0].implementation
            embedding = impl_nodes[0].impl_embedding

    Attributes:
        qualified_name: Human-readable identifier matching the parent
            node's ``qualified_name`` (indexed).
        uid: Deterministic SHA-1 hash — the cross-codebase-stable unique
            key, computed from ``qualified_name``.
        kind: Always "implementation".
        implementation: Full source code body of the method/function.
        impl_embedding: Vector embedding of the implementation source code.
    """

    # --- Identity ---
    uid = UniqueIdProperty()
    qualified_name = StringProperty(
        default="", index=True,
        help_text="Human-readable identifier matching the parent node's "
                  "qualified_name.",
    )
    kind = StringProperty(default="implementation")

    # --- Identity fields for uid computation ---
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # --- Source code ---
    implementation = StringProperty(
        default="",
        help_text="Full source code body of the method/function.",
    )

    # --- Embeddings ---
    impl_embedding = ArrayProperty(FloatProperty(), default=[],
        help_text="Vector embedding of the implementation source code.")
    tags = ArrayProperty(StringProperty(), default=[])

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "kind", "implementation"}