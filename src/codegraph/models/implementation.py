"""Implementation node model — :Implementation label in Neo4j.

Stores the full source code body and its vector embedding separately
from the parent method/function/compound node, so that lightweight
queries do not pull large text or embedding data.

Connected via HAS_IMPLEMENTATION from MethodNode, FunctionNode,
DefineNode, and CompoundNode types.
"""

from __future__ import annotations

from codegraph.models.descriptors import (
    Property,
    UniqueId,
)

from codegraph.models.tags import CodeGraphNode


class ImplementationNode(CodeGraphNode):
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
    uid = UniqueId()
    qualified_name = Property(
        str, default="", index=True,
        help_text="Human-readable identifier matching the parent node's "
                  "qualified_name.",
    )
    kind = Property(str, default="implementation")

    # --- Identity fields for uid computation ---
    # ``kind`` disambiguates from node types that share the parent's
    # qualified_name (e.g. TestStepNode — an implementation of a step
    # has the same qname as the step).  Neo4j tolerates same-uid
    # different-label nodes, but the sqlite backend keys on uid, so the
    # identity must be unique across types.
    _identity_fields: tuple[str, ...] = ("qualified_name", "kind")

    # --- Source code ---
    implementation = Property(
        str, default="",
        help_text="Full source code body of the method/function.",
    )

    # --- Embeddings ---
    impl_embedding = Property(list, default=[],
        help_text="Vector embedding of the implementation source code.")
    tags = Property(list, default=[])

    # --- Serialization contract ---
    _llm_fields: set[str] = {"qualified_name", "kind", "implementation"}