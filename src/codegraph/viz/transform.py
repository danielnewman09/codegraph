"""LayerGraph → Cytoscape elements transform.

Adapted from ticketing_system frontend_migrated/graph/format.py.
Walks the CompositeEntry tree to produce Cytoscape {{nodes, edges}}
dicts suitable for JSON serialisation.

Leaf members (methods, attributes, enum values) are collapsed into
their parent compound's UML HTML label rather than emitted as
separate Cytoscape nodes.
"""

from __future__ import annotations

from codegraph.constants import (
    COMPOUND_KINDS as CG_COMPOUND_KINDS_TUPLES,
    NAMESPACE_KINDS as CG_NAMESPACE_KINDS_TUPLES,
)
from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.viz.labels import (
    _CODEGRAPH_KIND_GROUP,
    _CODEGRAPH_STEREOTYPE_MAP,
    _ENTITY_KINDS,
    build_uml_html,
)

# ---------------------------------------------------------------------------
# Kind sets derived from codegraph.constants
# ---------------------------------------------------------------------------

_NAMESPACE_KINDS: frozenset[str] = frozenset(k for k, _ in CG_NAMESPACE_KINDS_TUPLES)
_COMPOUND_KINDS: frozenset[str] = frozenset(k for k, _ in CG_COMPOUND_KINDS_TUPLES)

