"""Neo4j requirements-layer operations.

Requirements-specific Cypher for HLR/LLR/TestNode tree traversal,
scaffold lifecycle, and verification edge management.

Separated from node_ops/rel_ops to keep domain boundaries clean.
"""

from __future__ import annotations

from neomodel import db

from codegraph.backends.neo4j.connection import Neo4jConnection


class Neo4jRequirementsOps:
    """Requirements-layer operations for the Neo4j backend."""

    def __init__(self, conn: Neo4jConnection):
        self._conn = conn

    # ── HLR/LLR/Test tree traversal ───────────────────────────────

    def get_hlr_tree(self, hlr_uid: str) -> list:
        """Return full HLR→LLRs→TestNodes tree with resolved targets.

        Returns raw rows: [(hlr, llr, test, verifies_target, step, step_target)].
        Grouping into a nested dict is done in the repository.
        """
        results, _ = db.cypher_query(
            "MATCH (hlr:HLR)-[:COMPOSES]->(llr:LLR) "
            "WHERE hlr.canonical_key = $key "
            "OPTIONAL MATCH (llr)-[:COMPOSES]->(test:TestNode) "
            "OPTIONAL MATCH (test)-[:VERIFIES]->(verifies_target) "
            "OPTIONAL MATCH (test)-[:COMPOSES]->(step:TestStepNode) "
            "OPTIONAL MATCH (step)-[:CALLEE]->(step_target) "
            "RETURN hlr, llr, test, verifies_target, step, step_target "
            "ORDER BY llr.name, test.test_name, step.order",
            {"uid": hlr_uid},
        )
        return results

    # ── Scaffold queries ──────────────────────────────────────────

    def find_scaffold_uids(self) -> list[str]:
        """Return all scaffold node uids."""
        results, _ = db.cypher_query(
            "MATCH (n) WHERE 'scaffold' IN coalesce(n.tags, []) "
            "RETURN n.canonical_key AS uid",
        )
        return [r[0] for r in results]

    def find_scaffold_with_references(self) -> list[str]:
        """Return scaffold uids that have incoming reference edges."""
        edge_list = ", ".join(
            f"'{e}'" for e in
            ["LEFT_OPERAND", "RIGHT_OPERAND", "CALLEE", "CALLER"]
        )
        results, _ = db.cypher_query(
            "MATCH (n) WHERE 'scaffold' IN coalesce(n.tags, []) "
            f"AND EXISTS {{ MATCH ()-[r]->(n) WHERE type(r) IN [{edge_list}] }} "
            "RETURN n.canonical_key AS uid",
        )
        return [r[0] for r in results]

    def find_scaffold_without_relationships(self) -> list[str]:
        """Return scaffold uids with no relationships."""
        results, _ = db.cypher_query(
            "MATCH (n) WHERE 'scaffold' IN coalesce(n.tags, []) "
            "AND NOT EXISTS { MATCH (n)-[r]-() } "
            "RETURN n.canonical_key AS uid",
        )
        return [r[0] for r in results]

    def find_scaffold_parents_of_referenced(
        self, referenced_uids: list[str]
    ) -> list[str]:
        """Return uids of scaffold ClassNode parents with referenced children."""
        if not referenced_uids:
            return []
        results, _ = db.cypher_query(
            "MATCH (parent:ClassNode)-[:COMPOSES]->(child) "
            "WHERE 'scaffold' IN parent.tags "
            "AND child.canonical_key IN $keys "
            "RETURN DISTINCT parent.canonical_key AS uid",
            {"uids": referenced_uids},
        )
        return [r[0] for r in results]

    def find_scaffold_with_non_scaffold_parents(self) -> list[str]:
        """Return uids of scaffold children whose parents are not scaffold."""
        results, _ = db.cypher_query(
            "MATCH (parent)-[:COMPOSES]->(child) "
            "WHERE 'scaffold' IN coalesce(child.tags, []) "
            "AND NOT 'scaffold' IN coalesce(parent.tags, []) "
            "RETURN child.canonical_key AS uid",
        )
        return [r[0] for r in results]

    def find_scaffold_directly_referenced_by_assertions(self) -> list[str]:
        """Return scaffold uids referenced by AssertionNode or TestStepNode."""
        results, _ = db.cypher_query(
            "MATCH (ca)-[r]->(s) "
            "WHERE (ca:AssertionNode OR ca:TestStepNode) "
            "AND (r:LEFT_OPERAND OR r:RIGHT_OPERAND OR r:CALLEE) "
            "AND 'scaffold' IN s.tags "
            "RETURN DISTINCT s.canonical_key AS uid",
        )
        return [r[0] for r in results]

    # ── Verification edge management ──────────────────────────────

    def delete_callee_edges(self, step_uid: str) -> None:
        """Delete all outgoing CALLEE edges from a TestStepNode."""
        db.cypher_query(
            "MATCH (step:TestStepNode {canonical_key: $key})-[r:CALLEE]->() "
            "DELETE r",
            {"uid": step_uid},
        )

    def merge_depends_on_hlr(
        self,
        source_key: str,
        target_name: str,
        *,
        description: str = "",
    ) -> dict | None:
        """MERGE DEPENDS_ON between HLRs with description."""
        results, _ = db.cypher_query(
            "MATCH (source:HLR {uid: $skey}) "
            "MATCH (target:HLR {name: $tname}) "
            "MERGE (source)-[r:DEPENDS_ON]->(target) "
            "SET r.description = $desc "
            "RETURN source.name, type(r), target.name",
            {"suid": source_key, "tname": target_name, "desc": description},
        )
        if results:
            r = results[0]
            return {
                "source": r[0],
                "relation": r[1],
                "target": r[2],
            }
        return None

    # ── Unresolved verification queries ───────────────────────────

    def find_unresolved_verifications(
        self, hlr_uid: str
    ) -> list:
        """Return TestNodes whose VERIFIES targets are still scaffold.

        Returns raw rows: [(test, verifies_target, llr_name)].
        """
        results, _ = db.cypher_query(
            "MATCH (hlr:HLR)-[:COMPOSES]->(llr:LLR) "
            "WHERE hlr.canonical_key = $key "
            "OPTIONAL MATCH (llr)-[:COMPOSES]->(test:TestNode) "
            "OPTIONAL MATCH (test)-[:VERIFIES]->(verifies_target) "
            "WHERE 'scaffold' IN coalesce(verifies_target.tags, []) "
            "RETURN test, verifies_target, llr.name AS llr_name",
            {"uid": hlr_uid},
        )
        return results

    def find_unresolved_callee_steps(
        self, hlr_uid: str
    ) -> list:
        """Return TestStepNodes whose CALLEE targets are still scaffold.

        Returns raw rows: [(step, callee_target)].
        """
        results, _ = db.cypher_query(
            "MATCH (hlr:HLR)-[:COMPOSES]->(llr:LLR) "
            "WHERE hlr.canonical_key = $key "
            "OPTIONAL MATCH (llr)-[:COMPOSES]->(test:TestNode) "
            "OPTIONAL MATCH (test)-[:COMPOSES]->(step:TestStepNode) "
            "OPTIONAL MATCH (step)-[:CALLEE]->(callee_target) "
            "WHERE 'scaffold' IN coalesce(callee_target.tags, []) "
            "RETURN step, callee_target",
            {"uid": hlr_uid},
        )
        return results
