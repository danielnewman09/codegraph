"""LayerGraph — tag-aware graph container for codebase views.

A Python-only container that holds a nested composition structure for
all nodes in a design view. Root entries are keyed by a stable local
identifier.  COMPOSES relationships create nesting; other relationship
types are stored as references.  Supports deserialization from dicts,
persistence to Neo4j, and querying from Neo4j by tag.
"""

from __future__ import annotations

import logging
import json
from dataclasses import dataclass, field
from typing import Iterator

log = logging.getLogger(__name__)

#: Node types that live in separate model packages and are registered
#: lazily (mirrors ``codegraph.export.markdown._LAZY_IMPORTS``).  A
#: serialized design LayerGraph may contain requirements nodes (HLR,
#: LLR) produced by the design pipeline; deserializing them requires
#: the owning package to be imported so its model classes register in
#: ``CodeGraphNode._registry``.
_LAZY_TYPE_IMPORTS: dict[str, str] = {
    "HLR": "codegraph_requirements.models.requirement",
    "LLR": "codegraph_requirements.models.requirement",
    "Component": "codegraph_project.models.component",
}


def _ensure_type_registered(node_type: str) -> None:
    """Import the package that registers *node_type* if not registered.

    Called before deserializing a node so unknown ``type`` values in
    serialized JSON (HLR/LLR/Component) resolve instead of raising
    ``KeyError`` from ``CodeGraphNode.deserialize``.
    """
    if node_type in CodeGraphNode._registry:
        return
    module = _LAZY_TYPE_IMPORTS.get(node_type)
    if module:
        import importlib

        importlib.import_module(module)

from codegraph.backends.interface import Backend
from codegraph.backends import get_backend

from codegraph.constants import Tag, TAGS
from codegraph.identity import (
    CanonicalIdentity,
    KEY_VERSION,
    VERSION_PREFIX,
    parse_key,
)
from codegraph.identity.registry import KeyConflictError
from codegraph.models.tags import CodeGraphNode, _type_discriminator
from codegraph.models.descriptors import PropertyRegistry


#: Current serialized-document format version (WP2.3).  ``LayerGraph``
#: documents may be a bare list of node dicts — the documented legacy
#: form, implicitly format v1 — or a versioned envelope dict:
#: ``{"format_version": 1, "identity_version": 1, "entries": [...]}``.
#: The envelope is how future formats present themselves; unknown
#: versions fail clearly instead of being inferred from field presence.
GRAPH_DOCUMENT_FORMAT_VERSION = 1

_PORTABLE_NODE_FORBIDDEN_FIELDS = frozenset({
    "uid", "refid", "compound_refid", "member_refid", "parent_refid",
    "child_refid", "from_refid", "to_refid",
})
_PORTABLE_EDGE_FORBIDDEN_FIELDS = frozenset({
    "uid", "target_uid", "refid", "from_refid", "to_refid",
})


def _validate_portable_edge_shape(edge: dict, *, context: str = "") -> None:
    """Validate the endpoint shape of one portable relationship.

    A portable edge has either a strict canonical ``target_key`` or an
    explicit ``target_ref``.  The latter is an unresolved extraction result;
    it is not a second spelling of ``target_key`` and must never be marked
    external.  Scope-aware classification is applied later, once the
    selected and complete key sets are known.
    """
    if not isinstance(edge, dict):
        raise GraphDocumentError(
            f"{context}: edge must be an object"
            if context else "edge must be an object"
        )
    forbidden = _PORTABLE_EDGE_FORBIDDEN_FIELDS & set(edge)
    if forbidden:
        raise GraphDocumentError(
            f"{context}: portable edge contains forbidden fields "
            f"{sorted(forbidden)}"
            if context
            else f"portable edge contains forbidden fields {sorted(forbidden)}"
        )
    if not isinstance(edge.get("relation_type"), str) or not edge["relation_type"]:
        raise GraphDocumentError(
            f"{context}: edge is missing relation_type"
            if context else "edge is missing relation_type"
        )
    if not isinstance(edge.get("target_type"), str) or not edge["target_type"]:
        raise GraphDocumentError(
            f"{context}: edge is missing target_type"
            if context else "edge is missing target_type"
        )

    target_key = edge.get("target_key")
    target_ref = edge.get("target_ref")
    if target_key:
        if not isinstance(target_key, str):
            raise GraphDocumentError(
                f"{context}: edge target_key must be a string"
                if context else "edge target_key must be a string"
            )
        try:
            CanonicalIdentity.from_key(target_key)
        except Exception as exc:
            raise GraphDocumentError(
                f"{context}: invalid edge target_key {target_key!r}: {exc}"
                if context
                else f"invalid edge target_key {target_key!r}: {exc}"
            ) from exc
        if target_ref:
            raise GraphDocumentError(
                f"{context}: edge cannot carry both target_key and target_ref"
                if context else "edge cannot carry both target_key and target_ref"
            )
        if edge.get("unresolved") is True:
            raise GraphDocumentError(
                f"{context}: an unresolved edge cannot carry target_key"
                if context else "an unresolved edge cannot carry target_key"
            )
    else:
        if not isinstance(target_ref, str) or not target_ref:
            raise GraphDocumentError(
                f"{context}: edge has no target_key or explicit target_ref"
                if context
                else "edge has no target_key or explicit target_ref"
            )
        if edge.get("external") is True:
            raise GraphDocumentError(
                f"{context}: external requires a valid target_key"
                if context else "external requires a valid target_key"
            )

    for field_name in ("external", "unresolved"):
        if field_name in edge and not isinstance(edge[field_name], bool):
            raise GraphDocumentError(
                f"{context}: edge {field_name} must be boolean"
                if context
                else f"edge {field_name} must be boolean"
            )
    if "diagnostic" in edge and (
        not isinstance(edge["diagnostic"], str) or not edge["diagnostic"].strip()
    ):
        raise GraphDocumentError(
            f"{context}: edge diagnostic must be a non-empty string"
            if context else "edge diagnostic must be a non-empty string"
        )


def _classify_portable_edge(
    edge: dict,
    *,
    selected_keys: set[str],
    complete_keys: set[str],
    context: str = "",
) -> dict:
    """Return one edge in the portable endpoint state for this export."""
    result = dict(edge)
    _validate_portable_edge_shape(result, context=context)
    target_key = result.get("target_key")
    if not target_key:
        result["unresolved"] = True
        result.setdefault(
            "diagnostic",
            "target could not be resolved during graph extraction",
        )
        return result

    if target_key in selected_keys:
        # A target that is present in the document is never external.  Drop
        # stale classification metadata when a graph is re-exported at a
        # wider scope.
        result.pop("external", None)
        result.pop("unresolved", None)
        result.pop("diagnostic", None)
        return result

    if target_key in complete_keys or result.get("external") is True:
        result["external"] = True
        result.pop("unresolved", None)
        result.pop("diagnostic", None)
        return result

    # Keep the original endpoint as human-readable diagnostic data, but do
    # not emit it as target_key: a canonical-looking key that does not
    # resolve is not made legal by an external marker.
    result["target_ref"] = target_key
    result.pop("target_key", None)
    result.pop("external", None)
    result["unresolved"] = True
    result.setdefault(
        "diagnostic",
        "canonical target is absent from the selected and complete graph",
    )
    return result


