"""MemoryNode — abstract mixin for all memory node types.

Provides shared fields (content, decided_at, updated_at, confidence,
doc_embedding) and common infrastructure for memory nodes.

Inherits from codegraph's CodeGraphNode so that memory nodes participate
in the same backend, tag system, serialization/deserialization pipeline,
and _registry.

Concrete subclasses (DecisionNode, ConstraintNode, etc.) set
``__abstract__ = False`` to override the inherited ``__abstract__ = True``
from this class, making them instantiable node types.
"""

from __future__ import annotations

from codegraph.models.descriptors import (
    DateTimeProperty,
    Property,
    )

from codegraph.models.tags import CodeGraphNode


class MemoryNode(CodeGraphNode):
    """Abstract mixin for memory node types.

    Subclasses MUST set:
      - ``__abstract__ = False`` (override inherited True)
      - ``_llm_fields``: set of field names for LLM serialization
      - ``_identity_fields``: tuple of field names for deterministic UID
      - ``_markdown_keyword``: capitalized heading keyword for markdown export
    """

    __abstract__ = True

    # ── Identity (same pattern as CompoundNode/MemberNode) ─────────
    qualified_name = Property(
        str,
        default="",
        index=True,
        help_text="Human-readable fully-qualified name (e.g. 'memory::db-choice'). "
                  "Indexed for lookup; the unique key is `uid`.",
    )

    # ── Provenance tags (same as CompoundNode/MemberNode) ──────────
    tags = Property(
        list,
        default=list,
        help_text="Provenance tags: 'design', 'as-built', or both. "
                  "Tracks lifecycle: design intent → implementation reality → validation.",
    )

    kind = Property(
        str,
        default="memory",
        help_text="Node category for kind-based queries.",
    )

    # ── Core content ──────────────────────────────────────────────
    content = Property(
        str,
        required=True,
        help_text="Free-text body of the memory (rationale, decision, constraint, etc.)",
    )

    # ── Temporal ──────────────────────────────────────────────────
    decided_at = DateTimeProperty(
        help_text="When this memory was first recorded",
    )
    updated_at = DateTimeProperty(
        help_text="Last mutation timestamp",
    )

    # ── Confidence ────────────────────────────────────────────────
    confidence = Property(
        float,
        default=1.0,
        help_text="0.0–1.0, how certain this memory is. "
                  "Low-confidence memories are de-emphasized by agents.",
    )

    # ── Vector embedding ──────────────────────────────────────────
    doc_embedding = Property(
        list,
        default=list,
        help_text="1536-dim embedding vector for semantic search "
                  "(reuses codegraph's vector infrastructure)",
    )

    # ── Default LLM fields (subclasses extend these) ──────────────
    _llm_fields: set[str] = {
        "name",
        "qualified_name",
        "content",
        "tags",
        "confidence",
        "source",
        "decided_at",
        "updated_at",
    }

    # ── Identity: UID derived from qualified_name only (stable) ───
    _identity_fields: tuple[str, ...] = ("qualified_name",)

    # ── __init_subclass__: re-inject save with timestamp logic ─────
    # CodeGraphNode.__init_subclass__ injects CodeGraphNode._save as
    # cls.save on every concrete subclass.  We override it here with
    # our own version that adds timestamp management.
    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # Skip abstract subclasses
        if getattr(cls, "__abstract__", False):
            return
        # Re-inject our save to override CodeGraphNode._save
        cls.save = MemoryNode._memory_save

    @staticmethod
    def _memory_save(self):
        """Save with automatic timestamp management.

        Sets decided_at on first save and updated_at on every save,
        then delegates to CodeGraphNode._save for UID computation and
        backend persistence.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        if not self.decided_at:
            self.decided_at = now
        self.updated_at = now
        if not self.source or self.source == "unknown":
            self.source = "memory"
        return CodeGraphNode._save(self)

    # ── Edge serialization ──────────────────────────────────────────
    # All edge traversal goes through the backend; no neomodel
    # relationship managers are used by pure-Python memory nodes.
    def serialize_edges(self) -> list[dict]:
        """Return all edges from this node as a flat list of relationship dicts.

        Delegates to the backend's edge traversal, which handles both
        neomodel and pure-Python node types.
        """
        from codegraph.backends import get_backend

        backend = get_backend()
        if not hasattr(self, "element_id_property"):
            return []
        edges: list[dict] = []
        for e in backend.get_all_edges(self):
            edges.append({
                "relation_type": e.relation_type,
                "target_key": e.target_key,
                "target_type": e.target_type,
            })
        return edges