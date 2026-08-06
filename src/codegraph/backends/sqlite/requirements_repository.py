"""SqliteRequirementsRepository — SQLite implementation of the
RequirementsRepository interface.

Ports ``Neo4jRequirementsRepository`` / ``Neo4jRequirementsOps`` to SQL
over the single graph schema: HLR/LLR/TestNode tree traversal via
COMPOSES edges + label filters, scaffold lifecycle queries, and
VERIFIES/CALLEE/DEPENDS_ON edge management.
"""

from __future__ import annotations

import json

import sqlalchemy as sa

from codegraph.backends.sqlite.connection import SqliteConnection, row_to_dict
from codegraph.backends.sqlite.node_ops import _row_to_node
from codegraph.persistence.requirements_repository import RequirementsRepository

_REF_EDGE_TYPES = ("LEFT_OPERAND", "RIGHT_OPERAND", "CALLEE", "CALLER")


class SqliteRequirementsRepository(RequirementsRepository):
    """SQLite implementation of the RequirementsRepository interface."""

    def __init__(
        self,
        conn: SqliteConnection,
        graph_repo,
    ):
        self._conn = conn
        self._graph = graph_repo

    # ── HLR/LLR/Test tree traversal ───────────────────────────────

    def get_hlr_tree(self, hlr_uid: str) -> dict:
        """Return the full HLR→LLRs→TestNodes tree with VERIFIES and
        CALLEE targets resolved."""
        with self._conn.connect() as conn:
            hlr_row = conn.execute(
                sa.text(
                    "SELECT n.id, n.uid, n.labels, n.properties FROM nodes n "
                    "JOIN node_labels nl ON nl.node_id = n.id "
                    "WHERE nl.label = 'HLR' AND n.uid = :uid LIMIT 1"
                ),
                {"uid": hlr_uid},
            ).first()
            if hlr_row is None:
                return {"hlr": None, "llrs": []}
            hlr_row = row_to_dict(hlr_row)
            hlr = _dict_from_props(hlr_row, ("uid", "name", "description"))

            # LLRs composed by the HLR.
            llr_rows = list(
                conn.execute(
                    sa.text(
                        "SELECT n.id, n.uid, n.labels, n.properties FROM edges e "
                        "JOIN nodes n ON n.id = e.target_id "
                        "JOIN node_labels nl ON nl.node_id = n.id "
                        "WHERE e.source_id = :sid AND e.rel_type = 'COMPOSES' "
                        "AND nl.label = 'LLR'"
                    ),
                    {"sid": hlr_row["id"]},
                )
            )
            llr_nodes = [_row_to_node(r, conn) for r in llr_rows]
            llr_nodes = [n for n in llr_nodes if n is not None]
            llr_ids = {n.element_id_property: n for n in llr_nodes}

            # Tests composed by each LLR.
            tests_by_llr: dict[int, list] = {}
            test_ids: dict[int, object] = {}
            if llr_ids:
                binds = ", ".join(f":l{i}" for i in range(len(llr_ids)))
                test_rows = list(
                    conn.execute(
                        sa.text(
                            "SELECT e.source_id AS llr_id, "
                            "n.id, n.uid, n.labels, n.properties "
                            "FROM edges e "
                            "JOIN nodes n ON n.id = e.target_id "
                            "JOIN node_labels nl ON nl.node_id = n.id "
                            f"WHERE e.source_id IN ({binds}) "
                            "AND e.rel_type = 'COMPOSES' AND nl.label = 'TestNode'"
                        ),
                        {f"l{i}": lid for i, lid in enumerate(llr_ids)},
                    )
                )
                for row in test_rows:
                    d = row_to_dict(row)
                    node = _row_to_node(row, conn)
                    if node is None:
                        continue
                    tests_by_llr.setdefault(d["llr_id"], []).append(node)
                    test_ids[node.element_id_property] = node

            # VERIFIES targets per test.
            verifies_by_test: dict[int, list[str]] = {}
            if test_ids:
                tbinds = ", ".join(f":t{i}" for i in range(len(test_ids)))
                vrows = list(
                    conn.execute(
                        sa.text(
                            "SELECT e.source_id AS test_id, "
                            "t.qualified_name AS qn "
                            "FROM edges e JOIN nodes t ON t.id = e.target_id "
                            f"WHERE e.source_id IN ({tbinds}) "
                            "AND e.rel_type = 'VERIFIES'"
                        ),
                        {f"t{i}": tid for i, tid in enumerate(test_ids)},
                    )
                )
                for row in vrows:
                    d = row_to_dict(row)
                    if d["qn"]:
                        verifies_by_test.setdefault(d["test_id"], []).append(d["qn"])

            # Test steps (COMPOSES children labelled TestStepNode) + CALLEE targets.
            steps_by_test: dict[int, list] = {}
            step_ids: dict[int, object] = {}
            if test_ids:
                tbinds = ", ".join(f":t{i}" for i in range(len(test_ids)))
                step_rows = list(
                    conn.execute(
                        sa.text(
                            "SELECT e.source_id AS test_id, "
                            "n.id, n.uid, n.labels, n.properties "
                            "FROM edges e "
                            "JOIN nodes n ON n.id = e.target_id "
                            "JOIN node_labels nl ON nl.node_id = n.id "
                            f"WHERE e.source_id IN ({tbinds}) "
                            "AND e.rel_type = 'COMPOSES' AND nl.label = 'TestStepNode'"
                        ),
                        {f"t{i}": tid for i, tid in enumerate(test_ids)},
                    )
                )
                for row in step_rows:
                    d = row_to_dict(row)
                    node = _row_to_node(row, conn)
                    if node is None:
                        continue
                    steps_by_test.setdefault(d["test_id"], []).append(node)
                    step_ids[node.element_id_property] = node

            callee_by_step: dict[int, str] = {}
            if step_ids:
                sbinds = ", ".join(f":s{i}" for i in range(len(step_ids)))
                crows = list(
                    conn.execute(
                        sa.text(
                            "SELECT e.source_id AS step_id, "
                            "t.qualified_name AS qn "
                            "FROM edges e JOIN nodes t ON t.id = e.target_id "
                            f"WHERE e.source_id IN ({sbinds}) AND e.rel_type = 'CALLEE'"
                        ),
                        {f"s{i}": sid for i, sid in enumerate(step_ids)},
                    )
                )
                for row in crows:
                    d = row_to_dict(row)
                    if d["qn"]:
                        callee_by_step[d["step_id"]] = d["qn"]

        # ── Pure-Python grouping (mirrors Neo4jRequirementsRepository) ──
        llrs_out: list[dict] = []
        for llr in llr_nodes:
            tests_out: list[dict] = []
            for test in tests_by_llr.get(llr.element_id_property, []):
                test_id = test.element_id_property
                steps_out: list[dict] = []
                for step in steps_by_test.get(test_id, []):
                    steps_out.append({
                        "step": {
                            "uid": step._uid_value(),
                            "qualified_name": getattr(step, "qualified_name", ""),
                            "order": getattr(step, "order", 0),
                        },
                        "callee_target": callee_by_step.get(step.element_id_property, ""),
                    })
                tests_out.append({
                    "test": {
                        "uid": test._uid_value(),
                        "test_name": getattr(test, "test_name", ""),
                        "qualified_name": getattr(test, "qualified_name", ""),
                    },
                    "verifies_targets": list(set(verifies_by_test.get(test_id, []))),
                    "step_callees": steps_out,
                })
            llrs_out.append({
                "llr": {
                    "uid": llr._uid_value(),
                    "name": getattr(llr, "name", ""),
                    "description": getattr(llr, "description", ""),
                },
                "tests": tests_out,
            })

        return {"hlr": hlr, "llrs": llrs_out}

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
        with self._conn.connect() as conn:
            if parent_is_not_scaffold:
                rows = list(
                    conn.execute(
                        sa.text(
                            "SELECT DISTINCT child.uid AS uid "
                            "FROM edges e "
                            "JOIN nodes child ON child.id = e.target_id "
                            "JOIN nodes parent ON parent.id = e.source_id "
                            "JOIN node_tags ct ON ct.node_id = child.id "
                            "WHERE e.rel_type = 'COMPOSES' "
                            "AND ct.tag = 'scaffold' "
                            "AND NOT EXISTS (SELECT 1 FROM node_tags pt "
                            "  WHERE pt.node_id = parent.id AND pt.tag = 'scaffold')"
                        )
                    )
                )
                return [r[0] for r in rows]

            if directly_referenced:
                rows = list(
                    conn.execute(
                        sa.text(
                            "SELECT DISTINCT s.uid AS uid "
                            "FROM edges e "
                            "JOIN nodes s ON s.id = e.target_id "
                            "JOIN nodes ca ON ca.id = e.source_id "
                            "JOIN node_labels cal ON cal.node_id = ca.id "
                            "JOIN node_tags st ON st.node_id = s.id "
                            "WHERE e.rel_type IN ('LEFT_OPERAND', 'RIGHT_OPERAND', 'CALLEE') "
                            "AND cal.label IN ('AssertionNode', 'TestStepNode') "
                            "AND st.tag = 'scaffold'"
                        )
                    )
                )
                return [r[0] for r in rows]

            if with_edges:
                edge_binds = ", ".join(f":e{i}" for i in range(len(with_edges)))
                rows = list(
                    conn.execute(
                        sa.text(
                            "SELECT DISTINCT n.uid AS uid FROM edges e "
                            "JOIN nodes n ON n.id = e.target_id "
                            "JOIN node_tags nt ON nt.node_id = n.id "
                            f"WHERE e.rel_type IN ({edge_binds}) AND nt.tag = 'scaffold'"
                        ),
                        {f"e{i}": t for i, t in enumerate(with_edges)},
                    )
                )
                return [r[0] for r in rows]

            if without_edges:
                rows = list(
                    conn.execute(
                        sa.text(
                            "SELECT n.uid AS uid FROM nodes n "
                            "JOIN node_tags nt ON nt.node_id = n.id "
                            "WHERE nt.tag = 'scaffold' "
                            "AND NOT EXISTS (SELECT 1 FROM edges e "
                            "  WHERE e.source_id = n.id OR e.target_id = n.id)"
                        )
                    )
                )
                return [r[0] for r in rows]

            rows = list(
                conn.execute(
                    sa.text(
                        "SELECT n.uid AS uid FROM nodes n "
                        "JOIN node_tags nt ON nt.node_id = n.id "
                        "WHERE nt.tag = 'scaffold'"
                    )
                )
            )
            return [r[0] for r in rows]

    def find_scaffold_parents_of_referenced(
        self, referenced_uids: list[str]
    ) -> list[str]:
        """Return uids of scaffold ClassNode parents whose COMPOSES
        children include any of *referenced_uids*."""
        if not referenced_uids:
            return []
        rbinds = ", ".join(f":r{i}" for i in range(len(referenced_uids)))
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        "SELECT DISTINCT parent.uid AS uid "
                        "FROM edges e "
                        "JOIN nodes parent ON parent.id = e.source_id "
                        "JOIN nodes child ON child.id = e.target_id "
                        "JOIN node_labels pl ON pl.node_id = parent.id "
                        "JOIN node_tags pt ON pt.node_id = parent.id "
                        f"WHERE e.rel_type = 'COMPOSES' "
                        f"AND child.uid IN ({rbinds}) "
                        "AND pl.label = 'ClassNode' AND pt.tag = 'scaffold'"
                    ),
                    {f"r{i}": u for i, u in enumerate(referenced_uids)},
                )
            )
        return [r[0] for r in rows]

    def retag_scaffold_to_design(self, uid: str) -> None:
        """Change a scaffold node's tags to ``['design']``."""
        self._graph.update_properties(uid, {"tags": ["design"]})

    def delete_scaffold(self, uid: str) -> None:
        """DETACH-style delete of a scaffold node by uid."""
        self._graph.delete_by_uid(uid)

    # ── Verification edge management ───────────────────────────────

    def merge_verification(
        self, test_qname: str, target_qname: str
    ) -> None:
        """MERGE a VERIFIES edge from a TestNode to a target."""
        test_uid = self._graph.resolve_uid(test_qname)
        target_uid = self._graph.resolve_uid(target_qname)
        if test_uid and target_uid:
            self._graph.merge_relationship(test_uid, "VERIFIES", target_uid)

    def replace_callee(
        self, step_qname: str, new_target_qname: str
    ) -> None:
        """Delete old CALLEE edges from a TestStep and MERGE a new one."""
        step_uid = self._graph.resolve_uid(step_qname)
        if step_uid:
            with self._conn.session() as conn:
                step_id = conn.execute(
                    sa.text("SELECT id FROM nodes WHERE uid = :uid"),
                    {"uid": step_uid},
                ).first()
                if step_id is not None:
                    conn.execute(
                        sa.text(
                            "DELETE FROM edges "
                            "WHERE source_id = :sid AND rel_type = 'CALLEE'"
                        ),
                        {"sid": step_id[0]},
                    )
        target_uid = self._graph.resolve_uid(new_target_qname)
        if step_uid and target_uid:
            self._graph.merge_relationship(step_uid, "CALLEE", target_uid)

    # ── HLR dependencies ──────────────────────────────────────────

    def merge_depends_on(
        self,
        source_uid: str,
        target_name: str,
        *,
        description: str = "",
    ) -> dict | None:
        """MERGE a DEPENDS_ON edge between HLRs and set the description."""
        with self._conn.session() as conn:
            src = conn.execute(
                sa.text(
                    "SELECT n.id FROM nodes n "
                    "JOIN node_labels nl ON nl.node_id = n.id "
                    "WHERE nl.label = 'HLR' AND n.uid = :uid LIMIT 1"
                ),
                {"uid": source_uid},
            ).first()
            tgt = conn.execute(
                sa.text(
                    "SELECT n.id, n.uid, n.properties FROM nodes n "
                    "JOIN node_labels nl ON nl.node_id = n.id "
                    "WHERE nl.label = 'HLR' "
                    "AND json_extract(n.properties, '$.name') = :name LIMIT 1"
                ),
                {"name": target_name},
            ).first()
            if src is None or tgt is None:
                return None
            conn.execute(
                sa.text(
                    "INSERT INTO edges (source_id, rel_type, target_id, properties) "
                    "VALUES (:sid, 'DEPENDS_ON', :tid, :props) "
                    "ON CONFLICT(source_id, rel_type, target_id) DO UPDATE SET "
                    "properties = excluded.properties"
                ),
                {"sid": src[0], "tid": tgt[0], "props": json.dumps({"description": description})},
            )
            tgt_name = (json.loads(tgt[2]) or {}).get("name", "")
            return {"source": source_uid, "relation": "DEPENDS_ON", "target": tgt_name}

    # ── Unresolved verification queries ────────────────────────────

    def find_unresolved_verifications(
        self, hlr_uid: str
    ) -> list[dict]:
        """Return TestNodes under *hlr_uid* whose VERIFIES targets still
        have 'scaffold' tags."""
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        "WITH RECURSIVE sub(sub_id, depth) AS ( "
                        "  SELECT n.id, 0 FROM nodes n "
                        "  JOIN node_labels hl ON hl.node_id = n.id "
                        "  WHERE hl.label = 'HLR' AND n.uid = :uid "
                        "  UNION ALL "
                        "  SELECT e.target_id, s.depth + 1 FROM edges e "
                        "  JOIN sub s ON e.source_id = s.sub_id "
                        "  WHERE e.rel_type = 'COMPOSES' AND s.depth < 20 "
                        ") "
                        "SELECT t.uid AS test_uid, t.properties AS t_props, "
                        "v.qualified_name AS target_qname, "
                        "json_extract(llr.properties, '$.name') AS llr_name "
                        "FROM sub s "
                        "JOIN edges te ON te.source_id = s.sub_id "
                        "JOIN nodes t ON t.id = te.target_id "
                        "JOIN node_labels tl ON tl.node_id = t.id "
                        "JOIN edges ve ON ve.source_id = t.id "
                        "JOIN nodes v ON v.id = ve.target_id "
                        "JOIN node_tags vt ON vt.node_id = v.id "
                        "LEFT JOIN edges le ON le.target_id = t.id "
                        "  AND le.rel_type = 'COMPOSES' "
                        "LEFT JOIN nodes llr ON llr.id = le.source_id "
                        "LEFT JOIN node_labels ll ON ll.node_id = llr.id "
                        "  AND ll.label = 'LLR' "
                        "WHERE te.rel_type = 'COMPOSES' AND tl.label = 'TestNode' "
                        "AND ve.rel_type = 'VERIFIES' AND vt.tag = 'scaffold'"
                    ),
                    {"uid": hlr_uid},
                )
            )
        results: list[dict] = []
        for r in rows:
            props = json.loads(r[1]) or {}
            results.append({
                "test_uid": r[0],
                "test_name": props.get("test_name", ""),
                "test_qname": props.get("qualified_name", ""),
                "target_qname": r[2],
                "llr_name": r[3] or "",
            })
        return results

    def find_unresolved_callee_steps(
        self, hlr_uid: str
    ) -> list[dict]:
        """Return TestStepNodes under *hlr_uid* whose CALLEE targets still
        have 'scaffold' tags."""
        with self._conn.connect() as conn:
            rows = list(
                conn.execute(
                    sa.text(
                        "WITH RECURSIVE sub(sub_id, depth) AS ( "
                        "  SELECT n.id, 0 FROM nodes n "
                        "  JOIN node_labels hl ON hl.node_id = n.id "
                        "  WHERE hl.label = 'HLR' AND n.uid = :uid "
                        "  UNION ALL "
                        "  SELECT e.target_id, s.depth + 1 FROM edges e "
                        "  JOIN sub s ON e.source_id = s.sub_id "
                        "  WHERE e.rel_type = 'COMPOSES' AND s.depth < 20 "
                        ") "
                        "SELECT DISTINCT st.uid AS step_uid, st.properties AS s_props, "
                        "c.qualified_name AS target_qname "
                        "FROM sub s "
                        "JOIN edges te ON te.source_id = s.sub_id "
                        "JOIN nodes t ON t.id = te.target_id "
                        "JOIN node_labels tl ON tl.node_id = t.id "
                        "JOIN edges ste ON ste.source_id = t.id "
                        "JOIN nodes st ON st.id = ste.target_id "
                        "JOIN node_labels sl ON sl.node_id = st.id "
                        "JOIN edges ce ON ce.source_id = st.id "
                        "JOIN nodes c ON c.id = ce.target_id "
                        "JOIN node_tags ct ON ct.node_id = c.id "
                        "WHERE te.rel_type = 'COMPOSES' AND tl.label = 'TestNode' "
                        "AND ste.rel_type = 'COMPOSES' AND sl.label = 'TestStepNode' "
                        "AND ce.rel_type = 'CALLEE' AND ct.tag = 'scaffold'"
                    ),
                    {"uid": hlr_uid},
                )
            )
        results: list[dict] = []
        for r in rows:
            props = json.loads(r[1]) or {}
            results.append({
                "step_uid": r[0],
                "step_qname": props.get("qualified_name", ""),
                "target_qname": r[2],
            })
        return results


def _dict_from_props(row: dict, keys: tuple[str, ...]) -> dict:
    """Extract a subset of keys from a nodes-table row's properties JSON.

    *row* must already be a plain dict (see :func:`row_to_dict`).
    """
    props = json.loads(row.get("properties") or "{}")
    return {k: props.get(k, "") for k in keys}
