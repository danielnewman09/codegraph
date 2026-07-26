"""Neo4j relationship operations.

Extracted from ``codegraph.models.tags.CodeGraphNode`` and
``codegraph.graph.__init__`` (connect/disconnect fallback logic).
"""

from __future__ import annotations


from neomodel import db

from codegraph.backends.interface import EdgeDescriptor
from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.models.tags import CodeGraphNode



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

        Uses ``_find_manager()`` to locate the correct neomodel relationship
        manager on *source*.  Raises ``ValueError`` if no matching
        relationship is declared — there is no fallback.
        """
        manager = self._find_manager(source, rel_type, target)
        manager.connect(target)

    def disconnect(
        self,
        source: "CodeGraphNode",
        rel_type: str,
        target: "CodeGraphNode",
    ) -> None:
        """Remove a single relationship between two nodes."""
        manager = self._find_manager(source, rel_type, target)
        manager.disconnect(target)

    # ── Relationship merge by uid ──────────────────────────────────

    def merge_relationship(
        self,
        source_uid: str,
        rel_type: str,
        target_uid: str,
    ) -> int:
        """Idempotently create a relationship between two nodes by uid.

        Returns 1 if the target was matched, 0 otherwise.
        """
        results, _ = db.cypher_query(
            f"MATCH (s), (t) "
            f"WHERE s.uid = $suid AND t.uid = $tuid "
            f"MERGE (s)-[:{rel_type}]->(t) "
            f"RETURN count(t) AS cnt",
            {"suid": source_uid, "tuid": target_uid},
        )
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

        Iterates all RelationshipTo descriptors where
        relation_type == "COMPOSES" and returns connected targets.
        """
        from neomodel import RelationshipTo

        if not hasattr(node, "element_id_property"):
            return []

        children: list["CodeGraphNode"] = []
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

    def get_all_edges(
        self,
        node: "CodeGraphNode",
    ) -> list[EdgeDescriptor]:
        """Return ALL edges (incoming + outgoing) from node."""
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
            resolve_objects=True,
        )

        edges: list[EdgeDescriptor] = []
        for row in results:
            target = row[0]
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

    # ── Relationship merge ─────────────────────────────────────────

    def merge_relationship(
        self, source_uid: str, rel_type: str, target_uid: str
    ) -> int:
        """MERGE a relationship between two nodes by uid."""
        results, _ = db.cypher_query(
            f"MATCH (s), (t) "
            f"WHERE s.uid = $suid AND t.uid = $tuid "
            f"MERGE (s)-[:{rel_type}]->(t) "
            f"RETURN count(t) AS cnt",
            {"suid": source_uid, "tuid": target_uid},
        )
        return results[0][0] if results else 0

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
