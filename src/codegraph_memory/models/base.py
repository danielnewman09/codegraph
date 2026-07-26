"""MemoryNode — abstract mixin for all memory node types.

Provides shared fields (content, decided_at, updated_at, confidence,
doc_embedding) and common infrastructure for memory nodes.

Inherits from codegraph's CodeGraphNode so that memory nodes participate
in the same Neo4j database, tag system, serialization/deserialization
pipeline, and _registry.

Concrete subclasses (DecisionNode, ConstraintNode, etc.) set
``__abstract__ = False`` to override the inherited ``__abstract__ = True``
from this class, making them instantiable neomodel nodes.
"""

from __future__ import annotations

from neomodel import (
    StringProperty,
    DateTimeProperty,
    FloatProperty,
    ArrayProperty,
    UniqueIdProperty,
    StructuredNode,
)

from codegraph.models.tags import CodeGraphNode


class MemoryNode(CodeGraphNode, StructuredNode):
    """Abstract mixin for memory node types.

    Subclasses MUST set:
      - ``__abstract__ = False`` (override inherited True)
      - ``_llm_fields``: set of field names for LLM serialization
      - ``_identity_fields``: tuple of field names for deterministic UID
      - ``_markdown_keyword``: capitalized heading keyword for markdown export
    """

    __abstract__ = True

    # ── Identity (same pattern as CompoundNode/MemberNode) ─────────
    uid = UniqueIdProperty()
    qualified_name = StringProperty(
        default="",
        index=True,
        help_text="Human-readable fully-qualified name (e.g. 'memory::db-choice'). "
                  "Indexed for lookup; the unique key is `uid`.",
    )

    # ── Provenance tags (same as CompoundNode/MemberNode) ──────────
    tags = ArrayProperty(
        StringProperty(),
        default=list,
        help_text="Provenance tags: 'design', 'as-built', or both. "
                  "Tracks lifecycle: design intent → implementation reality → validation.",
    )

    kind = StringProperty(
        default="memory",
        help_text="Node category for kind-based queries.",
    )

    # ── Core content ──────────────────────────────────────────────
    content = StringProperty(
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
    confidence = FloatProperty(
        default=1.0,
        help_text="0.0–1.0, how certain this memory is. "
                  "Low-confidence memories are de-emphasized by agents.",
    )

    # ── Vector embedding ──────────────────────────────────────────
    doc_embedding = ArrayProperty(
        FloatProperty(),
        default=[],
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
    # our own version that adds timestamp management, because
    # neomodel's pre_save hooks don't fire through CodeGraphNode._save's
    # direct call to StructuredNode.save(self).
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
        Neo4j persistence.
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
    # Override serialize_edges to handle relationships that point to
    # CodeGraphNode (which has no __label__).  neomodel's default
    # implementation calls .all() on every relationship manager, which
    # fails for CodeGraphNode targets.  We catch the error and use raw
    # Cypher for those relationships.
    def serialize_edges(self) -> list[dict]:
        """Return all edges from this node as a flat list of relationship dicts.

        Walks every RelationshipTo / RelationshipFrom descriptor on this
        instance.  For relationships targeting CodeGraphNode (which can't
        be traversed via neomodel), uses raw Cypher as a fallback.
        """
        from neomodel import RelationshipTo, RelationshipFrom
        from codegraph.backends import get_backend
        backend = get_backend()

        edges: list[dict] = []
        seen: set[str] = set()
        for klass in type(self).__mro__:
            for name, val in vars(klass).items():
                if not isinstance(val, (RelationshipTo, RelationshipFrom)):
                    continue
                if name in seen:
                    continue
                seen.add(name)

                # Check if target class has __label__ (CodeGraphNode doesn't)
                raw_class = val._raw_class
                target_cls = val.definition.get("node_class")
                has_label = target_cls is not None and hasattr(target_cls, "__label__")

                if has_label:
                    # Standard neomodel traversal
                    try:
                        manager = getattr(self, name)
                        for node in manager.all():
                            edges.append({
                                "relation_type": val.definition["relation_type"],
                                "target_uid": node._uid_value(),
                                "target_type": type(node).__name__,
                            })
                    except Exception:
                        pass
                else:
                    # Raw Cypher fallback for CodeGraphNode targets
                    if not hasattr(self, "element_id_property"):
                        continue
                    rel_type = val.definition["relation_type"]
                    direction = val.definition["direction"].name
                    try:
                        if direction == "OUTGOING":
                            results, _ = backend.execute_raw(
                                f"MATCH (s)-[:{rel_type}]->(t) "
                                f"WHERE elementId(s) = $sid "
                                f"RETURN t.uid AS uid, labels(t) AS labels",
                                {"sid": self.element_id},
                            )
                        else:
                            results, _ = backend.execute_raw(
                                f"MATCH (s)<-[:{rel_type}]-(t) "
                                f"WHERE elementId(s) = $sid "
                                f"RETURN t.uid AS uid, labels(t) AS labels",
                                {"sid": self.element_id},
                            )
                        for row in results:
                            target_uid = row[0]
                            target_labels = row[1] if row[1] else set()
                            # Determine target type from labels — prefer
                            # the most specific (deepest subclass) class
                            target_type = "CodeGraphNode"
                            candidates = []
                            for rname, rcls in CodeGraphNode._registry.items():
                                if getattr(rcls, "__label__", None) in target_labels and not getattr(rcls, "__abstract__", False):
                                    candidates.append(rname)
                            if candidates:
                                # Pick the class with the most MRO depth
                                # (most specific = deepest in hierarchy)
                                target_type = max(candidates, key=lambda n: len(CodeGraphNode._registry[n].__mro__))
                            edges.append({
                                "relation_type": rel_type,
                                "target_uid": target_uid,
                                "target_type": target_type,
                            })
                    except Exception:
                        pass  # best-effort

        return edges