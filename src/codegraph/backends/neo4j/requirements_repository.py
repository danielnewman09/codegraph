"""Neo4jRequirementsRepository — Neo4j implementation of the
RequirementsRepository interface.

All Cypher is sealed inside ``Neo4jRequirementsOps``.  The repository
does pure-Python grouping/transformation of op results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codegraph.backends.neo4j.connection import Neo4jConnection
from codegraph.backends.neo4j.requirements_ops import Neo4jRequirementsOps
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
        self._req_ops = Neo4jRequirementsOps(conn)

    # ── HLR/LLR/Test tree traversal ───────────────────────────────

    def get_hlr_tree(self, hlr_uid: str) -> dict:
        """Return full HLR→LLRs→TestNodes tree with resolved targets.

        Delegates Cypher to ``Neo4jRequirementsOps``; does grouping in
        pure Python.
        """
        rows = self._req_ops.get_hlr_tree(hlr_uid)

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
        if parent_is_not_scaffold:
            return self._req_ops.find_scaffold_with_non_scaffold_parents()

        if directly_referenced:
            return self._req_ops.find_scaffold_directly_referenced_by_assertions()

        if with_edges:
            return self._req_ops.find_scaffold_with_references()

        if without_edges:
            return self._req_ops.find_scaffold_without_relationships()

        return self._req_ops.find_scaffold_uids()

    def find_scaffold_parents_of_referenced(
        self, referenced_uids: list[str]
    ) -> list[str]:
        """Return uids of scaffold ClassNode parents with referenced children."""
        return self._req_ops.find_scaffold_parents_of_referenced(referenced_uids)

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
        test_uid = self._graph.resolve_uid(test_qname)
        target_key = self._graph.resolve_uid(target_qname)
        if test_uid and target_key:
            self._graph.merge_relationship(test_uid, "VERIFIES", target_key)

    def replace_callee(
        self, step_qname: str, new_target_qname: str
    ) -> None:
        """Delete old CALLEE edges and MERGE new one."""
        step_uid = self._graph.resolve_uid(step_qname)
        if step_uid:
            self._req_ops.delete_callee_edges(step_uid)
        target_key = self._graph.resolve_uid(new_target_qname)
        if step_uid and target_key:
            self._graph.merge_relationship(step_uid, "CALLEE", target_key)

    # ── HLR dependencies ──────────────────────────────────────────

    def merge_depends_on(
        self,
        source_key: str,
        target_name: str,
        *,
        description: str = "",
    ) -> dict | None:
        """MERGE DEPENDS_ON between HLRs with description."""
        return self._req_ops.merge_depends_on_hlr(
            source_key, target_name, description=description,
        )

    # ── Unresolved verification queries ────────────────────────────

    def find_unresolved_verifications(
        self, hlr_uid: str
    ) -> list[dict]:
        """Return TestNodes whose VERIFIES targets are still scaffold."""
        rows = self._req_ops.find_unresolved_verifications(hlr_uid)
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
        rows = self._req_ops.find_unresolved_callee_steps(hlr_uid)
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
