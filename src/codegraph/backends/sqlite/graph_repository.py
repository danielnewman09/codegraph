"""SqliteGraphRepository — SQLite implementation of the GraphRepository
abstract interface.

Composes ``SqliteNodeOps`` + ``SqliteRelOps``.  All SQL is sealed inside
the ops sub-modules; LayerGraph construction and filtering are pure
Python (shared shape with the Neo4j repository).
"""

from __future__ import annotations

from typing import Any, override

import sqlalchemy as sa

from codegraph.backends.sqlite.connection import SqliteConnection
from codegraph.backends.sqlite.node_ops import SqliteNodeOps
from codegraph.backends.sqlite.rel_ops import SqliteRelOps
from codegraph.constants import Tag
from codegraph.graph import CompositeEntry, LayerGraph
from codegraph.models.compound import (
    ClassNode,
    EnumNode,
    InterfaceNode,
    ModuleNode,
    UnionNode,
)
from codegraph.models.descriptors import PropertyRegistry
from codegraph.models.member import (
    AttributeNode,
    DefineNode,
    EnumValueNode,
    FunctionNode,
    MethodNode,
)
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

_COMPOUND_TYPES = [ClassNode, InterfaceNode, EnumNode, UnionNode, ModuleNode]
_MEMBER_TYPES = [MethodNode, AttributeNode, EnumValueNode, FunctionNode, DefineNode]
_NAMESPACE_TYPES = [NamespaceNode]


