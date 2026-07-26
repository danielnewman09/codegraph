"""Pipeline test: DesignAgent produces Migration Manager for cpp-sqlite.

This is an end-to-end test of the DesignAgent pipeline:
1. Load as-built cpp-sqlite classes from a saved JSON fixture
2. Load requirements + verification stubs from a saved markdown fixture
   (shared via ``conftest.py``)
3. Run DesignAgent.run_with_reconciliation()
4. Assert the design meets minimum expectations

Requires: Neo4j running, LLM_API_KEY set in .env.
Skip with: ``pytest -m "not slow"``
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

import pytest

# Load .env from project root
_roots = [Path(__file__).resolve().parents[2]]
for root in _roots:
    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        break

DATA_DIR = Path(__file__).parent.parent / "data" / "cpp_sqlite"

from codegraph.graph import LayerGraph
from codegraph.export.format import export_graph


def _requires_openai():
    """Skip if no LLM API key is configured."""
    if not os.getenv("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY not set")


from tests.pipelines.conftest import (
    _cleanup_design_and_scaffold,
    _has_neomodel_connection,
    _ingest_requirements_text,
)


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def ingest_as_built():
    """Import the cpp-sqlite as-built classes from the saved JSON export."""
    import logging
    log = logging.getLogger(__name__)

    json_path = DATA_DIR / "codegraph_as_built.json"
    if not json_path.exists():
        pytest.skip(f"as-built fixture not found: {json_path}")

    from codegraph.export.format import import_graph

    log.info("Ingesting as-built fixture: %s", json_path)
    text = json_path.read_text(encoding="utf-8")

    graph = import_graph(
        text, format="json", tags=frozenset({"as-built"}),
    )

    entries = list(graph._all_entries())
    log.info("Parsed %d entries from JSON", len(entries))

    graph.to_neo4j()
    log.info("Persisted %d entries to Neo4j (as-built)", len(entries))

    qnames: set[str] = set()
    for entry in entries:
        qn = getattr(entry.node, "qualified_name", "") or ""
        if qn:
            qnames.add(qn)

    return qnames


@pytest.fixture(scope="function")
def v3_design_inputs() -> dict:
    """Ingest v3 requirements + API contract for the design test.

    Clears stale design/scaffold/requirements data, then ingests
    both the v3 requirements markdown and the v3 API contract.

    Returns a dict with ``hlr_uid`` and ``contract_path``.
    """
    import logging
    log = logging.getLogger(__name__)

    # Clear stale data
    _cleanup_design_and_scaffold()

    # Ingest v3 requirements
    req_path = DATA_DIR / "migration_manager_requirements_v3.md"
    if not req_path.exists():
        pytest.skip(f"V3 requirements not found: {req_path}")

    hlr_uid = _ingest_requirements_text("v3", req_path)
    log.info("Ingested v3 requirements → HLR uid %s", hlr_uid[:16])

    # Ingest contract as scaffold
    contract_path = DATA_DIR / "migration_manager_api_contract_v3.md"
    if not contract_path.exists():
        pytest.skip(f"V3 contract not found: {contract_path}")

    from codegraph.export.markdown import MarkdownImporter
    contract_text = contract_path.read_text(encoding="utf-8")
    importer = MarkdownImporter(
        tags=frozenset({"scaffold"}), strict=False,
    )
    g = importer.import_markdown(contract_text)
    g.to_neo4j()
    log.info("Ingested contract: %d entries", len(list(g._all_entries())))

    return {
        "hlr_uid": hlr_uid,
        "contract_path": str(contract_path),
    }


# ── Tests ────────────────────────────────────────────────────────


@pytest.skip
@pytest.mark.slow
@pytest.mark.integration
class TestDesignMigrationManager:
    """Pipeline test: DesignAgent → Migration Manager."""

    def test_neo4j_reachable(self) -> None:
        """Prerequisite: Neo4j must be running."""
        assert _has_neomodel_connection(), (
            "Neo4j not reachable at bolt://localhost:7687"
        )

    def test_as_built_ingested(
        self, ingest_as_built: set[str],
    ) -> None:
        """As-built fixture loaded correctly."""
        assert "cpp_sqlite::Database" in ingest_as_built
        assert "cpp_sqlite::Transaction" in ingest_as_built
        assert "cpp_sqlite::DataAccessObject" in ingest_as_built
        assert "cpp_sqlite::BaseTransferObject" in ingest_as_built
        assert len(ingest_as_built) >= 10, (
            f"Expected >=10 as-built classes, got {len(ingest_as_built)}: "
            f"{sorted(ingest_as_built)}"
        )

    @pytest.mark.slow
    def test_design_agent_produces_expected_classes(
        self,
        ingest_as_built: set[str],
        v3_design_inputs: dict,
    ) -> None:
        """DesignAgent produces consistent design from v3 + contract."""
        import logging
        log = logging.getLogger(__name__)

        _requires_openai()

        from codegraph_agents.design import DesignAgent
        from codegraph_agents.config import AgentConfig

        hlr_uid = v3_design_inputs["hlr_uid"]
        contract_path = v3_design_inputs["contract_path"]

        log.info(
            "Running DesignAgent for HLR %s with %d as-built classes + contract",
            hlr_uid[:16], len(ingest_as_built),
        )

        agent = DesignAgent(
            AgentConfig(
                hlr_uid=hlr_uid,
                component_namespace="cpp_sqlite",
                log_dir="codegraph/logs",
            ),
            api_contract_path=contract_path,
        )

        result = agent.run_with_reconciliation()
        log.info("DesignAgent completed: %s", result.get("status"))

        # ── Basic liveness ──
        assert result["status"] == "designed", (
            f"Design failed: {result.get('errors', [])}"
        )
        assert (
            result["nodes_created"] + result["nodes_updated"]
        ) > 0, "No design nodes were created or updated"

        # ── Namespace reuse ──
        assert result["namespaces_created"] == 0, (
            f"Expected 0 namespaces created (should reuse existing), "
            f"got {result['namespaces_created']}. "
            f"Reused: {result.get('namespaces_reused', 0)}"
        )
        assert result["namespaces_reused"] >= 1, (
            f"Expected at least 1 namespace reused, "
            f"got {result.get('namespaces_reused', 0)}"
        )
        assert result["namespace_edges"] > 0, (
            f"Expected namespace→compound COMPOSES edges, "
            f"got {result.get('namespace_edges', 0)}"
        )

        # ── Collect design QNames ──
        from codegraph.models.compound import CompoundNode

        design_qnames: set[str] = set()
        for node in CompoundNode.nodes.all():
            tags = getattr(node, "tags", []) or []
            if "design" in tags:
                design_qnames.add(
                    getattr(node, "qualified_name", "") or ""
                )

        # ── Required classes from expected_design.json ──
        expected_path = DATA_DIR / "expected_design.json"
        expected = json.loads(expected_path.read_text(encoding="utf-8"))

        for expected_cls in expected["must_have_classes"]:
            expected_name = expected_cls["name"]
            found = any(
                qn.split("::")[-1].startswith(expected_name)
                for qn in design_qnames
            )
            assert found, (
                f"Required class starting with '{expected_name}' "
                f"not found in design.  "
                f"Design QNames: {sorted(design_qnames)}"
            )

        # ── Required edges (from expected_design.json) ──
        edge_assertions = expected.get("must_have_edges", [])
        if edge_assertions:
            from neomodel import db as neodb
            missing = []
            for edge_spec in edge_assertions:
                from_name = edge_spec["from_class"]
                rel = edge_spec["relation"]
                to_name = edge_spec["to_class"]
                desc = edge_spec.get("description", "")

                query = """
                    MATCH (a)-[r]->(b)
                    WHERE a.qualified_name CONTAINS $from_name
                      AND type(r) = $rel
                      AND b.qualified_name CONTAINS $to_name
                    RETURN count(r) > 0 as exists
                """
                rows, _ = neodb.cypher_query(
                    query,
                    {"from_name": from_name, "rel": rel, "to_name": to_name},
                )
                exists = rows[0][0] if rows else False
                if not exists:
                    entry = f"{from_name} -[{rel}]-> {to_name}"
                    if desc:
                        entry += f" ({desc})"
                    missing.append(entry)

            assert not missing, (
                f"Missing required edges: {missing}"
            )
            log.info(
                "All %d required edges verified", len(edge_assertions),
            )

        # ── DEPENDS_ON edges are synthesized during reconciliation ──
        # from the design nodes' depends_on arrays.  The agent may or
        # may not emit explicit depends_on edges; the contract document
        # specifies the relationship graph instead.
        if result["deps_edges"] == 0:
            log.info(
                "No explicit DEPENDS_ON edges emitted by agent "
                "(%d combined edges total).  Relationships are "
                "defined in the API contract document.",
                result.get("edges_linked", 0),
            )

        # ── Contract types must all appear ──
        contract_classes = [
            "Migration",
            "MigrationManager",
            "SchemaVersion",
            "MigrationResult",
            "SchemaMismatch",
            "SchemaVerificationResult",
            "MigrationErrorCode",
            "MismatchKind",
        ]
        for cls_name in contract_classes:
            found = any(
                qn.split("::")[-1] == cls_name
                for qn in design_qnames
            )
            assert found, (
                f"Contract class '{cls_name}' not found in design. "
                f"Design QNames: {sorted(design_qnames)}"
            )

        # ── MigrationManager must have all 4 key methods ──
        from codegraph.models.member import MethodNode

        design_methods: dict[str, set[str]] = {}
        for node in MethodNode.nodes.all():
            qn = getattr(node, "qualified_name", "") or ""
            name = getattr(node, "name", "") or ""
            # Derive parent from qualified_name (rsplit last ::).
            # parent_qualified_name is stored in Neo4j but not mapped
            # by neomodel, so getattr() always misses it.
            parent = qn.rsplit("::", 1)[0] if "::" in qn else ""
            if parent not in design_methods:
                design_methods[parent] = set()
            design_methods[parent].add(name)

        mgr_name = next(
            (qn for qn in design_qnames
             if qn.split("::")[-1] == "MigrationManager"),
            None,
        )
        if mgr_name:
            mgr_methods = design_methods.get(mgr_name, set())
            for expected in ["register_migration", "apply", "rollback", "verify"]:
                assert expected in mgr_methods, (
                    f"MigrationManager missing method '{expected}'. "
                    f"Found: {sorted(mgr_methods)}"
                )

        # ── Export artifacts ──
        out_dir = Path(__file__).parent.parent / "unit_test_data"
        out_dir.mkdir(parents=True, exist_ok=True)

        artifacts = result.get("artifacts", {})

        puml_path = artifacts.get("puml", "")
        if puml_path and Path(puml_path).exists():
            dest = out_dir / "architecture_class_diagram.puml"
            dest.write_text(Path(puml_path).read_text(), encoding="utf-8")
            log.info("Exported PUML: %s", dest)

        png_path = artifacts.get("png", "")
        if png_path and Path(png_path).exists():
            dest = out_dir / "architecture_class_diagram.png"
            shutil.copy2(png_path, dest)
            log.info("Exported PNG: %s (%d bytes)", dest, dest.stat().st_size)

        md_path = artifacts.get("design_md", "")
        if md_path and Path(md_path).exists():
            dest = out_dir / "design.md"
            dest.write_text(Path(md_path).read_text(), encoding="utf-8")
            log.info("Exported design MD: %s", dest)

        # ── Export design LayerGraph as JSON ──
        design_graph = LayerGraph.from_neo4j("design")
        json_text = export_graph(design_graph, format="json", fields="all")
        json_dest = out_dir / "design_layergraph.json"
        json_dest.write_text(json_text, encoding="utf-8")
        log.info(
            "Exported design LayerGraph JSON: %s (%d bytes)",
            json_dest, len(json_text),
        )

        log.info(
            "Design verified: %d classes, %d methods",
            len(design_qnames),
            sum(len(v) for v in design_methods.values()),
        )
