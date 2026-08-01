"""Neo4j relationship operations.

Extracted from ``codegraph.models.tags.CodeGraphNode`` and
``codegraph.graph.__init__`` (connect/disconnect fallback logic).
"""

from __future__ import annotations


from neomodel import db
from neomodel.sync_.node import StructuredNode

from codegraph.backends.interface import EdgeDescriptor
from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.models.tags import CodeGraphNode
from codegraph.models.descriptors import (
    PropertyRegistry,
    Relationship as CGRelationship,
)


def _labels_for(cls: type) -> list[str]:
    """Return Neo4j labels for a node type (neomodel or pure-Python)."""
    if hasattr(cls, "inherited_labels"):
        return cls.inherited_labels()
    return [cls.__name__]



class Neo4jRelOps:
    """Relationship CRUD operations for the Neo4j backend."""

    def __init__(self, conn: Neo4jConnection):
        self._conn = conn

    # ── Relationship management ──────────────────────────────────────

    def connect(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
    ) -> None:
        """Create a relationship between two saved nodes.

        Uses neomodel relationship managers for neomodel classes;
        uses raw Cypher MERGE for pure-Python classes.

        Raises ``ValueError`` if no matching relationship is declared
        on a neomodel source — there is no fallback.  Pure-Python
        sources connect via raw Cypher without declaration checks
        (the declaration is advisory metadata).
        """
        if issubclass(type(source), StructuredNode):
            manager = self._find_manager(source, rel_type, target)
            manager.connect(target)
            return
        # Pure-Python: raw Cypher MERGE by element id
        if not hasattr(source, "element_id_property") or not hasattr(target, "element_id_property"):
            raise ValueError(
                f"Cannot connect unsaved nodes: source saved="
                f"{hasattr(source, 'element_id_property')}, "
                f"target saved={hasattr(target, 'element_id_property')}"
            )
        db.cypher_query(
            f"MATCH (s), (t) "
            f"WHERE elementId(s) = $sid AND elementId(t) = $tid "
            f"MERGE (s)-[:{rel_type}]->(t)",
            {"sid": source.element_id, "tid": target.element_id},
        )

    def disconnect(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
    ) -> None:
        """Remove a single relationship between two nodes."""
        if issubclass(type(source), StructuredNode):
            manager = self._find_manager(source, rel_type, target)
            manager.disconnect(target)
            return
        # Pure-Python: raw Cypher DELETE by element id
        if not hasattr(source, "element_id_property") or not hasattr(target, "element_id_property"):
            return
        db.cypher_query(
            f"MATCH (s)-[r:{rel_type}]->(t) "
            f"WHERE elementId(s) = $sid AND elementId(t) = $tid "
            f"DELETE r",
            {"sid": source.element_id, "tid": target.element_id},
        )

    # ── Relationship merge by uid ──────────────────────────────────

    def merge_relationship(
        self,
        source_uid: str,
        rel_type: str,
        target_uid: str,
        *,
        edge_properties: dict[str, object] | None = None,
    ) -> int:
        """Idempotently create a relationship between two nodes by uid.

        Optionally sets *edge_properties* on the relationship.
        Returns 1 if the target was matched, 0 otherwise.
        """
        parts = [
            f"MATCH (s), (t) ",
            f"WHERE s.uid = $suid AND t.uid = $tuid ",
            f"MERGE (s)-[r:{rel_type}]->(t) ",
        ]
        if edge_properties:
            props_clause = ", ".join(
                f"r.{k} = $ep_{k}" for k in edge_properties
            )
            parts.append(f"ON CREATE SET {props_clause} ")
            parts.append(f"ON MATCH SET {props_clause} ")
        parts.append("RETURN count(t) AS cnt")

        params: dict = {"suid": source_uid, "tuid": target_uid}
        if edge_properties:
            for k, v in edge_properties.items():
                params[f"ep_{k}"] = v

        results, _ = db.cypher_query(" ".join(parts), params)
        return results[0][0] if results else 0

    # ── Traversal ───────────────────────────────────────────────────

    def get_ancestors(
        self, uid: str, max_depth: int = 10
    ) -> list[dict]:
        """Walk COMPOSES edges upward from uid.

        Returns a list of {"uid": str, "labels": list[str]} dicts.
        """
        results, _ = db.cypher_query(
            f"MATCH (target)<-[:COMPOSES*1..{max_depth}]-(ancestor) "
            "WHERE target.uid = $uid "
            "RETURN ancestor.uid AS uid, labels(ancestor) AS labels",
            {"uid": uid},
        )
        return [
            {"uid": r[0], "labels": r[1]}
            for r in results
        ]

    def get_descendants(
        self, uid: str, max_depth: int = 10
    ) -> list[dict]:
        """Walk COMPOSES edges downward from uid.

        Returns a list of {"uid": str, "labels": list[str]} dicts.
        """
        results, _ = db.cypher_query(
            f"MATCH (parent)-[:COMPOSES*1..{max_depth}]->(descendant) "
            "WHERE parent.uid = $uid "
            "RETURN descendant.uid AS uid, labels(descendant) AS labels",
            {"uid": uid},
        )
        return [
            {"uid": r[0], "labels": r[1]}
            for r in results
        ]

    # ── Relationship queries ─────────────────────────────────────────

    def get_composed_children(
        self,
        node: "CodeGraphNode",
    ) -> list["CodeGraphNode"]:
        """Return all nodes reachable via outgoing COMPOSES edges.

        Iterates relationship descriptors (new ``Relationship`` and
        neomodel ``RelationshipTo``) where relation_type == "COMPOSES"
        and returns connected targets.  For pure-Python classes the
        traversal is raw Cypher.
        """
        if not hasattr(node, "element_id_property"):
            return []

        if issubclass(type(node), StructuredNode):
            from neomodel import RelationshipTo

            children: list[CodeGraphNode] = []
            seen: set[str] = set()
            for klass in type(node).__mro__:
                for name, val in vars(klass).items():
                    if not isinstance(val, RelationshipTo):
                        continue
                    if val.definition["relation_type"] != "COMPOSES":
                        continue
                    if name in seen:
                        continue
                    seen.add(name)
                    children.extend(getattr(node, name).all())
            return children

        # Pure-Python: raw Cypher by element id
        from codegraph.backends.neo4j.node_ops import Neo4jNodeOps

        node_ops = Neo4jNodeOps(self._conn)
        results, _ = db.cypher_query(
            "MATCH (n)-[:COMPOSES]->(c) "
            "WHERE elementId(n) = $eid RETURN c",
            {"eid": node.element_id},
        )
        children = []
        for row in results:
            raw = row[0]
            if raw is None:
                continue
            child = node_ops._inflate_by_labels(raw)
            if child is not None:
                children.append(child)
        return children

    def get_all_edges(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return ALL edges (incoming + outgoing) from node."""
        if not hasattr(node, "element_id_property"):
            return []

        if not issubclass(type(node), StructuredNode):
            return self._query_all_edges_raw(node)

        from neomodel import RelationshipTo, RelationshipFrom

        edges: list[EdgeDescriptor] = []
        seen: set[str] = set()
        for klass in type(node).__mro__:
            for name, val in vars(klass).items():
                if not isinstance(val, (RelationshipTo, RelationshipFrom)):
                    continue
                if name in seen:
                    continue
                seen.add(name)

                is_outgoing = isinstance(val, RelationshipTo)
                target_cls = val.definition.get("node_class")
                if target_cls is not None and not hasattr(target_cls, "__label__"):
                    # Abstract target type (e.g. CodeGraphNode) —
                    # use a Cypher fallback without label filtering.
                    edges.extend(
                        self._query_edges_by_element_id(
                            node, val, is_outgoing
                        )
                    )
                    continue

                manager = getattr(node, name)
                for target in manager.all():
                    edges.append(EdgeDescriptor(
                        relation_type=val.definition["relation_type"],
                        target_uid=target._uid_value(),
                        target_type=type(target).__name__,
                        is_outgoing=is_outgoing,
                    ))

        return edges

    def get_all_edges_outgoing(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return only outgoing edges from node."""
        if not hasattr(node, "element_id_property"):
            return []

        if not issubclass(type(node), StructuredNode):
            return self._query_edges_raw(node, outgoing=True)

        from neomodel import RelationshipTo

        edges: list[EdgeDescriptor] = []
        seen: set[str] = set()
        for klass in type(node).__mro__:
            for name, val in vars(klass).items():
                if not isinstance(val, RelationshipTo):
                    continue
                if name in seen:
                    continue
                seen.add(name)

                target_cls = val.definition.get("node_class")
                if target_cls is not None and not hasattr(target_cls, "__label__"):
                    # Abstract target type (e.g. CodeGraphNode) —
                    # use a Cypher fallback without label filtering.
                    edges.extend(
                        self._query_edges_by_element_id(
                            node, val, is_outgoing=True
                        )
                    )
                    continue

                manager = getattr(node, name)
                connected = manager.all()
                for target in connected:
                    edges.append(EdgeDescriptor(
                        relation_type=val.definition["relation_type"],
                        target_uid=target._uid_value(),
                        target_type=type(target).__name__,
                        is_outgoing=True,
                    ))
        return edges

    # ── Private helpers ──────────────────────────────────────────────

    def _query_all_edges_raw(
        self, node: "CodeGraphNode"
    ) -> list[EdgeDescriptor]:
        """Return all edges (incoming + outgoing) via raw Cypher.

        Used for pure-Python classes whose relationship descriptors
        are ``codegraph.models.descriptors.Relationship``.
        """
        outgoing = self._query_edges_raw(node, outgoing=True)
        incoming = self._query_edges_raw(node, outgoing=False)
        return outgoing + incoming

    def _query_edges_raw(
        self,
        node: "CodeGraphNode",
        outgoing: bool,
    ) -> list[EdgeDescriptor]:
        """Query edges of a pure-Python node by element id."""
        if outgoing:
            cypher = (
                f"MATCH (n)-[r]->(t) WHERE elementId(n)=$eid "
                "RETURN type(r) AS rel_type, t.uid AS tuid, labels(t) AS tlbls"
            )
        else:
            cypher = (
                f"MATCH (t)-[r]->(n) WHERE elementId(n)=$eid "
                "RETURN type(r) AS rel_type, t.uid AS tuid, labels(t) AS tlbls"
            )
        results, _ = db.cypher_query(cypher, {"eid": node.element_id})
        edges: list[EdgeDescriptor] = []
        for row in results:
            rel_type, tuid, tlbls = row[0], row[1], row[2]
            # Determine the most specific registered class from labels
            target_type = "CodeGraphNode"
            labels = set(tlbls or set())
            from codegraph.backends.neo4j.node_ops import best_class_for_labels

            best = best_class_for_labels(labels)
            if best is not None:
                target_type = best.__name__
            edges.append(EdgeDescriptor(
                relation_type=rel_type,
                target_uid=tuid,
                target_type=target_type,
                is_outgoing=outgoing,
            ))
        return edges

    @staticmethod
    def _query_edges_by_element_id(
        node: "CodeGraphNode",
        val,
        is_outgoing: bool,
    ) -> list[EdgeDescriptor]:
        """Query edges for a relationship targeting an abstract type.

        When a RelationshipTo/From targets an abstract type like
        ``CodeGraphNode`` that has no ``__label__``, ``manager.all()``
        fails because neomodel can't build a label-qualified MATCH.
        Instead we query by elementId without a target-label filter.
        """
        from neomodel import db as neomodel_db

        rel_type = val.definition["relation_type"]

        if is_outgoing:
            cypher = (
                f"MATCH (n)-[r:`{rel_type}`]->(target) "
                f"WHERE elementId(n)=$eid "
                f"RETURN target"
            )
        else:
            cypher = (
                f"MATCH (target)-[r:`{rel_type}`]->(n) "
                f"WHERE elementId(n)=$eid "
                f"RETURN target"
            )

        results, _ = neomodel_db.cypher_query(
            cypher,
            {"eid": node.element_id},
        )

        from codegraph.backends.neo4j.node_ops import Neo4jNodeOps

        node_ops = Neo4jNodeOps(self._conn)
        edges: list[EdgeDescriptor] = []
        for row in results:
            target = node_ops._inflate_by_labels(row[0])
            if target is None:
                continue
            edges.append(EdgeDescriptor(
                relation_type=rel_type,
                target_uid=target._uid_value(),
                target_type=type(target).__name__,
                is_outgoing=is_outgoing,
            ))
        return edges

    @staticmethod
    def _find_manager(
        source: "CodeGraphNode",
        relation_type: str,
        target: "CodeGraphNode",
    ):
        """Find the relationship manager on source matching both
        relation_type and the class of target.

        Extracted from CodeGraphNode.find_relationship_manager().
        """
        from neomodel import RelationshipTo, RelationshipFrom

        target_cls = type(target)
        for klass in type(source).__mro__:
            for name, val in vars(klass).items():
                if isinstance(val, (RelationshipTo, RelationshipFrom)):
                    if val.definition["relation_type"] != relation_type:
                        continue
                    rel_target = val.definition.get("model") or val._raw_class
                    if rel_target == target_cls or (
                        isinstance(rel_target, type)
                        and issubclass(target_cls, rel_target)
                    ):
                        return getattr(source, name)
                    if isinstance(rel_target, str) and (
                        rel_target == target_cls.__name__
                        or rel_target.endswith(f".{target_cls.__name__}")
                    ):
                        return getattr(source, name)
        raise ValueError(
            f"No '{relation_type}' relationship from "
            f"{type(source).__name__} to {target_cls.__name__}"
        )

    # ── Traversal ─────────────────────────────────────────────────

    def get_ancestors(
        self, uid: str, max_depth: int = 10
    ) -> list[dict]:
        """Walk COMPOSES edges upward from uid."""
        results, _ = db.cypher_query(
            f"MATCH (target)<-[:COMPOSES*1..{max_depth}]-(ancestor) "
            "WHERE target.uid = $uid "
            "RETURN ancestor.uid AS uid, labels(ancestor) AS labels",
            {"uid": uid},
        )
        return [{"uid": r[0], "labels": r[1]} for r in results]

    def get_descendants(
        self, uid: str, max_depth: int = 10
    ) -> list[dict]:
        """Walk COMPOSES edges downward from uid."""
        results, _ = db.cypher_query(
            f"MATCH (parent)-[:COMPOSES*1..{max_depth}]->(descendant) "
            "WHERE parent.uid = $uid "
            "RETURN descendant.uid AS uid, labels(descendant) AS labels",
            {"uid": uid},
        )
        return [{"uid": r[0], "labels": r[1]} for r in results]