class SqliteGraphRepository(GraphRepository):
    """SQLite implementation of the GraphRepository interface."""

    def __init__(self, conn: SqliteConnection):
        self._conn = conn
        self._node_ops = SqliteNodeOps(conn)
        self._rel_ops = SqliteRelOps(conn)

    # ── uid / qualified_name resolution ───────────────────────────

    @override
    def resolve_uid(self, qualified_name: str) -> str | None:
        return self._node_ops.find_uid_by_qualified_name(qualified_name)

    @override
    def resolve_uid_by_name(self, name: str, *, label: str | None = None) -> str | None:
        return self._node_ops.find_uid_by_name(name, label=label)

    @override
    def resolve_qualified_name(self, uid: str) -> str | None:
        return self._node_ops.find_qualified_name_by_uid(uid)

    # ── Node lookup ───────────────────────────────────────────────

    @override
    def find_by_uid(self, uid: str) -> CodeGraphNode | None:
        return self._node_ops.find_by_uid(uid)

    @override
    def find_by_qualified_name(
        self, qualified_name: str
    ) -> CodeGraphNode | None:
        uid = self.resolve_uid(qualified_name)
        if uid is None:
            return None
        return self.find_by_uid(uid)

    @override
    def find_all_by_qualified_name(
        self, qualified_name: str
    ) -> list[CodeGraphNode]:
        return self._node_ops.find_all_by_qualified_name(qualified_name)

    # ── Node label operations ─────────────────────────────────────

    @override
    def get_labels(self, uid: str) -> set[str]:
        return self._node_ops.get_labels(uid)

    @override
    def set_labels(self, uid: str, labels: list[str]) -> None:
        self._node_ops.set_labels(uid, labels)

    @override
    def remove_labels(self, uid: str, labels: list[str]) -> None:
        self._node_ops.remove_labels(uid, labels)

    # ── Bulk queries ─────────────────────────────────────────────

    @override
    def get_all_node_labels(self) -> list[dict]:
        return self._node_ops.get_all_node_labels()

    @override
    def find_nodes_with_labels(self, labels: list[str]) -> list[dict]:
        return self._node_ops.find_nodes_with_labels(labels)

    @override
    def count_all_nodes(self, tag: str | None = None) -> int:
        """Count all nodes, optionally filtered by *tag*."""
        if tag:
            return len(self._node_ops.find_uids_by_tag(tag))
        return self._node_ops.count_all_nodes()

    # ── Node mutation ─────────────────────────────────────────────

    @override
    def update_properties(
        self, uid: str, props: dict, *, add_labels: list[str] | None = None
    ) -> bool:
        return self._node_ops.update_properties(uid, props, add_labels=add_labels)

    @override
    def delete_by_uid(self, uid: str) -> bool:
        return self._node_ops.delete_by_uid(uid)

    @override
    def delete_by_source(self, source: str) -> int:
        return self._node_ops.delete_by_source(source)

    @override
    def delete_by_uids(self, uids: list[str]) -> int:
        return self._node_ops.delete_by_uids(uids)

    # ── Relationships ─────────────────────────────────────────────

    @override
    def merge_relationship(
        self,
        source_uid: str,
        rel_type: str,
        target_uid: str,
        *,
        edge_properties: dict[str, object] | None = None,
    ) -> int:
        return self._rel_ops.merge_relationship(
            source_uid, rel_type, target_uid,
            edge_properties=edge_properties,
        )

    @override
    def merge_labeled_relationship(
        self,
        source_uid: str,
        source_label: str,
        rel_type: str,
        target_uid: str,
        target_label: str,
    ) -> None:
        # Labels are advisory in SQLite (uid is the canonical key) —
        # same idempotent MERGE via the UNIQUE triple.
        self._rel_ops.merge_relationship(source_uid, rel_type, target_uid)

    # ── Traversal ─────────────────────────────────────────────────

    @override
    def get_ancestors(
        self, uid: str, max_depth: int = 10
    ) -> list[dict]:
        return self._rel_ops.get_ancestors(uid, max_depth)

    @override
    def get_descendants(
        self, uid: str, max_depth: int = 10
    ) -> list[dict]:
        return self._rel_ops.get_descendants(uid, max_depth)

    # ── Tag queries ───────────────────────────────────────────────

    @override
    def find_uids_by_tag(self, tag: str) -> list[str]:
        return self._node_ops.find_uids_by_tag(tag)

    @override
    def find_uids_by_tag_and_condition(
        self,
        tag: str,
        *,
        condition_clause: str = "",
        params: dict | None = None,
    ) -> list[str]:
        return self._node_ops.find_uids_by_tag_condition(
            tag, condition_clause=condition_clause, params=params,
        )

    # ── Related-node queries ──────────────────────────────────────

    @override
    def find_related_nodes(
        self,
        target_uid: str,
        rel_pattern: str,
        *,
        source_labels: str | None = None,
    ) -> list[dict]:
        from codegraph.backends.sqlite.memory_ops import SqliteMemoryOps
        return SqliteMemoryOps(self._conn).find_related_nodes(
            target_uid, rel_pattern, source_labels=source_labels,
        )

    # ── Full-text search ──────────────────────────────────────────

    @override
    def search_fulltext(
        self,
        query: str,
        *,
        index_name: str,
        labels: str = "",
        tag: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        return self._node_ops.search_fulltext(
            query, index_name=index_name, labels=labels,
            tag=tag, limit=limit,
        )

    # ── Vector search ─────────────────────────────────────────────

    @override
    def search_vector(
        self,
        embedding: list[float],
        *,
        index_name: str,
        labels: str = "",
        tag: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        return self._node_ops.search_vector(
            embedding, index_name=index_name, labels=labels,
            tag=tag, limit=limit,
        )

    # ── Scope-based reads ─────────────────────────────────────────

    @override
    def get_by_tag(self, tag: Tag) -> LayerGraph:
        seeds = self._node_ops.find_all_by_tag(tag)
        return self._build_layer_graph(seeds)

    @override
    def get_by_source(self, source: str) -> LayerGraph:
        seeds = self._node_ops.find_all_by_source(source)
        return self._build_layer_graph(seeds)

    @override
    def get_by_namespace(self, qualified_name: str) -> LayerGraph:
        ns = self._node_ops.get(NamespaceNode, qualified_name=qualified_name)
        if ns is None:
            return LayerGraph(tags=frozenset({"design"}))
        seeds = [ns] + self._rel_ops.get_composed_children(ns)
        return self._build_layer_graph(seeds)

    @override
    def get_by_compound(self, qualified_name: str) -> LayerGraph:
        compound = self._get_node_by_qualified_name(qualified_name)
        if compound is None:
            return LayerGraph(tags=frozenset({"design"}))
        return self._build_layer_graph([compound])

    @override
    def get_by_neighbourhood(self, qualified_name: str) -> LayerGraph:
        node = self._get_node_by_qualified_name(qualified_name)
        if node is None:
            node = self._get_member_by_qualified_name(qualified_name)
        if node is None:
            return LayerGraph(tags=frozenset({"design"}))
        return self._build_layer_graph([node])

    @override
    def get_by_kind(
        self, kind: str, tag: Tag | None = None
    ) -> LayerGraph:
        seeds = self._node_ops.find_all_by_kind(kind, tag)
        return self._build_layer_graph(seeds)

    @override
    def get_hlr_subtree(self, uid: str, tag: str = "") -> LayerGraph:
        from codegraph_requirements.models import HLR

        hlr = self._node_ops.get(HLR, uid=uid)
        if hlr is None:
            return LayerGraph(tags=frozenset({"design"}))

        seen_uids: set[str] = set()
        queue: list[CodeGraphNode] = [hlr]
        composes_reachable: list[CodeGraphNode] = []

        while queue:
            node = queue.pop(0)
            node_uid = node._uid_value()
            if not node_uid or node_uid in seen_uids:
                continue
            seen_uids.add(node_uid)
            composes_reachable.append(node)

            for child in self._rel_ops.get_composed_children(node):
                child_uid = child._uid_value()
                if child_uid and child_uid not in seen_uids:
                    queue.append(child)

        graph = self._build_layer_graph(composes_reachable)

        if tag:
            graph = _filter_graph_by_tag(graph, tag)

        return graph

    # ── Flat queries ──────────────────────────────────────────────

    @override
    def find_by_tag(
        self, node_type: type[CodeGraphNode], tag: str
    ) -> list[CodeGraphNode]:
        return self._node_ops.find_by_tag(node_type, tag)

    @override
    def find_all_by_tag(self, tag: str) -> list[CodeGraphNode]:
        return self._node_ops.find_all_by_tag(tag)

    @override
    def find_all_by_source(self, source: str) -> list[CodeGraphNode]:
        return self._node_ops.find_all_by_source(source)

    @override
    def find_all_by_kind(
        self, kind: str, tag: str | None = None
    ) -> list[CodeGraphNode]:
        return self._node_ops.find_all_by_kind(kind, tag)

    # ── Relationship traversal ────────────────────────────────────

    @override
    def composed_children(
        self,
        node: CodeGraphNode,
        child_type: type[CodeGraphNode],
    ) -> list[CodeGraphNode]:
        return [
            c for c in self._rel_ops.get_composed_children(node)
            if isinstance(c, child_type)
        ]

    @override
    def incoming_composers(
        self,
        node: CodeGraphNode,
        composer_type: type[CodeGraphNode] | None = None,
    ) -> list[CodeGraphNode]:
        edges = self._rel_ops.get_all_edges(node)
        composers: list[CodeGraphNode] = []
        for e in edges:
            if e.relation_type != "COMPOSES" or e.is_outgoing:
                continue
            target_cls = CodeGraphNode._registry.get(e.target_type)
            if target_cls is None:
                continue
            if composer_type is not None and target_cls is not composer_type:
                continue
            composer = self._node_ops.get(target_cls, uid=e.target_uid)
            if composer is not None:
                composers.append(composer)
        return composers

    @override
    def outgoing_by_relation(
        self,
        node: CodeGraphNode,
        relation_type: str,
        target_type: type[CodeGraphNode] | None = None,
    ) -> list[CodeGraphNode]:
        edges = self._rel_ops.get_all_edges_outgoing(node)
        targets: list[CodeGraphNode] = []
        for e in edges:
            if e.relation_type != relation_type:
                continue
            target_cls = CodeGraphNode._registry.get(e.target_type)
            if target_cls is None:
                continue
            if target_type is not None and target_cls is not target_type:
                continue
            target = self._node_ops.get(target_cls, uid=e.target_uid)
            if target is not None:
                targets.append(target)
        return targets

    # ── Write ─────────────────────────────────────────────────────

    @override
    def save_layer_graph(self, graph: LayerGraph) -> None:
        from codegraph.backends.sqlite.bulk_ops import SqliteBulkOps
        bulk = SqliteBulkOps(self._conn, self._node_ops, self._rel_ops)
        bulk.bulk_save(graph)

    # ── Aggregation ──────────────────────────────────────────────

    @override
    def count_relationships(
        self,
        rel_types: list[str],
        *,
        source_labels: list[str] | None = None,
        target_labels: list[str] | None = None,
        target_tag: str | None = None,
    ) -> int:
        """Count relationships whose type is in *rel_types*."""
        if not rel_types:
            return 0
        sql = (
            "SELECT COUNT(*) AS c FROM edges e "
            "JOIN nodes s ON s.id = e.source_id "
            "JOIN nodes t ON t.id = e.target_id "
        )
        binds = ", ".join(f":rt{i}" for i in range(len(rel_types)))
        params: dict[str, Any] = {f"rt{i}": rt for i, rt in enumerate(rel_types)}
        where = [f"e.rel_type IN ({binds})"]
        if source_labels:
            sl = ", ".join(f":sl{i}" for i in range(len(source_labels)))
            sql += "JOIN node_labels snl ON snl.node_id = s.id "
            where.append(f"snl.label IN ({sl})")
            params.update({f"sl{i}": l for i, l in enumerate(source_labels)})
        if target_labels:
            tl = ", ".join(f":tl{i}" for i in range(len(target_labels)))
            sql += "JOIN node_labels tnl ON tnl.node_id = t.id "
            where.append(f"tnl.label IN ({tl})")
            params.update({f"tl{i}": l for i, l in enumerate(target_labels)})
        if target_tag:
            sql += "JOIN node_tags tt ON tt.node_id = t.id "
            where.append("tt.tag = :ttag")
            params["ttag"] = target_tag
        with self._conn.connect() as conn:
            row = conn.execute(sa.text(sql + " WHERE " + " AND ".join(where)), params).first()
        return row[0] if row else 0

    # ── Private helpers ───────────────────────────────────────────

    def _get_node_by_qualified_name(
        self, qualified_name: str
    ) -> CodeGraphNode | None:
        for node_cls in _COMPOUND_TYPES + _NAMESPACE_TYPES:
            node = self._node_ops.get(node_cls, qualified_name=qualified_name)
            if node is not None:
                return node
        return None

    def _get_member_by_qualified_name(
        self, qualified_name: str
    ) -> CodeGraphNode | None:
        for node_cls in _MEMBER_TYPES:
            node = self._node_ops.get(node_cls, qualified_name=qualified_name)
            if node is not None:
                return node
        return None

    def _build_layer_graph(
        self, seeds: list[CodeGraphNode]
    ) -> LayerGraph:
        """Build a LayerGraph from seed nodes plus 1-hop neighbours."""
        nodes: dict[str, CodeGraphNode] = {}
        uid_to_key: dict[str, str] = {}

        for node in seeds:
            key = LayerGraph._node_key(node)
            nodes[key] = node
            uid = node._uid_value()
            if uid:
                uid_to_key[uid] = key

        for node in list(seeds):
            for edge_info in self._rel_ops.get_all_edges(node):
                if edge_info.relation_type == "HAS_IMPLEMENTATION":
                    continue
                target_uid = edge_info.target_uid
                target_type = edge_info.target_type
                if target_uid not in uid_to_key:
                    target_cls = CodeGraphNode._registry.get(target_type)
                    if target_cls:
                        neighbor = self._node_ops.get(target_cls, uid=target_uid)
                        if neighbor:
                            neighbor_key = LayerGraph._node_key(neighbor)
                            nodes[neighbor_key] = neighbor
                            uid_to_key[target_uid] = neighbor_key

        key_to_entry: dict[str, CompositeEntry] = {}
        for key, node in nodes.items():
            key_to_entry[key] = CompositeEntry(node=node)

        child_keys: set[str] = set()
        for key, node in nodes.items():
            entry = key_to_entry[key]
            for child in self._rel_ops.get_composed_children(node):
                child_key = LayerGraph._node_key(child)
                if child_key not in key_to_entry:
                    continue
                child_entry = key_to_entry[child_key]
                child_type = type(child).__name__
                entry.children.setdefault(child_type, {})[child_key] = child_entry
                child_keys.add(child_key)

            for edge_info in self._rel_ops.get_all_edges(node):
                relation_type = edge_info.relation_type
                if relation_type in ("COMPOSES", "HAS_IMPLEMENTATION"):
                    continue
                target_key = uid_to_key.get(edge_info.target_uid)
                if target_key and target_key in key_to_entry:
                    entry.references.append(
                        (relation_type, target_key, edge_info.target_type)
                    )

        root_entries = {
            key: entry
            for key, entry in key_to_entry.items()
            if key not in child_keys
        }

        all_tags: set[str] = set()
        for node in seeds:
            if PropertyRegistry.has_property(type(node), "tags"):
                node_tags = getattr(node, "tags", None)
                if node_tags:
                    all_tags.update(node_tags)
        tags = frozenset(all_tags) if all_tags else frozenset({"design"})

        return LayerGraph(tags=tags, entries=root_entries)


# ══════════════════════════════════════════════════════════════════════════
# Filter helpers (pure Python — no SQL)
# ══════════════════════════════════════════════════════════════════════════


def _filter_graph_by_tag(graph: LayerGraph, tag: str) -> LayerGraph:
    """Filter a LayerGraph to only entries whose node carries *tag*,
    plus their ancestors (to preserve tree structure)."""
    tagged_keys: set[str] = set()

    def _collect_tagged(entry) -> None:
        key = LayerGraph._node_key(entry.node)
        node_tags: list[str] = getattr(entry.node, "tags", None) or []
        if tag in node_tags:
            tagged_keys.add(key)
        for type_children in entry.children.values():
            for child_entry in type_children.values():
                _collect_tagged(child_entry)

    for entry in graph.entries.values():
        _collect_tagged(entry)

    if not tagged_keys:
        return LayerGraph(tags=graph.tags)

    keep_keys: set[str] = set()

    def _walk(entry, path: list[str]) -> bool:
        key = LayerGraph._node_key(entry.node)
        has_tag = key in tagged_keys
        descendant_has = False
        for type_children in entry.children.values():
            for child_key, child_entry in type_children.items():
                if _walk(child_entry, path + [key]):
                    descendant_has = True
        if has_tag or descendant_has:
            keep_keys.add(key)
            keep_keys.update(path)
            return True
        return False

    for entry in graph.entries.values():
        _walk(entry, [])

    filtered: dict = {}

    def _prune(entry):
        key = LayerGraph._node_key(entry.node)
        if key not in keep_keys:
            return None
        new_entry = CompositeEntry(node=entry.node)
        new_entry.references = list(entry.references)
        for child_type, type_children in entry.children.items():
            for child_key, child_entry in type_children.items():
                if child_key in keep_keys:
                    pruned = _prune(child_entry)
                    if pruned is not None:
                        new_entry.children.setdefault(child_type, {})[child_key] = pruned
        return new_entry

    for key, entry in graph.entries.items():
        if key in keep_keys:
            pruned = _prune(entry)
            if pruned is not None:
                filtered[key] = pruned

    return LayerGraph(tags=graph.tags, entries=filtered)
