"""Neo4jRequirementsRepository — Neo4j implementation of the
RequirementsRepository interface.

Consolidates HLR/LLR/test tree traversal, scaffold lifecycle, and
verification edge management Cypher into a single module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.persistence.requirements_repository import RequirementsRepository

if TYPE_CHECKING:
    from codegraph.persistence.repository import GraphRepository


class Neo4jRequirementsRepository(RequirementsRepository):
    """Neo4j implementation of the RequirementsRepository interface."""

    def __init__(
        self,
        conn: Neo4jConnection,
        graph_repo: "GraphRepository",
    ):
        self._conn = conn
        self._graph = graph_repo

    def _raw(self, query: str, params: dict | None = None):
        """Shorthand for connection-level execute_raw."""
        rows, _ = self._conn.execute_raw(query, params)
        return rows

    # ── HLR/LLR/Test tree traversal ────────────────────────────────

    def get_hlr_tree(self, hlr_uid: str) -> dict:
        """Return full HLR→LLRs→TestNodes tree with resolved targets."""
        rows = self._raw(
            "MATCH (hlr:HLR)-[:COMPOSES]->(llr:LLR) "
            "WHERE hlr.uid = $uid "
            "OPTIONAL MATCH (llr)-[:COMPOSES]->(test:TestNode) "
            "OPTIONAL MATCH (test)-[:VERIFIES]->(verifies_target) "
            "OPTIONAL MATCH (test)-[:COMPOSES]->(step:TestStepNode) "
            "OPTIONAL MATCH (step)-[:CALLEE]->(step_target) "
            "RETURN hlr, llr, test, verifies_target, step, step_target "
            "ORDER BY llr.name, test.test_name, step.order",
            {"uid": hlr_uid},
        )

        # Group by LLR → test
        llr_map: dict[str, dict] = {}
        hlr = None
        for r in rows:
            if hlr is None and r[0]:
                raw_hlr = r[0]
                hlr = {
                    "uid": raw_hlr.get("uid", ""),
                    "name": raw_hlr.get("name", ""),
                    "description": raw_hlr.get("description", ""),
                }
            llr_raw = r[1]
            if llr_raw is None:
                continue
            llr_key = llr_raw.get("uid", "")
            if llr_key not in llr_map:
                llr_map[llr_key] = {
                    "llr": {
                        "uid": llr_key,
                        "name": llr_raw.get("name", ""),
                        "description": llr_raw.get("description", ""),
                    },
                    "tests": {},
                }
            test_raw = r[2]
            if test_raw is None:
                continue
            test_key = test_raw.get("uid", "")
            if test_key not in llr_map[llr_key]["tests"]:
                llr_map[llr_key]["tests"][test_key] = {
                    "test": {
                        "uid": test_key,
                        "test_name": test_raw.get("test_name", ""),
                        "qualified_name": test_raw.get("qualified_name", ""),
                    },
                    "verifies_targets": [],
                    "step_callees": {},
                }
            verifies = r[3]
            if verifies:
                v_qn = verifies.get("qualified_name", "")
                if v_qn:
                    llr_map[llr_key]["tests"][test_key]["verifies_targets"].append(v_qn)
            step_raw = r[4]
            step_target = r[5]
            if step_raw and step_target:
                step_uid = step_raw.get("uid", "")
                tgt_qn = step_target.get("qualified_name", "")
                if step_uid not in llr_map[llr_key]["tests"][test_key]["step_callees"]:
                    llr_map[llr_key]["tests"][test_key]["step_callees"][step_uid] = {
                        "step": {
                            "uid": step_uid,
                            "qualified_name": step_raw.get("qualified_name", ""),
                            "order": step_raw.get("order", 0),
                        },
                        "callee_target": tgt_qn,
                    }

        llrs = []
        for entry in llr_map.values():
            tests_list = []
            for t_entry in entry["tests"].values():
                t_entry["verifies_targets"] = list(set(t_entry["verifies_targets"]))
                t_entry["step_callees"] = list(t_entry["step_callees"].values())
                tests_list.append(t_entry)
            entry["tests"] = tests_list
            llrs.append(entry)

        return {"hlr": hlr, "llrs": llrs}

    # ── Scaffold lifecycle ─────────────────────────────────────────

    def find_scaffold_uids(
        self,
        *,
        with_edges: list[str] | None = None,
        without_edges: bool = False,
        parent_is_not_scaffold: bool = False,
        directly_referenced: bool = False,
    ) -> list[str]:
        """Find scaffold node uids matching criteria."""
        conditions: list[str] = []

        if with_edges:
            edge_list = ", ".join(f"'{e}'" for e in with_edges)
            conditions.append(
                f"AND EXISTS {{ MATCH ()-[r]->(n) "
                f"WHERE type(r) IN [{edge_list}] }}"
            )

        if without_edges:
            conditions.append("AND NOT EXISTS { MATCH (n)-[r]-() }")

        if parent_is_not_scaffold:
            # This query operates on (parent)-[:COMPOSES]->(child)
            rows = self._raw(
                "MATCH (parent)-[:COMPOSES]->(child) "
                "WHERE 'scaffold' IN coalesce(child.tags, []) "
                "AND NOT 'scaffold' IN coalesce(parent.tags, []) "
                "RETURN child.uid AS uid",
            )
            return [r["uid"] for r in rows]

        if directly_referenced:
            rows = self._raw(
                "MATCH (ca)-[r]->(s) "
                "WHERE (ca:AssertionNode OR ca:TestStepNode) "
                "AND (r:LEFT_OPERAND OR r:RIGHT_OPERAND OR r:CALLEE) "
                "AND 'scaffold' IN s.tags "
                "RETURN DISTINCT s.uid AS uid",
            )
            return [r["uid"] for r in rows]

        query = (
            "MATCH (n) WHERE 'scaffold' IN coalesce(n.tags, []) "
            + " ".join(conditions)
            + " RETURN n.uid AS uid"
        )
        rows = self._raw(query)
        return [r["uid"] for r in rows]

    def find_scaffold_parents_of_referenced(
        self, referenced_uids: list[str]
    ) -> list[str]:
        """Return uids of scaffold ClassNode parents with referenced children."""
        if not referenced_uids:
            return []
        rows = self._raw(
            "MATCH (parent:ClassNode)-[:COMPOSES]->(child) "
            "WHERE 'scaffold' IN parent.tags "
            "AND child.uid IN $uids "
            "RETURN DISTINCT parent.uid AS uid",
            {"uids": referenced_uids},
        )
        return [r["uid"] for r in rows]

    def retag_scaffold_to_design(self, uid: str) -> None:
        """Change scaffold tags to ['design']."""
        self._graph.update_properties(uid, {"tags": ["design"]})

    def delete_scaffold(self, uid: str) -> None:
        """DETACH DELETE a scaffold node."""
        self._graph.delete_by_uid(uid)

    # ── Verification edge management ───────────────────────────────

    def merge_verification(
        self, test_qname: str, target_qname: str
    ) -> None:
        """MERGE VERIFIES edge."""
        self._graph.merge_relationship(
            test_qname, "VERIFIES", target_qname,
        )

    def replace_callee(
        self, step_qname: str, new_target_qname: str
    ) -> None:
        """Delete old CALLEE edges and MERGE new one."""
        # Delete old
        step_uid = self._graph.resolve_uid(step_qname)
        if step_uid:
            self._raw(
                "MATCH (step:TestStepNode {uid: $uid})-[r:CALLEE]->() "
                "DELETE r",
                {"uid": step_uid},
            )
        # Create new
        self._graph.merge_relationship(
            step_qname, "CALLEE", new_target_qname,
        )

    # ── HLR dependencies ──────────────────────────────────────────

    def merge_depends_on(
        self,
        source_uid: str,
        target_name: str,
        *,
        description: str = "",
    ) -> dict | None:
        """MERGE DEPENDS_ON between HLRs with description."""
        rows = self._raw(
            "MATCH (source:HLR {uid: $suid}) "
            "MATCH (target:HLR {name: $tname}) "
            "MERGE (source)-[r:DEPENDS_ON]->(target) "
            "SET r.description = $desc "
            "RETURN source.name, type(r), target.name",
            {"suid": source_uid, "tname": target_name, "desc": description},
        )
        if rows:
            r = rows[0]
            return {
                "source": r[0],
                "relation": r[1],
                "target": r[2],
            }
        return None

    # ── Unresolved verification queries ────────────────────────────

    def find_unresolved_verifications(
        self, hlr_uid: str
    ) -> list[dict]:
        """Return TestNodes whose VERIFIES targets are still scaffold."""
        rows = self._raw(
            "MATCH (hlr:HLR)-[:COMPOSES]->(llr:LLR) "
            "WHERE hlr.uid = $uid "
            "OPTIONAL MATCH (llr)-[:COMPOSES]->(test:TestNode) "
            "OPTIONAL MATCH (test)-[:VERIFIES]->(verifies_target) "
            "WHERE 'scaffold' IN coalesce(verifies_target.tags, []) "
            "RETURN test, verifies_target, llr.name AS llr_name",
            {"uid": hlr_uid},
        )
        results: list[dict] = []
        for r in rows:
            test = r[0]
            target = r[1]
            if test and target:
                results.append({
                    "test_uid": test.get("uid", ""),
                    "test_name": test.get("test_name", ""),
                    "test_qname": test.get("qualified_name", ""),
                    "target_qname": target.get("qualified_name", ""),
                    "llr_name": r[2],
                })
        return results

    def find_unresolved_callee_steps(
        self, hlr_uid: str
    ) -> list[dict]:
        """Return TestStepNodes whose CALLEE targets are still scaffold."""
        rows = self._raw(
            "MATCH (hlr:HLR)-[:COMPOSES]->(llr:LLR) "
            "WHERE hlr.uid = $uid "
            "OPTIONAL MATCH (llr)-[:COMPOSES]->(test:TestNode) "
            "OPTIONAL MATCH (test)-[:COMPOSES]->(step:TestStepNode) "
            "OPTIONAL MATCH (step)-[:CALLEE]->(callee_target) "
            "WHERE 'scaffold' IN coalesce(callee_target.tags, []) "
            "RETURN step, callee_target",
            {"uid": hlr_uid},
        )
        results: list[dict] = []
        for r in rows:
            step = r[0]
            target = r[1]
            if step and target:
                results.append({
                    "step_uid": step.get("uid", ""),
                    "step_qname": step.get("qualified_name", ""),
                    "target_qname": target.get("qualified_name", ""),
                })
        return results
