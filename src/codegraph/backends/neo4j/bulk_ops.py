"""Neo4j bulk operations — save/load LayerGraphs.

Extracted from ``codegraph.graph.LayerGraph.to_neo4j()`` and
``codegraph.graph.LayerGraph.from_neo4j()``.
"""

from __future__ import annotations

import logging
import os

from neomodel.sync_.node import StructuredNode

from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.backends.neo4j.node_ops import (
    Neo4jNodeOps,
    _build_save_payload,
    _node_labels,
)
from codegraph.backends.neo4j.rel_ops import Neo4jRelOps

from codegraph.graph import CompositeEntry
from codegraph.graph import LayerGraph
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode

log = logging.getLogger(__name__)

#: Batch size for UNWIND upserts — matches the pre-decoupling batched
#: Cypher write path (``write_result`` used batches of 1000).
_BATCH = 1000

#: Debug stage tracing (CODEGRAPH_DEBUG=1) — used to root-cause slow
#: integration fixtures; harmless no-op otherwise.
_DEBUG = os.environ.get("CODEGRAPH_DEBUG") == "1"

def _dbg(msg: str) -> None:
    if _DEBUG:
        print(f"[DBG bulk_ops] {msg}", flush=True)


class Neo4jBulkOps:
    """Bulk save/load operations for LayerGraph -> Neo4j."""

    def __init__(
        self,
        conn: Neo4jConnection,
        node_ops: Neo4jNodeOps,
        rel_ops: Neo4jRelOps,
    ):
        self._conn = conn
        self._node_ops = node_ops
        self._rel_ops = rel_ops

    def bulk_save(self, layer_graph: "LayerGraph") -> None:
        """Persist all nodes and relationships in a LayerGraph to Neo4j.

        Batched write path: nodes are upserted via UNWIND in batches of
        :data:`_BATCH` (one query per label per batch), and edges via
        UNWIND MATCH-by-element-id + MERGE in batches of :data:`_BATCH`
        (one query per relationship type per batch) — the same batching
        the pre-decoupling ``write_result`` used, and the write-side
        counterpart to the already-batched read helpers
        (``find_all_by_uids`` / ``get_edges_for_uids``).

        ``element_id_property`` is resolved back onto every saved node
        from the batch query results, so downstream callers that read
        ``node.element_id`` keep working (``rel_ops.connect`` semantics
        preserved).  Neomodel ``StructuredNode`` models (which manage
        their own relationship descriptors) fall back to the per-node
        ``save()`` / per-edge ``connect()`` paths.
        """

        entries = list(layer_graph._all_entries())
        if not entries:
            return

        # Build flat indexes for resolving reference targets.
        flat: dict[str, CompositeEntry] = {}
        qname_index: dict[str, CompositeEntry] = {}
        for entry in entries:
            key = LayerGraph._node_key(entry.node)
            flat[key] = entry
            qname = getattr(entry.node, "qualified_name", None)
            if qname:
                qname_index[qname] = entry

        # ── Phase 1: nodes — batched UNWIND upserts ──────────────────
        by_label: dict[str, list[CodeGraphNode]] = {}
        for entry in entries:
            node = entry.node
            if issubclass(type(node), StructuredNode):
                # Neomodel models: per-node path (own relationship managers).
                self._node_ops.save(node)
                continue
            labels = ":".join(_node_labels(type(node)))
            # Backtick each label so the label chain is valid Cypher
            # (``MERGE (n:`ClassNode`:`CompoundNode` {{uid: …}})``).
            by_label.setdefault(labels, []).append(node)

        for labels, nodes in by_label.items():
            for j in range(0, len(nodes), _BATCH):
                batch = nodes[j:j + _BATCH]
                rows = []
                for node in batch:
                    _, uid, props = _build_save_payload(node)
                    rows.append({"uid": uid, "props": props})
                label_clause = ":".join(f"`{l}`" for l in labels.split(":"))
                results, _ = self._conn.execute_raw(
                    f"UNWIND $rows AS row "
                    f"MERGE (n:{label_clause} {{uid: row.uid}}) "
                    f"SET n += row.props "
                    f"RETURN row.uid AS uid, elementId(n) AS eid",
                    {"rows": rows},
                )
                eid_by_uid = {row["uid"]: row["eid"] for row in results}
                for node in batch:
                    eid = eid_by_uid.get(node.uid)
                    if eid is not None:
                        node.element_id_property = eid

        # ── Phase 2: edges — batched UNWIND MERGEs ───────────────────
        edges: list[tuple[CodeGraphNode, str, CodeGraphNode]] = []
        for entry in entries:
            source_node = entry.node

            # Connect COMPOSES children
            for _target_type, type_children in entry.children.items():
                for _child_key, child_entry in type_children.items():
                    edges.append((source_node, "COMPOSES", child_entry.node))

            # Connect references
            for relation_type, target_key, _target_type in entry.references:
                target_entry = flat.get(target_key) or qname_index.get(target_key)
                if target_entry is not None:
                    edges.append((source_node, relation_type, target_entry.node))

        by_rel: dict[str, list[tuple[CodeGraphNode, CodeGraphNode]]] = {}
        for source, rel_type, target in edges:
            if issubclass(type(source), StructuredNode):
                # Neomodel models: per-edge path (relationship managers).
                self._rel_ops.connect(source, rel_type, target)
                continue
            by_rel.setdefault(rel_type, []).append((source, target))

        for rel_type, pairs in by_rel.items():
            for j in range(0, len(pairs), _BATCH):
                batch = pairs[j:j + _BATCH]
                rows = [
                    {"sid": s.element_id, "tid": t.element_id}
                    for s, t in batch
                ]
                self._conn.execute_raw(
                    f"UNWIND $rows AS row "
                    f"MATCH (s) WHERE elementId(s) = row.sid "
                    f"MATCH (t) WHERE elementId(t) = row.tid "
                    f"MERGE (s)-[:{rel_type}]->(t)",
                    {"rows": rows},
                )

    def bulk_load_by_tag(self, tag: str) -> list["CodeGraphNode"]:
        """Load all nodes with tag plus 1-hop neighbors.

        Returns a flat list of nodes.  Tree construction is done by
        ``LayerGraph.from_backend()``.

        Uses batched edge fetches (2 queries per uid-batch instead of
        per-node queries) and batched per-type target fetches — the
        big-data retrieval path.  Semantics match the per-node version:
        ``HAS_IMPLEMENTATION`` edges are skipped; the second pass pulls
        in incoming ``COMPOSES`` parents of non-tag-matched neighbours.
        """

        nodes: dict[str, "CodeGraphNode"] = {}
        uid_to_key: dict[str, str] = {}
        seen_uids: set[str] = set()

        # Fetch all tag-matched nodes
        _dbg(f"bulk_load_by_tag({tag!r}): find_all_by_tag...")
        matched_nodes = self._node_ops.find_all_by_tag(tag)
        _dbg(f"  matched {len(matched_nodes)} tag-matched nodes")

        for node in matched_nodes:
            key = _node_key_safe(node)
            nodes[key] = node
            uid = node._uid_value()
            if uid:
                uid_to_key[uid] = key
                seen_uids.add(uid)

        # Expand to first-level neighbors — batched edge fetch (2 queries).
        _dbg("  expanding 1-hop neighbors...")
        matched_uids = [n._uid_value() for n in matched_nodes if n._uid_value()]
        edges_by_uid = self._rel_ops.get_edges_for_uids(matched_uids)
        _dbg(f"  edge fetch done")
        pending: dict[str, list[str]] = {}  # target_type -> [uids]
        pending: dict[str, list[str]] = {}  # target_type -> [uids]
        for node in matched_nodes:
            uid = node._uid_value()
            for edge in edges_by_uid.get(uid, []):
                if edge.relation_type == "HAS_IMPLEMENTATION":
                    continue
                target_uid = edge.target_uid
                if target_uid not in seen_uids:
                    seen_uids.add(target_uid)
                    pending.setdefault(edge.target_type, []).append(target_uid)
        neighbors = self._fetch_batched(pending)
        _dbg(f"  fetched {len(neighbors)} neighbors")
        for nbr in neighbors:
            key = _node_key_safe(nbr)
            nodes[key] = nbr
            if nbr._uid_value():
                uid_to_key[nbr._uid_value()] = key

        # Second pass: pull in namespace parents of non-project 1-hop
        # neighbours.  ONLY ``NamespaceNode`` parents qualify — arbitrary
        # COMPOSES parents (e.g. an HLR composing its LLRs) would drag
        # unrelated requirements/scaffold trees into e.g. a design
        # export, breaking the design-closure invariant (every node
        # design-tagged or 1-hop from a design-tagged node).
        initial_uids = {n._uid_value() for n in matched_nodes}
        neighbor_uids = [n._uid_value() for n in neighbors if n._uid_value()]
        parent_edges = self._rel_ops.get_edges_for_uids(neighbor_uids)
        pending2: dict[str, list[str]] = {}
        for nbr in neighbors:
            nuid = nbr._uid_value()
            if nuid in initial_uids:
                continue
            for edge in parent_edges.get(nuid, []):
                if edge.relation_type != "COMPOSES":
                    continue
                if edge.is_outgoing:
                    continue  # only interested in incoming (parent→ns)
                target_uid = edge.target_uid
                target_cls = CodeGraphNode._registry.get(edge.target_type)
                if target_cls is None or not issubclass(target_cls, NamespaceNode):
                    continue
                if target_uid not in seen_uids:
                    seen_uids.add(target_uid)
                    pending2.setdefault(edge.target_type, []).append(target_uid)
        for parent in self._fetch_batched(pending2):
            key = _node_key_safe(parent)
            nodes[key] = parent
            if parent._uid_value():
                uid_to_key[parent._uid_value()] = key

        return list(nodes.values())

    def _fetch_batched(
        self,
        pending: dict[str, list[str]],
    ) -> list["CodeGraphNode"]:
        """Fetch nodes for ``{type_name: [uids]}`` with one query per type."""
        out: list["CodeGraphNode"] = []
        for type_name, uids in pending.items():
            target_cls = CodeGraphNode._registry.get(type_name)
            if target_cls is None:
                continue
            out.extend(self._node_ops.find_all_by_uids(target_cls, uids))
        return out


def _node_key_safe(obj) -> str:
    """Derive a stable local key from a node instance.

    Delegates to LayerGraph._node_key() but avoids circular imports
    by using the static version.
    """
    return LayerGraph._node_key(obj)