# Node types to exclude from the visualisation entirely.
_EXCLUDED_NODE_TYPES: frozenset[str] = frozenset({
    "ImplementationNode",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_compound(node) -> bool:
    """Return True if the node represents a compound (class, struct, etc.)."""
    return getattr(node, "kind", "") in _COMPOUND_KINDS


def _is_namespace(node) -> bool:
    """Return True if the node represents a namespace-like kind."""
    return getattr(node, "kind", "") in _NAMESPACE_KINDS


def _is_excluded(node) -> bool:
    """Return True if this node type should not appear in the graph."""
    return type(node).__name__ in _EXCLUDED_NODE_TYPES


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def layer_graph_to_cytoscape(graph: LayerGraph) -> dict:
    """Walk a LayerGraph's CompositeEntry tree → Cytoscape {{nodes, edges}}.

    Args:
        graph: A :class:`LayerGraph` populated with nodes for a single
            tag (e.g. ``"design"``).

    Returns:
        A dict with ``"nodes"`` and ``"edges"`` keys, each a list of
        Cytoscape element data dicts.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    # Determine the layer name from graph tags (single tag per export).
    layer = next(iter(graph.tags)) if graph.tags else "design"

    for entry in graph.entries.values():
        if _is_excluded(entry.node):
            continue
        _walk_entry(entry, parent_id=None, nodes=nodes, edges=edges,
                    seen=seen, layer=layer)

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Tree walk
# ---------------------------------------------------------------------------


def _collect_skipped_member_refs(entry: CompositeEntry) -> list[tuple[str, str, str]]:
    """Collect references from leaf members that are collapsed into UML label.

    These members won't be walked by _walk_entry, so their references
    need to be collected here and re-attached to the parent compound.
    """
    refs: list[tuple[str, str, str]] = []
    for _type_key, children in entry.children.items():
        for _child_key, child_entry in children.items():
            child_kind = getattr(child_entry.node, "kind", "")
            # If this child will be walked as a separate node, skip it
            if child_kind in _ENTITY_KINDS or child_kind in _NAMESPACE_KINDS or _is_compound(child_entry.node):
                continue
            # Collect references from collapsed member
            for rel_type, tgt_key, tgt_type in child_entry.references:
                if tgt_type == "ImplementationNode":
                    continue
                refs.append((getattr(child_entry.node, "qualified_name", "") or
                            getattr(child_entry.node, "name", ""),
                            tgt_key, rel_type))
            # Recurse into member's children (e.g. nested locals)
            refs.extend(_collect_skipped_member_refs(child_entry))
    return refs


def _walk_entry(
    entry: CompositeEntry,
    parent_id: str | None,
    nodes: list[dict],
    edges: list[dict],
    seen: set[str],
    layer: str,
) -> None:
    """Recursively walk a CompositeEntry, emitting Cytoscape nodes and edges.

    Leaf members are NOT emitted as separate nodes — they are collapsed
    into their parent compound's UML label.  References from collapsed
    members ARE emitted as edges from the parent.
    """
    node = entry.node
    uid = node._uid_value()
    qname = uid if uid is not None else (getattr(node, "qualified_name", None) or getattr(node, "name", ""))
    if qname in seen:
        return
    seen.add(qname)

    # Build and emit the Cytoscape node
    cy_node = _build_node(entry, parent_id=parent_id, layer=layer)
    nodes.append(cy_node)

    # Emit this entry's own references
    for rel_type, target_key, target_type in entry.references:
        if target_type == "ImplementationNode":
            continue
        edges.append(_build_edge(qname, target_key, rel_type))

    # Emit references from collapsed members — use a counter
    # for unique edge IDs since multiple members may share target.
    member_edge_idx = 0
    for _src, tgt, rel in _collect_skipped_member_refs(entry):
        member_edge_idx += 1
        edges.append(_build_edge(qname, tgt, rel, suffix=f"_m{member_edge_idx}"))

    # Recurse into composed children that get their own nodes
    for _type_key, children in entry.children.items():
        for _child_key, child_entry in children.items():
            child_kind = getattr(child_entry.node, "kind", "")
            if child_kind not in _ENTITY_KINDS and child_kind not in _NAMESPACE_KINDS and not _is_compound(child_entry.node):
                continue
            child_parent = qname if _is_namespace(node) else parent_id
            _walk_entry(child_entry, parent_id=child_parent,
                       nodes=nodes, edges=edges, seen=seen, layer=layer)


# ---------------------------------------------------------------------------
# Node / edge builders
# ---------------------------------------------------------------------------


def _build_node(entry: CompositeEntry, parent_id: str | None, layer: str) -> dict:
    """Build a Cytoscape node data dict from a CompositeEntry."""
    node = entry.node
    # Use the same UID as LayerGraph._node_key for consistent edge target resolution.
    uid = node._uid_value()
    qname = uid if uid is not None else (getattr(node, "qualified_name", "") or getattr(node, "name", ""))
    name = getattr(node, "name", "")
    kind = getattr(node, "kind", "")

    data: dict = {
        "id": qname,
        "label": name,
        "qualified_name": qname,
        "kind": kind,
        "layer": layer,
    }

    if parent_id:
        data["parent"] = parent_id

    # Namespace nodes
    if _is_namespace(node):
        data["is_namespace"] = "true"
        return {"data": data}

    # Compound nodes with children → UML label
    if entry.children:
        by_kind = _build_member_data(entry, layer=layer)
        if by_kind:
            stereo_key = _CODEGRAPH_STEREOTYPE_MAP.get(kind, "")
            is_dep = (layer == "dependency")
            html_label = build_uml_html(
                name, by_kind, owner_kind=stereo_key, is_dependency=is_dep,
            )
            data["html_label"] = html_label
            data["has_members"] = "true"

    return {"data": data}


def _build_edge(source_qname: str, target_key: str, relation_type: str, suffix: str = "") -> dict:
    """Build a Cytoscape edge data dict."""
    return {
        "data": {
            "id": f"e_{source_qname}_{target_key}_{relation_type}{suffix}",
            "source": source_qname,
            "target": target_key,
            "label": relation_type,
        }
    }


def _build_member_data(entry: CompositeEntry, *, layer: str) -> dict[str, list[dict]]:
    """Extract member dicts from entry.children for UML label building.

    Groups by canonical UML kind using _CODEGRAPH_KIND_GROUP.
    Skips entity-kind children (nested classes, enums, etc.).

    Args:
        entry: The parent CompositeEntry whose children to extract.
        layer: The graph layer (e.g. ``"design"``, ``"dependency"``)
            to record on each member for type-origin markers.
    """
    by_kind: dict[str, list[dict]] = {}
    for _type_key, children in entry.children.items():
        for _child_key, child_entry in children.items():
            m_kind = getattr(child_entry.node, "kind", "")
            if m_kind in _ENTITY_KINDS:
                continue
            norm = _CODEGRAPH_KIND_GROUP.get(m_kind, m_kind)
            by_kind.setdefault(norm, []).append({
                "name": getattr(child_entry.node, "name", ""),
                "type_signature": getattr(child_entry.node, "type_signature", ""),
                "argsstring": getattr(child_entry.node, "argsstring", ""),
                "visibility": (
                    getattr(child_entry.node, "protection", "")
                    or getattr(child_entry.node, "visibility", "")
                ),
                "qualified_name": getattr(child_entry.node, "qualified_name", ""),
                "layer": layer,
            })
    return by_kind