class GraphDocumentError(ValueError):
    """Raised when a serialized LayerGraph document is malformed or
    declares a format/key version this build does not support.

    Attributes mirror the offending document's declarations so callers
    can distinguish a version problem (``format_version`` set) from a
    structural one (``format_version`` is ``None``).
    """

    def __init__(
        self,
        message: str,
        *,
        format_version: int | None = None,
        identity_version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.format_version = format_version
        self.identity_version = identity_version


def _require_tags(tag: str, nodes) -> None:
    """Raise if any loaded graph node lacks a provenance tag.

    Every persisted node must carry at least one provenance tag from
    ``TAGS`` (design, as-built, dependency, scaffold, requirements,
    test).  An empty ``tags`` list means the node was written without
    tag propagation — surfacing the offenders here pinpoints which
    write path dropped the tag.

    Args:
        tag: The tag the graph was loaded with (for the error message).
        nodes: Iterable of loaded node instances.

    Raises:
        ValueError: If one or more nodes have no tags.
    """
    untagged: list[tuple[str, str, str, str | None]] = []
    for node in nodes:
        if getattr(node, "tags", None):
            continue
        untagged.append(
            (
                type(node).__name__,
                getattr(node, "qualified_name", None)
                or getattr(node, "name", None)
                or "<unnamed>",
                getattr(node, "source", "") or "",
                getattr(node, "uid", None),
            )
        )
    if untagged:
        details = "; ".join(
            f"{cls}({qn}, source={src!r}, uid={uid})"
            for cls, qn, src, uid in untagged[:15]
        )
        more = f" (+{len(untagged) - 15} more)" if len(untagged) > 15 else ""
        raise ValueError(
            f"LayerGraph.from_backend({tag!r}): {len(untagged)} node(s) have "
            f"empty tags — every node must carry a provenance tag from "
            f"{TAGS}. First offenders: {details}{more}"
        )


@dataclass
class CompositeEntry:
    """A node and its composition hierarchy.

    Bundles a ``CodeGraphNode`` with its composed children (COMPOSES
    edges) and non-composition references (all other edge types).

    Attributes:
        node: The CodeGraphNode instance.
        children: Composed children keyed by target type, then by
            target key.  Only COMPOSES edges create entries here.
        references: Non-composition edges from this node.  Each tuple
            is ``(relation_type, target_key, target_type)``.
        edge_attrs: Optional per-edge metadata keyed by
            ``(relation_type, target_key)`` (e.g. the include spelling
            on INCLUDES edges) — carried through serialization and the
            backends so relationship-level information survives.
    """

    node: CodeGraphNode
    children: dict[str, dict[str, "CompositeEntry"]] = field(default_factory=dict)
    references: list[tuple[str, str, str]] = field(default_factory=list)
    edge_attrs: dict[tuple[str, str], dict] = field(default_factory=dict)
    unresolved_edges: list[dict] = field(default_factory=list)

    def serialize(
        self,
        fields: str = "llm",
        *,
        export_implementation: bool = False,
        canonical_by_local: dict[str, str] | None = None,
        selected_keys: set[str] | None = None,
        complete_keys: set[str] | None = None,
    ) -> dict:
        """Recursively serialize this CompositeEntry and its composed children.

        Walks the pre-built ``children`` tree to produce nested output.
        Composed children appear under a ``composes`` key and COMPOSES
        edges are removed from the ``edges`` array.  The node's unique
        identifier property is included in the output when not already
        present, so that roundtrip deserialization can resolve edge
        targets correctly.

        Uses ``CodeGraphNode.serialize()`` for each node's properties
        and edges, then adds the ``composes`` nesting and uid supplement
        on top.

        Args:
            fields: Which property fields to include when serializing
                each node.  ``"llm"`` (default) — only ``_llm_fields``.
                ``"all"`` — every declared property.  Passed through to
                ``CodeGraphNode.serialize()``.
            export_implementation: When True, MethodNode ``body``
                text (implementation bodies captured at parse time) is
                included so codegen can regenerate out-of-line and
                inline definitions.  Default False — implementation
                data is opt-in.
            canonical_by_local: Map of local node key → canonical key
                (``cg:v1:...``); reference edges emit ``target_key`` from
                it (WP B — canonical keys only).
            selected_keys: Keys emitted in this document.  Used to ensure
                an in-document target is never also marked external.
            complete_keys: Keys known to exist in the complete graph.  A
                valid key outside ``selected_keys`` is emitted with
                ``external: true``.

        Returns:
            A dict representing the entry with nested children.
        """
        # Start from the node's own flat serialization.
        # Remove COMPOSES, HAS_IMPLEMENTATION, and TEMPLATE_PARAM edges —
        # COMPOSES is represented by nesting; HAS_IMPLEMENTATION and
        # TEMPLATE_PARAM reference implementation/type-parameter nodes
        # that are intentionally excluded from serialized graph views.
        serialized = self.node.serialize(fields=fields)
        # ``refid`` and the parent-relative Doxygen locators are extraction
        # details, not portable graph properties.  Canonical identity has
        # already been resolved on the node and is the only identity field
        # emitted on the wire.
        for field_name in _PORTABLE_NODE_FORBIDDEN_FIELDS:
            serialized.pop(field_name, None)
        edges = [
            e for e in serialized.get("edges", [])
            if e["relation_type"] not in (
                "COMPOSES", "HAS_IMPLEMENTATION", "TEMPLATE_PARAM"
            )
        ]
        # Include LayerGraph-level references (built during deserialization
        # or graph construction) that aren't represented on the node's
        # neomodel relationship managers.  This is essential for graphs
        # that were deserialized from JSON (e.g. subgraph views) where
        # the node is not connected to Neo4j.
        selected_keys = selected_keys or set()
        complete_keys = complete_keys or set()

        # Relationship attributes captured on the LayerGraph (notably
        # ``external`` and include spelling) must also update edges emitted
        # by the node's backend serializer.
        for edge in edges:
            target_key = edge.get("target_key")
            attrs = self.edge_attrs.get(
                (edge.get("relation_type"), target_key), {}
            )
            if attrs:
                edge.update(attrs)

        seen_targets = {
            (e.get("relation_type"), e.get("target_key") or e.get("target_ref"))
            for e in edges
        }
        for rt, target_key, target_type in self.references:
            if rt in ("COMPOSES", "HAS_IMPLEMENTATION", "TEMPLATE_PARAM"):
                continue
            if (rt, target_key) in seen_targets:
                continue
            seen_targets.add((rt, target_key))
            edge = {
                "relation_type": rt,
                "target_key": target_key,
                "target_type": target_type,
            }
            edge.update(self.edge_attrs.get((rt, target_key), {}))
            edges.append(edge)

        for edge in self.unresolved_edges:
            identity = (
                edge.get("relation_type"),
                edge.get("target_key") or edge.get("target_ref"),
            )
            if identity not in seen_targets:
                edges.append(dict(edge))
                seen_targets.add(identity)

        # Relationship managers and backend queries do not guarantee order.
        # Sort before classification so portable JSON has a stable byte order
        # even when the same graph is loaded through different backends.
        edges.sort(
            key=lambda edge: (
                edge.get("relation_type", ""),
                edge.get("target_key") or edge.get("target_ref") or "",
                edge.get("target_type", "") or "",
                bool(edge.get("external", False)),
                bool(edge.get("unresolved", False)),
                repr(sorted(edge.items())),
            )
        )

        # LayerGraph references normally use canonical/local keys, but
        # importers may retain qualified names until serialization.  Resolve
        # either form to the target node's canonical key before exporting.
        if canonical_by_local:
            for edge in edges:
                target_key = edge.get("target_key")
                if target_key in canonical_by_local:
                    edge["target_key"] = canonical_by_local[target_key]

        classified_edges = []
        for edge in edges:
            classified_edges.append(
                _classify_portable_edge(
                    edge,
                    selected_keys=selected_keys,
                    complete_keys=complete_keys,
                    context=(
                        f"{type(self.node).__name__} "
                        f"{getattr(self.node, 'qualified_name', '') or self.node.name}"
                    ),
                )
            )
        serialized["edges"] = classified_edges

        # Implementation data is opt-in: method bodies are stripped unless
        # the exporter explicitly asks for them (and even then an empty
        # body adds no information).
        if type(self.node).__name__ == "MethodNode":
            body = serialized.get("body")
            if not export_implementation or not body:
                serialized.pop("body", None)

        # Inline composed children under "composes".  ``children`` is built
        # from parser/backend result order; that order is semantic for enum
        # values, declarations, parameters, and source-layout fragments.
        # Keep both the type buckets and each bucket's insertion order.  The
        # relationship arrays above are intentionally sorted because their
        # order has no code-generation meaning.
        if self.children:
            composes: list[dict] = []
            for type_name, type_children in self.children.items():
                for child_key, child_entry in type_children.items():
                    composes.append(child_entry.serialize(
                        fields=fields,
                        export_implementation=export_implementation,
                        canonical_by_local=canonical_by_local,
                        selected_keys=selected_keys,
                        complete_keys=complete_keys,
                    ))
            serialized["composes"] = composes

        return serialized


@dataclass
class LayerGraph:
    """A Python-only container for all nodes in a design view, filtered by tags.

    Nodes are organised into a nested composition structure via
    ``CompositeEntry`` instances.  Root entries are nodes not composed
    by any other node (files, namespaces, orphan compounds).  Children
    live inside their parent entry's ``children`` dict, keyed by
    target type then target key.

    Non-COMPOSES relationships are stored as references on each entry.

    Attributes:
        tags: The provenance tags this graph was constructed from
            (e.g. frozenset({"design"}), frozenset({"design", "as-built"})).
        entries: Dict mapping stable local keys to CompositeEntry instances
            for root-level nodes only.
        known_keys: Canonical keys observed in the complete source graph,
            including valid endpoints omitted from this selected view.
    """

    tags: frozenset[str]  # e.g. frozenset({"design"}) or frozenset({"design", "as-built"})

    def __post_init__(self) -> None:
        """Validate that all tags are from the allowed vocabulary."""
        invalid = self.tags - set(TAGS)
        if invalid:
            raise ValueError(
                f"Invalid tags {invalid!r}; must be from {TAGS}"
            )

    entries: dict[str, CompositeEntry] = field(default_factory=dict)

    # Canonical keys known to exist in the complete source graph.  This is
    # deliberately wider than the selected entries: a scoped export uses it
    # to distinguish a valid excluded endpoint from a genuinely unresolved
    # extraction result.
    known_keys: frozenset[str] = field(default_factory=frozenset)

    # Scoped views retain their focal compound as the first serialized root;
    # ordinary backend exports use the stable provenance/key ordering below.
    _preferred_root_key: str | None = field(default=None, repr=False, compare=False)

    # Full portable exports may contain a composition DAG rather than a
    # tree: a canonical node can be composed by more than one parent.  Flat
    # wire documents retain each node once and carry COMPOSES as logical
    # edges; deserialization still builds the normal composition indexes.
    _wire_layout: str = field(default="nested", repr=False, compare=False)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _register_identity_maps(
        key_to_key: dict[str, str],
        canonical: str,
        key: str,
        *,
        context: str,
    ) -> None:
        """Register a node's canonical key, REJECTING ambiguous duplicates
        instead of allowing last-write-wins (WP B — canonical-only)."""
        if canonical:
            existing = key_to_key.get(canonical)
            if existing is not None and existing != key:
                raise KeyConflictError(canonical, existing, key, context=context)
            key_to_key[canonical] = key

    @staticmethod
    def _nodes_content_equal(a, b) -> bool:
        """Content equality excluding identity fields (uid, canonical key,
        element id) — used to tell a benign duplicated copy from an
        ambiguous same-uid/same-key pair with differing content."""
        da = a.serialize(fields="all")
        db = b.serialize(fields="all")
        for drop in ("uid", "canonical_key", "element_id"):
            da.pop(drop, None)
            db.pop(drop, None)
        return da == db

    @staticmethod
    def _register_entry(
        key_to_entry: dict[str, "CompositeEntry"],
        key: str,
        entry: "CompositeEntry",
        *,
        context: str,
    ) -> None:
        """Register an entry, rejecting duplicate keys (WP5.1).

        Two DISTINCT nodes resolving to the same entry key — whether a
        shared canonical key or a shared legacy uid — are reported as a
        :class:`KeyConflictError` instead of overwriting one silently.
        Only a true duplicate copy (same identity AND same content, e.g.
        a D9 placement) is tolerated.
        """
        existing = key_to_entry.get(key)
        if existing is not None and existing.node is not entry.node:
            same_logical = (
                (getattr(existing.node, "canonical_key", "") or "")
                == (getattr(entry.node, "canonical_key", "") or "")
                and LayerGraph._nodes_content_equal(existing.node, entry.node)
            )
            if not same_logical:
                raise KeyConflictError(
                    key,
                    getattr(existing.node, "canonical_key", "") or "",
                    getattr(entry.node, "canonical_key", "") or "",
                    context=context,
                )
            # Same logical node re-registered (a duplicated copy in the
            # document, e.g. a D9 placement).  Not ambiguous — the first
            # registration stands and the tree position (child vs root)
            # is decided by child_keys.
            return
        key_to_entry[key] = entry

    @staticmethod
    def _node_key(obj) -> str:
        """Derive a node's local (entry) key — ALWAYS the canonical key
        (WP B — canonical-only).  A node or document entry without a
        canonical key cannot be part of a graph.

        For dicts (raw JSON data), reads the ``canonical_key`` field.
        For CodeGraphNode instances, returns ``canonical_key``.

        Args:
            obj: A CodeGraphNode instance or a raw dict with ``type``
                and node property keys.

        Returns:
            The canonical key string.

        Raises:
            ValueError: if the object carries no canonical key.
        """
        canonical = ""
        if isinstance(obj, dict):
            canonical = obj.get("canonical_key") or ""
        else:
            canonical = getattr(obj, "canonical_key", "") or ""
        if not canonical:
            raise ValueError(
                f"{type(obj).__name__ if not isinstance(obj, dict) else 'document entry'} "
                f"has no canonical_key — canonical-only graphs reject "
                f"uid-bearing legacy data (WP B)"
            )
        try:
            parse_key(canonical)
        except ValueError as exc:
            raise ValueError(
                f"{type(obj).__name__ if not isinstance(obj, dict) else 'document entry'} "
                f"has invalid canonical_key {canonical!r}: {exc}"
            ) from exc
        return canonical

    def resolve_target_name(
        self,
        target_key: str,
        flat: dict[str, "CompositeEntry"] | None = None,
    ) -> str:
        """Resolve a canonical target key to a human-readable display name.

        Looks up *target_key* in the flat entry index and returns the
        node's ``qualified_name`` if set, falling back to ``name``.
        Falls back to *target_key* itself if the entry is not in the
        graph (e.g. a filtered-out neighbour).

        Args:
            target_key: The target node's canonical key.
            flat: Optional prebuilt flat key → entry index.  Callers
                that resolve MANY targets (exporters) MUST pass a
                cached index — the default builds the index from
                scratch per call, which is O(N) per resolution and
                quadratic over a whole export.

        Returns:
            A human-readable display name for the target node.
        """
        if flat is None:
            flat = self._flat_index()
        entry = flat.get(target_key)
        if entry is not None:
            qn = getattr(entry.node, "qualified_name", "") or ""
            if qn:
                return qn
            name = getattr(entry.node, "name", "") or ""
            if name:
                return name
        return target_key

    @staticmethod
    def _walk_entries(entry: CompositeEntry) -> Iterator[CompositeEntry]:
        """Yield all CompositeEntry instances depth-first from *entry*.

        Args:
            entry: The root CompositeEntry to walk.

        Yields:
            Each CompositeEntry in the subtree, depth-first.
        """
        yield entry
        for type_children in entry.children.values():
            for child in type_children.values():
                yield from LayerGraph._walk_entries(child)

    def _all_entries(self) -> Iterator[CompositeEntry]:
        """Yield every CompositeEntry across all root entries, depth-first.

        Yields:
            Each CompositeEntry in the graph.
        """
        for entry in self.entries.values():
            yield from self._walk_entries(entry)

    def _flat_index(self) -> dict[str, CompositeEntry]:
        """Build a flat key → CompositeEntry lookup across the entire tree.

        Returns:
            A dict mapping every node key to its CompositeEntry.
        """
        return {LayerGraph._node_key(e.node): e for e in self._all_entries()}

    def _qname_index(self) -> dict[str, "CompositeEntry"]:
        """Build a qualified_name → CompositeEntry lookup across the entire tree.

        Returns:
            A dict mapping every node's qualified_name to its CompositeEntry.
            Nodes without a qualified_name are skipped. Bare names are also
            indexed for unqualified lookups.
        """
        idx: dict[str, "CompositeEntry"] = {}
        for entry in self._all_entries():
            qname = getattr(entry.node, "qualified_name", None)
            if qname:
                idx[qname] = entry
            name = getattr(entry.node, "name", None)
            if name and name not in idx:
                idx[name] = entry
        return idx

    def has_qname(self, qname: str) -> bool:
        """Check if a qualified or bare name exists anywhere in this graph."""
        if not qname:
            return False
        idx = self._qname_index()
        if qname in idx:
            return True
        bare = qname.rsplit("::", 1)[-1] if "::" in qname else qname
        return bare in idx

    def merge(self, other: "LayerGraph") -> None:
        """Merge another LayerGraph's entries into this one.

        Existing entries (matched by node_key) are NOT overwritten —
        children and references are merged recursively.
        """
        for key, other_entry in other.entries.items():
            if key in self.entries:
                existing = self.entries[key]
                for child_type, child_map in other_entry.children.items():
                    existing.children.setdefault(child_type, {}).update(child_map)
                existing_refs = set(existing.references)
                for ref in other_entry.references:
                    if ref not in existing_refs:
                        existing.references.append(ref)
                        # Carry edge metadata for newly-added references.
                        existing.edge_attrs.update(
                            (k, v) for k, v in other_entry.edge_attrs.items()
                            if k[1] == ref[1] and k[0] == ref[0]
                        )
            else:
                self.entries[key] = other_entry

    # ── Deserialization ──────────────────────────────────────────────

    @classmethod
    def _parse_nested_entry(
        cls,
        data: dict,
        key_to_entry: dict[str, CompositeEntry],
        key_to_key: dict[str, str],
        child_keys: set[str],
    ) -> CompositeEntry:
        """Phase 1: Create entries and build the tree (WP B — canonical-only).

        Does not resolve references — that requires a complete key
        mapping, which is only available after all entries have been
        created.  Use ``_resolve_nested_references`` for Phase 2.

        Args:
            data: A dict representing one node with optional ``composes``
                children.
            key_to_entry: Global index mapping node keys to entries.
            key_to_key: Mapping from canonical keys to local keys.
            child_keys: Set of keys that appear as composed children
                (used to determine root entries).

        Returns:
            The CompositeEntry for this node (with children attached,
            references pending).
        """
        _ensure_type_registered(_type_discriminator(data) or "")
        node = CodeGraphNode.deserialize(data)
        entry = CompositeEntry(node=node)

        key = cls._node_key(data)
        canonical = getattr(node, "canonical_key", "") or ""
        cls._register_identity_maps(
            key_to_key, canonical, key, context="nested deserialize"
        )

        # Register in the global index (reject duplicate keys)
        cls._register_entry(key_to_entry, key, entry, context="nested deserialize")

        # Process composes children recursively
        for child_data in data.get("composes", []):
            child_entry = cls._parse_nested_entry(
                child_data, key_to_entry, key_to_key, child_keys
            )
            child_key = cls._node_key(child_data)
            child_type = _type_discriminator(child_data)
            if child_type not in entry.children:
                entry.children[child_type] = {}
            entry.children[child_type][child_key] = child_entry
            child_keys.add(child_key)

        return entry

    @classmethod
    def _resolve_target_key(
        cls,
        edge: dict,
        key_to_key: dict[str, str],
    ) -> str | None:
        """Resolve an edge target to a local key (WP B — canonical-only).

        ``target_key`` is the canonical endpoint.  An edge without a
        canonical target is unresolved — human-readable references use a
        distinct ``target_ref`` field and must resolve before persistence;
        they are never stored in ``target_key``.

        Returns the resolved local key, or None when nothing matches.
        """
        key = edge.get("target_key") or ""
        return key_to_key.get(key) if key else None

    @classmethod
    def _resolve_nested_references(
        cls,
        data: dict,
        key_to_entry: dict[str, CompositeEntry],
        key_to_key: dict[str, str],
    ) -> None:
        """Phase 2: Resolve non-COMPOSES references for all entries.

        Walks the nested data recursively and populates the
        ``references`` list on each CompositeEntry using the complete
        canonical-key mapping.

        Args:
            data: A dict representing one node with optional ``composes``
                children and ``edges``.
            key_to_entry: Global index mapping node keys to entries.
            key_to_key: Complete mapping from canonical keys to local keys.
        """
        source_key = cls._node_key(data)
        source_entry = key_to_entry[source_key]

        for edge in data.get("edges", []):
            _validate_portable_edge_shape(edge, context="nested deserialize")
            target_key = cls._resolve_target_key(edge, key_to_key)
            if target_key is None or edge.get("external") is True:
                if target_key is not None and edge.get("external") is True:
                    raise GraphDocumentError(
                        "nested deserialize: an in-document target cannot also be external"
                    )
                raw_target_key = edge.get("target_key")
                if raw_target_key:
                    source_entry.references.append(
                        (edge["relation_type"], raw_target_key, edge["target_type"])
                    )
                    attrs = {
                        k: v for k, v in edge.items()
                        if k not in ("relation_type", "target_key",
                                     "target_local_id", "target_type")
                    }
                    if attrs:
                        source_entry.edge_attrs[
                            (edge["relation_type"], raw_target_key)
                        ] = attrs
                else:
                    source_entry.unresolved_edges.append(dict(edge))
                continue
            source_entry.references.append(
                (edge["relation_type"], target_key, edge["target_type"])
            )
            # Relationship-level metadata (e.g. the include spelling on
            # INCLUDES edges) rides alongside the reference so it survives
            # deserialize → serialize → backends.
            attrs = {
                k: v for k, v in edge.items()
                if k not in ("relation_type", "target_key",
                             "target_local_id", "target_type")
            }
            if attrs:
                source_entry.edge_attrs[(edge["relation_type"], target_key)] = attrs

        for child_data in data.get("composes", []):
            cls._resolve_nested_references(
                child_data, key_to_entry, key_to_key
            )

    @classmethod
    def _deserialize_nested(cls, data: list[dict]) -> "LayerGraph":
        """Deserialize from the nested JSON format (entries with composes key).

        Two-phase approach:
        1. Create all CompositeEntry instances and build the canonical-key mapping.
        2. Resolve references using the complete mapping.

        Args:
            data: A list of dicts in nested format, where each entry may
                have a ``composes`` key containing child nodes.

        Returns:
            A LayerGraph with the nested composition structure.
        """
        key_to_entry: dict[str, CompositeEntry] = {}
        key_to_key: dict[str, str] = {}
        child_keys: set[str] = set()
        tags: frozenset[str] = frozenset()

        # Phase 1: create entries and build tree structure
        for entry_data in data:
            cls._parse_nested_entry(
                entry_data, key_to_entry, key_to_key, child_keys
            )
            # Infer tags from node data (backward compat: "layer" field)
            if not tags:
                node_tags = entry_data.get("tags", [])
                if not node_tags and "layer" in entry_data:
                    node_tags = [entry_data["layer"]]
                if node_tags:
                    tags = frozenset(node_tags)

        # Phase 2: resolve references with complete key mapping
        for entry_data in data:
            cls._resolve_nested_references(
                entry_data, key_to_entry, key_to_key
            )

        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }
        return cls(
            tags=tags or frozenset({"design"}),
            entries=root_entries,
            known_keys=frozenset(key_to_entry),
        )

    @classmethod
    def _deserialize_flat(
        cls,
        data: list[dict],
        *,
        create_missing: bool = False,
    ) -> "LayerGraph":
        """Deserialize from the flat JSON format (edges with target_key).

        Args:
            data: A list of dicts in flat format, where COMPOSES edges
                create nesting and other edges become references.
            create_missing: When True, auto-create scaffold nodes (with
                ``tags=["scaffold"]``) for edge targets that don't
                resolve to any node in *data*.  This allows partial graphs
                that reference external nodes to be deserialized without
                manually pre-creating placeholder nodes.

        Returns:
            A LayerGraph with the nested composition structure.
        """
        key_to_entry: dict[str, CompositeEntry] = {}
        key_to_key: dict[str, str] = {}
        tags: frozenset[str] = frozenset()

        # Phase 1: create all CompositeEntry instances (nodes only, no edges yet)
        for node_data in data:
            _ensure_type_registered(_type_discriminator(node_data) or "")
            node = CodeGraphNode.deserialize(node_data)
            key = cls._node_key(node_data)
            cls._register_entry(
                key_to_entry, key, CompositeEntry(node=node),
                context="flat deserialize",
            )

            canonical = getattr(node, "canonical_key", "") or ""
            cls._register_identity_maps(
                key_to_key, canonical, key, context="flat deserialize",
            )

            # Infer tags from node data (backward compat: "layer" field)
            if not tags:
                node_tags = node_data.get("tags", [])
                if not node_tags and "layer" in node_data:
                    node_tags = [node_data["layer"]]
                if node_tags:
                    tags = frozenset(node_tags)

        # Phase 2: walk edges and build nesting / references
        # Track which nodes are children (composed by another node)
        child_keys: set[str] = set()

        for node_data in data:
            source_key = cls._node_key(node_data)
            source_entry = key_to_entry[source_key]

            for edge in node_data.get("edges", []):
                _validate_portable_edge_shape(edge, context="flat deserialize")
                # Canonical-only resolution: canonical key → local entry key.
                target_key = cls._resolve_target_key(edge, key_to_key)

                # Auto-create a scaffold only for an explicit unresolved
                # notional reference.  A canonical target that is absent
                # from this document is not enough to invent a second key
                # algorithm; it remains an unresolved endpoint unless the
                # producer supplied ``target_ref``.
                created_scaffold = False
                if (
                    target_key is None
                    and create_missing
                    and edge.get("target_ref")
                    and edge.get("external") is not True
                ):
                    target_key = cls._create_missing_scaffold(
                        edge, key_to_entry, key_to_key
                    )
                    created_scaffold = target_key is not None

                # Once a target_ref has materialized into a canonical local
                # entry it is no longer an unresolved portable endpoint.
                # Do not retain the source diagnostic metadata in
                # edge_attrs, or serialization would emit both endpoint
                # fields on the next round trip.
                if created_scaffold:
                    edge = dict(edge)
                    edge["target_key"] = target_key
                    edge.pop("target_ref", None)
                    edge.pop("unresolved", None)
                    edge.pop("diagnostic", None)

                if target_key is None:
                    raw_target_key = edge.get("target_key")
                    if raw_target_key:
                        source_entry.references.append(
                            (edge["relation_type"], raw_target_key, edge["target_type"])
                        )
                        attrs = {
                            k: v for k, v in edge.items()
                            if k not in ("relation_type", "target_key",
                                         "target_local_id", "target_type")
                        }
                        if attrs:
                            source_entry.edge_attrs[
                                (edge["relation_type"], raw_target_key)
                            ] = attrs
                    else:
                        source_entry.unresolved_edges.append(dict(edge))
                    continue

                relation_type = edge["relation_type"]
                target_type = edge["target_type"]

                if edge.get("external") is True:
                    raise GraphDocumentError(
                        "flat deserialize: an in-document target cannot also be external"
                    )

                if relation_type == "COMPOSES":
                    # Nest target as a child under the source entry
                    target_entry = key_to_entry.get(target_key)
                    if target_entry is not None:
                        if target_type not in source_entry.children:
                            source_entry.children[target_type] = {}
                        source_entry.children[target_type][target_key] = target_entry
                        child_keys.add(target_key)
                else:
                    # Store as a reference
                    source_entry.references.append(
                        (relation_type, target_key, target_type)
                    )
                    # Relationship-level metadata (e.g. the include
                    # spelling on INCLUDES edges) rides alongside.
                    attrs = {
                        k: v for k, v in edge.items()
                        if k not in ("relation_type", "target_key",
                                     "target_local_id", "target_type")
                    }
                    if attrs:
                        source_entry.edge_attrs[(relation_type, target_key)] = attrs

        # Phase 3: root entries = nodes that were never a COMPOSES target
        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }

        compose_parent_counts: dict[str, int] = {}
        for node_data in data:
            for edge in node_data.get("edges", []):
                if edge.get("relation_type") == "COMPOSES" and edge.get("target_key"):
                    target_key = edge["target_key"]
                    compose_parent_counts[target_key] = (
                        compose_parent_counts.get(target_key, 0) + 1
                    )

        return cls(
            tags=tags or frozenset({"design"}),
            entries=root_entries,
            known_keys=frozenset(key_to_entry),
            # Ordinary flat documents with a tree-shaped COMPOSES relation
            # retain the established nested serialization contract. A true
            # DAG (shared composition targets) keeps the lossless flat layout.
            _wire_layout=(
                "flat"
                if any(count > 1 for count in compose_parent_counts.values())
                else "nested"
            ),
        )

    @staticmethod
    def _classify_literal(value: str) -> str:
        """Classify a literal value string as int, float, boolean, or string."""
        value = value.strip()
        if value.lower() in ("true", "false"):
            return "boolean"
        try:
            int(value)
            return "int"
        except ValueError:
            pass
        try:
            float(value)
            return "float"
        except ValueError:
            pass
        return "string"

    @staticmethod
    def _create_missing_scaffold(
        edge: dict,
        key_to_entry: dict[str, CompositeEntry],
        key_to_key: dict[str, str],
    ) -> str | None:
        """Create a scaffold node for an unresolved notional target
        (WP B — canonical-only).

        Builds a minimal node dict from the edge's ``target_type`` and
        its notional reference (``target_ref`` / ``target_qualified_name``
        — the plan's distinct field for human-readable references; it is
        never stored in ``target_key``), deserializes it, computes its
        canonical key under the ACTIVE identity scope, and registers it.

        The scaffold gets ``tags=["scaffold"]`` so it can be identified
        and later reconciled with real design nodes.

        Args:
            edge: The unresolved edge dict with ``target_type`` and a
                ``target_ref`` / ``target_qualified_name`` reference.
            key_to_entry: Global index to add the scaffold to.
            key_to_key: Canonical-key → local-key mapping to update.

        Returns:
            The scaffold's key, or None if creation failed (no active
            scope, or the edge carries no resolvable reference).
        """
        target_type = edge.get("target_type", "")
        target_ref = (
            edge.get("target_ref")
            or edge.get("target_qualified_name")
            or edge.get("target_name")
            or ""
        )
        if not target_type or not target_ref:
            return None
        from codegraph.identity import get_identity_scope, resolve_identity_for

        scope = get_identity_scope()
        if scope is None:
            return None

        target_cls = CodeGraphNode._registry.get(target_type)
        if not target_cls:
            return None

        # Build minimal scaffold dict
        scaffold_data: dict = {
            "type": target_type, "source": "scaffold", "tags": ["scaffold"],
        }
        if PropertyRegistry.has_property(target_cls, "qualified_name"):
            scaffold_data["qualified_name"] = target_ref
        scaffold_data["name"] = target_ref.rsplit("::", 1)[-1] if "::" in target_ref else target_ref

        kind_defaults = {
            "ClassNode": "class",
            "CompoundNode": "class",
            "InterfaceNode": "interface",
            "EnumNode": "enum",
            "AttributeNode": "attribute",
            "MemberNode": "attribute",
            "MethodNode": "method",
            "FunctionNode": "function",
            "LiteralNode": "literal",
        }
        if target_type in kind_defaults and PropertyRegistry.has_property(target_cls, "kind"):
            scaffold_data["kind"] = kind_defaults[target_type]

        if target_type == "LiteralNode":
            raw_value = (
                target_ref.split("::", 1)[1]
                if target_ref.startswith("literal::")
                else target_ref
            )
            scaffold_data["value"] = raw_value
            scaffold_data["value_type"] = LayerGraph._classify_literal(raw_value)

        scaffold_node = CodeGraphNode.deserialize(scaffold_data)
        try:
            scaffold_node.canonical_key = resolve_identity_for(
                scaffold_node, scope
            ).key()
        except Exception:
            return None
        scaffold_key = scaffold_node.canonical_key

        # Repeated references to the same notional target are one scaffold,
        # not replacement entries.  This keeps deserialization idempotent and
        # lets later edges resolve to the exact same canonical entry.
        if scaffold_key not in key_to_entry:
            key_to_entry[scaffold_key] = CompositeEntry(node=scaffold_node)
            key_to_key[scaffold_key] = scaffold_key

        # For member types with a "::"-separated qualified_name, also
        # create a parent ClassNode scaffold (if not already present)
        # and nest the member under it via COMPOSES.  This follows the
        # codegraph convention that members belong to compounds.
        if target_type in (
            "AttributeNode", "MemberNode", "MethodNode", "FunctionNode",
        ):
            if "::" in target_ref:
                parent_name = target_ref.rsplit("::", 1)[0]
            else:
                parent_name = None
            if parent_name:
                parent_key = next(
                    (k for k, e in key_to_entry.items()
                     if getattr(e.node, "qualified_name", "") == parent_name
                     and type(e.node).__name__ == "ClassNode"),
                    None,
                )
                if parent_key is None:
                    parent_edge = {
                        "target_ref": parent_name,
                        "target_type": "ClassNode",
                        "relation_type": "COMPOSES",
                    }
                    parent_key = LayerGraph._create_missing_scaffold(
                        parent_edge, key_to_entry, key_to_key
                    )
                if parent_key is not None:
                    parent_entry = key_to_entry[parent_key]
                    if target_type not in parent_entry.children:
                        parent_entry.children[target_type] = {}
                    parent_entry.children[target_type][scaffold_key] = (
                        key_to_entry[scaffold_key]
                    )

        return scaffold_key

    @classmethod
    def deserialize(
        cls,
        data: list[dict],
        *,
        create_missing: bool = False,
    ) -> "LayerGraph":
        """Deserialize from a list of dicts (as produced by ``serialize()``).

        Pure deserialization — no database interaction.  Infers tags from
        the first node that has a ``tags`` field (fallback: ``frozenset({"design"})``).
        Supports backward compatibility with legacy ``layer`` field data.

        Accepts two formats:
        - **Nested format**: entries with a ``composes`` key containing
          child nodes.  COMPOSES edges are represented by nesting, not
          in the ``edges`` array.
        - **Flat format**: all nodes as separate entries with ``edges``
          arrays containing COMPOSES and other relationship types.

        Args:
            data: A list of dicts, each a serialized node with ``type``,
                properties, and optionally ``edges`` and ``composes``.
                May also be a versioned document envelope (as produced by
                ``serialize(document=True)``):
                ``{"format_version": 1, "identity_version": 1,
                "entries": [...]}``.  A bare list is the documented legacy
                form and is treated as format version 1.
            create_missing: When True, auto-create scaffold nodes for
                edge targets that don't resolve to any node in *data*.

        Returns:
            A LayerGraph containing the deserialized nodes in a nested
            composition structure.

        Raises:
            GraphDocumentError: if *data* is a document envelope that
                is structurally invalid or declares a format/key version
                this build does not support (WP2.3).
        """
        if isinstance(data, dict):
            data = cls._unwrap_document(data)
        if not isinstance(data, list):
            raise GraphDocumentError("LayerGraph entries must be a list")
        # Detect format: nested if any entry has a "composes" key
        has_nested = any("composes" in entry for entry in data)

        if has_nested:
            return cls._deserialize_nested(data)

        return cls._deserialize_flat(data, create_missing=create_missing)

    # ── versioned document envelope (WP2.3) ─────────────────────────

    @classmethod
    def _unwrap_document(cls, document: dict) -> list[dict]:
        """Validate and unwrap a versioned document envelope.

        A document dict must declare ``format_version`` and
        ``identity_version`` (both ints); unknown/future values fail
        clearly.  ``entries`` must be a list of node dicts.  Extra keys
        are tolerated so future envelopes can add metadata without
        breaking older readers.

        Raises:
            GraphDocumentError: on a missing/invalid/unsupported
                declaration.
        """
        if "format_version" not in document:
            raise GraphDocumentError(
                "document envelope must declare 'format_version'; a bare "
                "list is the legacy format — a dict is not"
            )
        format_version = document.get("format_version")
        if not isinstance(format_version, int) or isinstance(format_version, bool):
            raise GraphDocumentError(
                f"'format_version' must be an int, got {type(format_version).__name__}",
                format_version=format_version,
            )
        if format_version != GRAPH_DOCUMENT_FORMAT_VERSION:
            raise GraphDocumentError(
                f"unsupported graph document format version {format_version}; "
                f"this build supports only version "
                f"{GRAPH_DOCUMENT_FORMAT_VERSION}",
                format_version=format_version,
            )
        identity_version = document.get("identity_version")
        if not isinstance(identity_version, int) or isinstance(identity_version, bool):
            raise GraphDocumentError(
                f"'identity_version' must be an int, got "
                f"{type(identity_version).__name__}",
                format_version=format_version,
                identity_version=identity_version,
            )
        if identity_version != KEY_VERSION:
            raise GraphDocumentError(
                f"unsupported canonical identity version {identity_version}; "
                f"this build supports only version {KEY_VERSION} "
                f"(keys carry the {VERSION_PREFIX!r} prefix)",
                format_version=format_version,
                identity_version=identity_version,
            )
        entries = document.get("entries")
        if not isinstance(entries, list):
            raise GraphDocumentError(
                "document envelope 'entries' must be a list of node dicts",
                format_version=format_version,
                identity_version=identity_version,
            )
        return entries

    # ── to_backend / from_backend ──────────────────────────────────────

    def to_backend(self, backend: Backend) -> None:
        """Persist to any backend (replaces to_neo4j)."""
        backend.bulk_save(self)

    @classmethod
    def from_backend(cls, backend: Backend, tag: str) -> "LayerGraph":
        """Load from any backend (replaces from_neo4j).

        The backend returns a flat list of nodes.  Tree construction
        (COMPOSES nesting, duplicate merging, namespace pruning) is
        pure Python in this method.
        """
        matched_nodes = backend.bulk_load_by_tag(tag)

        nodes: dict[str, CodeGraphNode] = {}
        key_to_key: dict[str, str] = {}
        known_keys: set[str] = set()

        # Backend implementations do not promise row ordering.  Sort before
        # resolving duplicate qualified names so the representative canonical
        # node is selected deterministically across SQLite/Neo4j loads.
        matched_nodes = sorted(
            backend.bulk_load_by_tag(tag),
            key=lambda node: (
                cls._node_key(node),
                type(node).__name__,
                getattr(node, "qualified_name", "") or "",
                getattr(node, "name", "") or "",
            ),
        )

        # ImplementationNode is deliberately excluded from LayerGraphs
        # (see its model docstring: "LayerGraph construction skips
        # implementation nodes by design").  Implementation bodies are
        # reachable only via HAS_IMPLEMENTATION edges, which the
        # expansion/serialization/viz paths all exclude — but a tag
        # match on the implementation node itself (e.g. project code
        # tagged as-built) would still load it as a matched node,
        # producing isolated floating leaves in every exporter.
        #
        # type_parameter nodes (ClassNode with kind="type_parameter" —
        # template-parameter slots, ``type_param:<qn>:<pos>``) are
        # likewise excluded: their TEMPLATE_PARAM edges are dropped
        # from serialized graph views by design, so without this filter
        # they load as matched nodes and float disconnected.
        for node in matched_nodes:
            if type(node).__name__ == "ImplementationNode":
                continue
            if getattr(node, "kind", "") == "type_parameter":
                continue
            key = cls._node_key(node)
            # WP B: two DISTINCT nodes resolving to one canonical key are
            # reported, not merged by last-write-wins.
            existing = nodes.get(key)
            if existing is not None and existing is not node:
                same_logical = (
                    (getattr(existing, "canonical_key", "") or "")
                    == (getattr(node, "canonical_key", "") or "")
                )
                if not same_logical:
                    raise KeyConflictError(
                        key,
                        getattr(existing, "canonical_key", "") or "",
                        getattr(node, "canonical_key", "") or "",
                        context="backend load",
                    )
            nodes[key] = node
            key_to_key[key] = key
            known_keys.add(
                getattr(node, "canonical_key", "") or key
            )

        key_to_entry: dict[str, CompositeEntry] = {}
        duplicate_to_canonical: dict[str, str] = {}
        qname_to_key: dict[str, str] = {}
        for key, node in nodes.items():
            entry = CompositeEntry(node=node)
            qn = (getattr(node, "qualified_name", None)
                  or getattr(node, "name", None))
            if qn:
                existing_key = qname_to_key.get(qn)
                if existing_key is not None:
                    duplicate_to_canonical[key] = existing_key
                    key_to_entry[key] = entry
                    continue
                qname_to_key[qn] = key
            key_to_entry[key] = entry

        child_keys: set[str] = set()

        # Batch-fetch children + edges once.  The ABC default falls back
        # to per-node queries; the Neo4j backend batches (2 queries for
        # edges, 1 for children) so tree assembly stays O(batches) rather
        # than O(nodes) round trips at graph scale.
        node_list = list(nodes.values())
        children_by_key = backend.get_composed_children_bulk(node_list)
        edges_by_key = backend.get_edges_bulk(node_list)

        def _child_sort_key(
            indexed_child: tuple[int, CodeGraphNode],
        ) -> tuple[int, int, int]:
            """Order composed declarations by source position when known.

            Backend relationship queries are intentionally unordered.  A
            canonical-key sort is deterministic but changes declaration
            order for enum values and mixed class members, which is
            observable in generated source.  Indexed source spans are the
            semantic order; backend/parser order is preserved when a node
            has no source location.
            """
            index, child = indexed_child
            start_line = int(getattr(child, "start_line", 0) or 0)
            line_number = int(getattr(child, "line_number", 0) or 0)
            return (
                0 if start_line or line_number else 1,
                start_line or line_number,
                index,
            )

        for key, node in nodes.items():
            canonical_key = duplicate_to_canonical.get(key, key)
            entry = key_to_entry.get(canonical_key)
            if entry is None:
                continue

            key = cls._node_key(node)
            children = [
                child for _index, child in sorted(
                    enumerate(children_by_key.get(key, [])),
                    key=_child_sort_key,
                )
            ]
            edges = sorted(
                edges_by_key.get(key, []),
                key=lambda edge: (
                    edge.relation_type,
                    edge.target_key or "",
                    edge.target_type or "",
                    bool(edge.is_outgoing),
                    repr(getattr(edge, "attributes", {}) or {}),
                ),
            )
            if not children and not edges:
                children = [
                    child for _index, child in sorted(
                        enumerate(backend.get_composed_children(node)),
                        key=_child_sort_key,
                    )
                ]
                edges = sorted(
                    backend.get_all_edges(node),
                    key=lambda edge: (
                        edge.relation_type,
                        edge.target_key or "",
                        edge.target_type or "",
                        bool(edge.is_outgoing),
                        repr(getattr(edge, "attributes", {}) or {}),
                    ),
                )

            for child in children:
                child_key = cls._node_key(child)
                child_key = duplicate_to_canonical.get(child_key, child_key)
                if child_key not in key_to_entry:
                    continue
                child_entry = key_to_entry[child_key]
                child_type = type(child).__name__
                entry.children.setdefault(child_type, {})[child_key] = child_entry
                child_keys.add(child_key)

            for edge in edges:
                if edge.relation_type in ("COMPOSES", "HAS_IMPLEMENTATION"):
                    continue
                if not edge.is_outgoing:
                    continue
                target_key = edge.target_key
                if target_key:
                    known_keys.add(target_key)
                    entry.references.append(
                        (edge.relation_type, target_key, edge.target_type)
                    )
                    if getattr(edge, "attributes", None):
                        entry.edge_attrs[(edge.relation_type, target_key)] = dict(
                            edge.attributes
                        )

        for dup_key, canon_key in duplicate_to_canonical.items():
            dup_entry = key_to_entry.get(dup_key)
            canon_entry = key_to_entry.get(canon_key)
            if dup_entry and canon_entry:
                for ct, cm in dup_entry.children.items():
                    canon_entry.children.setdefault(ct, {}).update(cm)
                    for ck in cm:
                        child_keys.add(ck)
                existing_refs = set(canon_entry.references)
                for ref in dup_entry.references:
                    if ref not in existing_refs:
                        canon_entry.references.append(ref)
                        existing_refs.add(ref)
                canon_entry.edge_attrs.update(dup_entry.edge_attrs)
                canon_entry.unresolved_edges.extend(
                    edge for edge in dup_entry.unresolved_edges
                    if edge not in canon_entry.unresolved_edges
                )

        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }

        _require_tags(tag, (e.node for e in key_to_entry.values()))

        graph = cls(
            tags=frozenset({tag}),
            entries=root_entries,
            known_keys=frozenset(known_keys),
        )
        graph._prune_empty_namespaces()
        return graph

    # ── to_neo4j (compat) ────────────────────────────────────────────

    def to_neo4j(self) -> None:
        """Persist via the active backend. Delegates to to_backend()."""
        self.to_backend(get_backend())

    # ── Serialization ──────────────────────────────────────────────────

    def _serialize_flat(
        self,
        fields: str,
        *,
        export_implementation: bool,
    ) -> list[dict]:
        """Serialize a canonical-key graph once per node.

        This is the lossless wire form for full backend exports.  The normal
        nested serializer is intentionally retained for bounded/tree views;
        this path only activates for documents read from flat input and
        preserves shared COMPOSES targets without duplicate node records.
        """
        flat = self._flat_index()
        result: list[dict] = []
        for key, entry in sorted(flat.items(), key=lambda item: (
            0 if "as-built" in (getattr(item[1].node, "tags", None) or [])
            else 1 if "design" in (getattr(item[1].node, "tags", None) or [])
            else 2,
            item[0],
        )):
            serialized = entry.node.serialize(fields=fields)
            for field_name in _PORTABLE_NODE_FORBIDDEN_FIELDS:
                serialized.pop(field_name, None)
            # A deserialized node can have an element id after a persistence
            # round-trip; do not leak backend-fetched edges into this wire
            # representation.  The LayerGraph reference/child indexes below
            # are the complete logical edge source.
            serialized["edges"] = []
            if type(entry.node).__name__ == "MethodNode":
                body = serialized.get("body")
                if not export_implementation or not body:
                    serialized.pop("body", None)

            observations: dict[tuple[str, str], tuple[str, dict]] = {}
            unresolved_edges: list[dict] = []

            def add_edge(
                relation_type: str,
                target_key: str,
                target_type: str,
                attrs: dict | None = None,
            ) -> None:
                attrs = dict(attrs or {})
                identity = (relation_type, target_key)
                value = (target_type, attrs)
                existing = observations.get(identity)
                if existing is not None and existing != value:
                    raise GraphDocumentError(
                        "conflicting duplicate endpoint triple during flat "
                        f"serialization: {key!r}, {identity!r}"
                    )
                observations[identity] = value

            for relation_type, target_key, target_type in entry.references:
                if relation_type in ("HAS_IMPLEMENTATION", "TEMPLATE_PARAM"):
                    continue
                attrs = dict(entry.edge_attrs.get((relation_type, target_key)) or {})
                if target_key not in flat:
                    if attrs.get("external") is True or target_key in self.known_keys:
                        attrs["external"] = True
                        attrs.pop("unresolved", None)
                        attrs.pop("diagnostic", None)
                    else:
                        unresolved_edges.append({
                            "relation_type": relation_type,
                            "target_ref": target_key,
                            "target_type": target_type,
                            "unresolved": True,
                            "diagnostic": (
                                "canonical target is absent from the selected "
                                "and complete graph"
                            ),
                        })
                        continue
                else:
                    attrs.pop("external", None)
                    attrs.pop("unresolved", None)
                    attrs.pop("diagnostic", None)
                add_edge(
                    relation_type,
                    target_key,
                    target_type,
                    attrs,
                )
            for child_type, children in entry.children.items():
                for child_key, child_entry in children.items():
                    add_edge("COMPOSES", child_key, child_type)

            def edge_sort(item: tuple[tuple[str, str], tuple[str, dict]]) -> tuple:
                (relation_type, target_key), (target_type, attrs) = item
                target_entry = flat.get(target_key)
                target_node = target_entry.node if target_entry else None
                if relation_type == "COMPOSES":
                    return (
                        0,
                        int(getattr(target_node, "start_line", 0) or
                            getattr(target_node, "line_number", 0) or 0),
                        int(getattr(target_node, "position", 0) or 0),
                        target_key,
                    )
                return (
                    1,
                    relation_type,
                    target_key,
                    target_type,
                    json.dumps(attrs, sort_keys=True, separators=(",", ":")),
                )

            serialized["edges"] = [
                {
                    "relation_type": relation_type,
                    "target_key": target_key,
                    "target_type": target_type,
                    **attrs,
                }
                for (relation_type, target_key), (target_type, attrs)
                in sorted(observations.items(), key=edge_sort)
            ]
            serialized["edges"].extend(
                sorted(
                    (dict(edge) for edge in unresolved_edges + entry.unresolved_edges),
                    key=lambda edge: (
                        edge.get("relation_type", ""),
                        edge.get("target_ref", ""),
                        edge.get("target_type", ""),
                    ),
                )
            )
            result.append(serialized)
        return result

    def serialize(
        self,
        fields: str = "llm",
        *,
        export_implementation: bool = False,
        document: bool = False,
    ) -> list[dict] | dict:
        """Serialize the graph as a nested list of dicts.

        Root entries are serialized recursively.  Composed children
        appear under a ``composes`` key on their parent and do not
        appear as top-level entries.  COMPOSES edges are excluded
        from the ``edges`` array since the nesting represents them
        explicitly.

        For nodes that have not been persisted to Neo4j, the
        ``edges`` key will be an empty list.

        Args:
            fields: Which property fields to include when serializing
                each node.  ``"llm"`` (default) — only ``_llm_fields``.
                ``"all"`` — every defined property.  Passed through to
                ``CodeGraphNode.serialize()``.
            export_implementation: When True, MethodNode ``body``
                text (implementation bodies captured at parse time) is
                included so codegen can regenerate out-of-line and
                inline definitions.  Default False — implementation
                data is opt-in and default exports stay lean.
            document: When True, wrap the entries in a versioned
                document envelope (WP2.3):
                ``{"format_version": 1, "identity_version": 1,
                "entries": [...]}`` so readers never infer the format
                from field presence.  Default False — the bare nested
                list, the documented legacy v1 form.

        Returns:
            A list of serialized node dicts with nested composition
            (or the versioned envelope dict when *document* is True),
            suitable for passing to ``json.dumps()`` externally.
        """
        if self._wire_layout == "flat":
            entries = self._serialize_flat(
                fields,
                export_implementation=export_implementation,
            )
            if not document:
                return entries
            return {
                "format_version": GRAPH_DOCUMENT_FORMAT_VERSION,
                "identity_version": KEY_VERSION,
                "entries": entries,
            }

        # WP B: build the local-key → canonical-key map across the whole
        # tree so reference edges carry the target's canonical key.
        canonical_by_local: dict[str, str] = {}
        flat = self._flat_index()
        selected_keys = set(flat)
        complete_keys = set(self.known_keys)
        for key, entry in flat.items():
            canonical = getattr(entry.node, "canonical_key", "") or ""
            if canonical:
                canonical_by_local[key] = canonical
                qname = getattr(entry.node, "qualified_name", "") or ""
                if qname:
                    canonical_by_local[qname] = canonical
        def _entry_sort_key(item: tuple[str, CompositeEntry]) -> tuple[int, int, str]:
            key, entry = item
            node_tags = set(getattr(entry.node, "tags", None) or ())
            # Preserve the primary provenance tag used by legacy bare-list
            # readers, which infer graph tags from the first serialized node.
            # Within that stable provenance bucket, canonical identity orders
            # the document independently of backend row order.
            priority = (
                0 if "as-built" in node_tags
                else 1 if "design" in node_tags
                else 2
            )
            preferred = 0 if key == self._preferred_root_key else 1
            return preferred, priority, key

        entries = [
            entry.serialize(
                fields=fields,
                export_implementation=export_implementation,
                canonical_by_local=canonical_by_local,
                selected_keys=selected_keys,
                complete_keys=complete_keys,
            )
            for key, entry in sorted(self.entries.items(), key=_entry_sort_key)
        ]
        if not document:
            return entries
        return {
            "format_version": GRAPH_DOCUMENT_FORMAT_VERSION,
            "identity_version": KEY_VERSION,
            "entries": entries,
        }

    def identity_digest(self) -> str:
        """Full-graph identity hash (WP5.1/5.4).

        One digest over the entire tree keyed by each node's
        :meth:`CodeGraphNode.primary_key` (canonical key when present,
        else legacy uid) with a content hash of its non-identity
        properties.  Two graphs with the same digest have the same
        nodes under the same identities — the basis for graph-fixpoint
        comparison and migration verification.
        """
        import hashlib
        from codegraph.models.descriptors import PropertyRegistry

        digest = hashlib.sha256()
        lines: list[str] = []
        for entry in self._all_entries():
            node = entry.node
            parts = [
                node.primary_key(),
                type(node).__name__,
                ",".join(sorted(type(node).inherited_labels())),
            ]
            for name in sorted(PropertyRegistry.properties_of(type(node))):
                if name in ("uid", "canonical_key", "element_id"):
                    continue
                val = getattr(node, name, None)
                if val is None or val == "" or val == []:
                    continue
                parts.append(f"{name}={val!r}")
            lines.append("\n".join(parts))
        digest.update("\n---\n".join(sorted(lines)).encode("utf-8"))
        return digest.hexdigest()

    # ── from_neo4j (compat) ──────────────────────────────────────────

    @classmethod
    def from_neo4j(cls, tag: str) -> "LayerGraph":
        """Load via the active backend. Delegates to from_backend()."""
        return cls.from_backend(get_backend(), tag)

    @classmethod
    def import_compound(cls, qname: str, tag: str | None = None) -> "LayerGraph":
        """Create a LayerGraph containing a single compound and its members.

        Fetches the compound node by qualified_name from Neo4j, walks
        its COMPOSES children and non-COMPOSES edges.  Returns a new
        LayerGraph for the caller to merge into a working graph.

        Args:
            qname: Fully-qualified name of the compound to fetch.
            tag: Optional tag filter (e.g. 'as-built').  Only the
                compound itself is tag-checked; children are included
                regardless of tag.

        Returns:
            A LayerGraph containing the compound and its immediate
            composition children.
        """
        from codegraph.models.compound import CompoundNode
        from codegraph.models.namespace import NamespaceNode

        node = CompoundNode.nodes.get_or_none(qualified_name=qname)
        if node is None:
            node = NamespaceNode.nodes.get_or_none(qualified_name=qname)
        if node is None:
            raise ValueError(f"No compound or namespace found for '{qname}'")
        if tag and tag not in (node.tags or []):
            raise ValueError(
                f"Node '{qname}' has tags {list(node.tags or [])}, not '{tag}'"
            )

        actual_tags = frozenset(node.tags or []) or frozenset({"as-built"})
        key = cls._node_key(node)
        entry = CompositeEntry(node=node)
        known_keys: set[str] = {key}

        for child in get_backend().get_composed_children(node):
            child_key = cls._node_key(child)
            child_entry = CompositeEntry(node=child)
            child_type = type(child).__name__
            entry.children.setdefault(child_type, {})[child_key] = child_entry

        for edge in get_backend().get_all_edges(node):
            rt = edge.relation_type
            if rt in ("COMPOSES", "HAS_IMPLEMENTATION"):
                continue
            if not edge.is_outgoing:
                continue
            entry.references.append((rt, edge.target_key, edge.target_type))
            if edge.target_key:
                known_keys.add(edge.target_key)
            if getattr(edge, "attributes", None):
                entry.edge_attrs[(rt, edge.target_key)] = dict(edge.attributes)

        return cls(
            tags=actual_tags,
            entries={key: entry},
            known_keys=frozenset(known_keys),
        )

    # ── Lookups & mutation ────────────────────────────────────────────

    def _qname_index(self) -> dict[str, CompositeEntry]:
        """Build a qualified_name → CompositeEntry lookup across the entire tree.

        Returns:
            A dict mapping every node's ``qualified_name`` to its
            CompositeEntry.  Nodes without a ``qualified_name`` are
            omitted.
        """
        index: dict[str, CompositeEntry] = {}
        for entry in self._all_entries():
            qname = getattr(entry.node, "qualified_name", None)
            if qname:
                index[qname] = entry
        return index

    def has_qualified_name(self, qname: str) -> bool:
        """Check whether any node in the graph has the given qualified_name."""
        return qname in self._qname_index()

    # ── Empty namespace pruning ──────────────────────────────────────

    def _prune_empty_namespaces(self) -> None:
        """Remove namespace nodes that have no substantive content.

        A namespace is **substantive** if any of the following holds:

        * it has at least one non-COMPOSES reference (edge);
        * another entry references it;
        * it composes at least one non-namespace child;
        * it composes at least one namespace child that is itself
          substantive (transitive closure).

        Namespaces that fail all four checks are dead containers —
        they were pulled into the graph by the namespace-parent
        expansion but have no link back to the as-built code.

        This is called automatically from ``from_neo4j()`` after
        the graph is assembled.

        Note: uses ``type(node).__name__ == 'NamespaceNode'`` rather
        than ``isinstance(node, NamespaceNode)`` to stay consistent
        with label-based type checks used elsewhere (pure-Python
        model classes share the same label chain).
        """
        flat = self._flat_index()

        # Track which keys are substantive.  Build bottom-up so we
        # don't infinite-recurse on namespace cycles (unlikely, but
        # defensive).
        substantive: dict[str, bool] = {}

        def _is_namespace(entry: CompositeEntry) -> bool:
            return type(entry.node).__name__ == "NamespaceNode"

        def _is_substantive(key: str, entry: CompositeEntry) -> bool:
            if key in substantive:
                return substantive[key]

            # 1. Direct edges
            if entry.references:
                substantive[key] = True
                return True

            # 2. Incoming edges from other entries
            for other in flat.values():
                if other is entry:
                    continue
                for ref in other.references:
                    if ref[1] == key:
                        substantive[key] = True
                        return True

            # 3. Children: check for non-namespace or substantive namespace
            has_non_ns = False
            has_sub_ns = False
            for type_children in entry.children.values():
                for child_key, child_entry in type_children.items():
                    if not _is_namespace(child_entry):
                        has_non_ns = True
                    elif _is_substantive(child_key, child_entry):
                        has_sub_ns = True

            result = has_non_ns or has_sub_ns
            substantive[key] = result
            return result

        for entry in self._all_entries():
            if _is_namespace(entry):
                key = self._node_key(entry.node)
                _is_substantive(key, entry)

        # Prune non-substantive namespace entries.
        # Walk the tree and remove them from parents' children dicts.
        def _prune_from(entry: CompositeEntry) -> None:
            for type_name in list(entry.children.keys()):
                type_children = entry.children[type_name]
                for child_key in list(type_children.keys()):
                    child_entry = type_children[child_key]
                    if _is_namespace(child_entry):
                        if not substantive.get(child_key, False):
                            del type_children[child_key]
                        else:
                            _prune_from(child_entry)
                    else:
                        _prune_from(child_entry)
                if not type_children:
                    del entry.children[type_name]

        for entry in self.entries.values():
            _prune_from(entry)

        # Remove non-substantive root namespace entries
        for key in list(self.entries.keys()):
            entry = self.entries[key]
            if _is_namespace(entry) and not substantive.get(key, False):
                del self.entries[key]

    def merge(self, other: "LayerGraph") -> None:
        """Merge another LayerGraph into this one (mutates self).

        For each root entry in *other*:
        - If a node with the same ``qualified_name`` already exists in
          *self*, recursively merges children and references into the
          existing entry.
        - Otherwise, adds the entire subtree as a new root entry.

        Duplicate references are skipped; existing children take
        precedence over same-keyed incoming children.

        Args:
            other: A LayerGraph whose entries will be merged in.
        """
        self.known_keys = frozenset(
            set(self.known_keys)
            | set(other.known_keys)
            | set(other._flat_index())
        )
        # Pre-build index so it stays fresh as we mutate self.entries
        self_qnames = self._qname_index()

        def _merge_children(
            existing_children: dict,
            incoming_children: dict,
        ) -> None:
            """Recursively merge incoming children into existing."""
            for type_name, incoming_type_children in incoming_children.items():
                if type_name not in existing_children:
                    existing_children[type_name] = {}
                for child_key, child_entry in incoming_type_children.items():
                    child_qname = getattr(
                        child_entry.node, "qualified_name", None
                    )
                    if child_qname and child_qname in self_qnames:
                        # Child already exists — merge deeper
                        _merge_existing(
                            self_qnames[child_qname], child_entry
                        )
                    elif child_key not in existing_children[type_name]:
                        existing_children[type_name][child_key] = child_entry
                        # Index all newly-added entries in the subtree
                        for e in self._walk_entries(child_entry):
                            eqn = getattr(e.node, "qualified_name", None)
                            if eqn:
                                self_qnames[eqn] = e

        def _merge_existing(
            existing: CompositeEntry,
            incoming: CompositeEntry,
        ) -> None:
            """Merge references and children from incoming into existing."""
            # Merge references (skip duplicates)
            existing_refs = set(existing.references)
            for ref in incoming.references:
                if ref not in existing_refs:
                    existing.references.append(ref)
                    existing_refs.add(ref)

            existing.edge_attrs.update(incoming.edge_attrs)
            for edge in incoming.unresolved_edges:
                if edge not in existing.unresolved_edges:
                    existing.unresolved_edges.append(dict(edge))

            # Recursively merge children
            _merge_children(existing.children, incoming.children)

        # Walk other's root entries
        for key, entry in other.entries.items():
            qname = getattr(entry.node, "qualified_name", None)
            if qname and qname in self_qnames:
                # Merge into existing entry
                _merge_existing(self_qnames[qname], entry)
            elif key not in self.entries:
                # Add as a new root entry
                self.entries[key] = entry
                # Index the entire new subtree
                for e in self._walk_entries(entry):
                    eqn = getattr(e.node, "qualified_name", None)
                    if eqn:
                        self_qnames[eqn] = e

    def subgraph(self, qname: str) -> "LayerGraph":
        """Return a new LayerGraph scoped to a compound and its 1-hop neighbours.

        Finds the entry matching *qname*, includes its full composition
        subtree (children), and pulls in every directly-referenced target
        node from the full graph.  The result is a standalone LayerGraph
        suitable for class-scoped visualisation.

        Args:
            qname: Fully-qualified name of the compound (e.g.
                ``"cpp_sqlite::Database"``).

        Returns:
            A new LayerGraph containing the matched entry, its children,
            and all 1-hop neighbour entries.

        Raises:
            ValueError: If *qname* is not found in the graph.
        """
        flat = self._flat_index()
        qnames = self._qname_index()

        source_entry = qnames.get(qname)
        if source_entry is None:
            raise ValueError(f"No entry found for '{qname}'")

        source_key = self._node_key(source_entry.node)

        # 1. Walk the full subtree of the source entry (the compound
        #    plus all its members, nested types, etc.).
        subtree_keys: set[str] = set()
        for e in self._walk_entries(source_entry):
            subtree_keys.add(self._node_key(e.node))

        # Build a reverse index: child key → parent entry key so we
        # can pull in parent compounds when a member node is collected
        # as a 1-hop neighbour.
        child_to_parent: dict[str, str] = {}
        for parent_key, parent_entry in flat.items():
            for type_children in parent_entry.children.values():
                for child_key in type_children:
                    child_to_parent[child_key] = parent_key

        # 2. Collect all references from every node in the subtree.
        #    For each reference, pull the target entry from the flat
        #    index (if present).
        collected_entries: dict[str, CompositeEntry] = {}
        parent_reparent: dict[str, str] = {}  # member_key → parent_entry_key

        for key in subtree_keys:
            entry = flat.get(key)
            if entry is None:
                continue
            # Deep-copy this entry's subtree so we can place it under
            # the matching new entry.
            new_entry = CompositeEntry(
                node=entry.node,
                children=dict(entry.children),
                references=[],  # references rebuilt below
                edge_attrs=dict(entry.edge_attrs),
                unresolved_edges=[dict(edge) for edge in entry.unresolved_edges],
            )
            collected_entries[key] = new_entry

        # Copy references from the source tree and resolve neighbour
        # entries.
        for key in subtree_keys:
            entry = flat.get(key)
            if entry is None:
                continue
            new_entry = collected_entries[key]
            for rt, target_key, target_type in entry.references:
                new_entry.references.append((rt, target_key, target_type))
                if target_key in collected_entries:
                    continue  # already in subtree
                # Skip DEFINED_IN edges — FileNodes provide
                # location metadata, not structural dependencies.
                if rt == "DEFINED_IN":
                    continue
                target_entry = flat.get(target_key)
                if target_entry is not None:
                    collected_entries[target_key] = CompositeEntry(
                        node=target_entry.node,
                        children=dict(target_entry.children),
                        references=list(target_entry.references),
                        edge_attrs=dict(target_entry.edge_attrs),
                        unresolved_edges=[
                            dict(edge) for edge in target_entry.unresolved_edges
                        ],
                    )
                    # If the target is a member node, pull in its
                    # parent compound so it gets rendered as a member
                    # line rather than a standalone element.
                    if target_key in child_to_parent:
                        parent_key = child_to_parent[target_key]
                        parent_reparent[target_key] = parent_key
                        if parent_key not in collected_entries:
                            parent_entry = flat.get(parent_key)
                            if parent_entry is not None:
                                collected_entries[parent_key] = CompositeEntry(
                                    node=parent_entry.node,
                                    children={},  # container only; members reparented below
                                    references=list(parent_entry.references),
                                    edge_attrs=dict(parent_entry.edge_attrs),
                                    unresolved_edges=[
                                        dict(edge)
                                        for edge in parent_entry.unresolved_edges
                                    ],
                                )

        # 3. Reparent member nodes under their parent compound.
        #    Remove standalone member entries and nest them under the
        #    parent compound that was pulled in above.
        for member_key, parent_key in parent_reparent.items():
            member_entry = collected_entries.pop(member_key, None)
            parent_entry = collected_entries.get(parent_key)
            if member_entry is None or parent_entry is None:
                continue
            node_type = type(member_entry.node).__name__
            if node_type not in parent_entry.children:
                parent_entry.children[node_type] = {}
            parent_entry.children[node_type][member_key] = member_entry

        # 4. Build a new LayerGraph.  Root entries are any collected
        #    entries that are not children of another collected entry.
        parent_of: set[str] = set()
        for key, entry in collected_entries.items():
            for type_children in entry.children.values():
                for child_key in type_children:
                    parent_of.add(child_key)

        root_entries = {
            key: entry
            for key, entry in collected_entries.items()
            if key not in parent_of
        }

        return LayerGraph(
            tags=self.tags,
            entries=root_entries,
            known_keys=frozenset(set(self.known_keys) | set(flat)),
            _preferred_root_key=source_key,
        )

    def __len__(self) -> int:
        """Number of nodes in the graph (including children)."""
        return sum(1 for _ in self._all_entries())
