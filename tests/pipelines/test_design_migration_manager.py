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

DATA_DIR = Path(__file__).parent / "data" / "cpp_sqlite"


def _requires_openai():
    """Skip if no LLM API key is configured."""
    if not os.getenv("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY not set")


from tests.pipelines.conftest import _has_neomodel_connection


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def ingest_as_built():
    """Import the cpp-sqlite as-built classes from the saved JSON export.

    The JSON is a full codegraph export (produced by doxygen-index)
    containing ClassNode, ConceptNode, ImplementationNode,
    ParameterNode, FileNode, and NamespaceNode entries.

    Returns the set of qualified names imported.
    """
    import logging
    import json as _json
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


# ── Tests ────────────────────────────────────────────────────────


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

    def test_requirements_ingested(
        self, ingest_requirements: str,
    ) -> None:
        """Requirements fixture loaded and HLR uid returned."""
        assert len(ingest_requirements) > 0

    @pytest.mark.slow
    def test_design_agent_produces_expected_classes(
        self,
        ingest_as_built: set[str],
        ingest_requirements: str,
    ) -> None:
        """DesignAgent produces Migration, SchemaVersion, MigrationManager."""
        import logging
        log = logging.getLogger(__name__)

        _requires_openai()

        from codegraph_agents.design import DesignAgent
        from codegraph_agents.config import AgentConfig

        log.info(
            "Running DesignAgent for HLR %s with %d as-built classes",
            ingest_requirements[:16], len(ingest_as_built),
        )

        agent = DesignAgent(AgentConfig(
            hlr_uid=ingest_requirements,
            component_namespace="cpp_sqlite",
            log_dir="codegraph/logs",
        ))

        result = agent.run_with_reconciliation()
        log.info("DesignAgent completed: %s", result.get("status"))

        # ── Basic liveness assertions ──
        assert result["status"] == "designed", (
            f"Design failed: {result.get('errors', [])}"
        )
        assert (
            result["nodes_created"] + result["nodes_updated"]
        ) > 0, "No design nodes were created or updated"

        # ── Namespace reuse: the design must reuse the existing
        #     cpp_sqlite namespace (not create a duplicate).
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

        # ── Reuse existing namespace (not create a new one) ──
        assert result.get("namespaces_reused", 0) > 0, (
            f"Expected at least one existing namespace to be reused, "
            f"got created={result.get('namespaces_created', 0)}, "
            f"reused={result.get('namespaces_reused', 0)}"
        )
        assert result.get("namespaces_created", 0) == 0, (
            f"Expected zero new namespaces, "
            f"got created={result.get('namespaces_created', 0)}, "
            f"reused={result.get('namespaces_reused', 0)}"
        )

        # ── Load expected design from JSON ──
        expected_path = DATA_DIR / "expected_design.json"
        expected = json.loads(expected_path.read_text(encoding="utf-8"))

        # Collect actual design classes from Neo4j
        from codegraph.models.compound import CompoundNode

        design_qnames: set[str] = set()
        for node in CompoundNode.nodes.all():
            tags = getattr(node, "tags", []) or []
            if "design" in tags:
                design_qnames.add(
                    getattr(node, "qualified_name", "") or ""
                )

        # ── Assert required classes ──
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

        # ── Assert required edges to existing as-built entities ──
        edge_assertions = expected.get("must_have_edges", [])
        if edge_assertions:
            from neomodel import db as neodb
            for edge_spec in edge_assertions:
                from_name = edge_spec["from_class"]
                rel = edge_spec["relation"]
                to_name = edge_spec["to_class"]
                desc = edge_spec.get("description", "")

                # Query for edges between nodes whose qualified_name
                # contains the from/to class names.  This handles both
                # exact matches (e.g., cpp_sqlite::Database) and
                # namespace-prefixed matches.
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
                assert exists, (
                    f"Edge {from_name} -[{rel}]-> {to_name} not found. "
                    f"Description: {desc}"
                )
            log.info(
                "All %d required edges verified", len(edge_assertions),
            )

        # ── Verify DEPENDS_ON edges exist (counted in result) ──
        assert result["deps_edges"] > 0, (
            f"Expected at least 1 DEPENDS_ON edge, "
            f"got {result['deps_edges']}"
        )

        # ── Export artifacts to unit_test_data/ ──
        out_dir = Path(__file__).parent / "unit_test_data"
        out_dir.mkdir(parents=True, exist_ok=True)

        artifacts = result.get("artifacts", {})

        # Copy PlantUML source
        puml_path = artifacts.get("puml", "")
        if puml_path and Path(puml_path).exists():
            dest = out_dir / "architecture_class_diagram.puml"
            dest.write_text(Path(puml_path).read_text(), encoding="utf-8")
            log.info("Exported PUML: %s", dest)

        # Copy rendered PNG
        png_path = artifacts.get("png", "")
        if png_path and Path(png_path).exists():
            import shutil
            dest = out_dir / "architecture_class_diagram.png"
            shutil.copy2(png_path, dest)
            log.info("Exported PNG: %s (%d bytes)", dest, dest.stat().st_size)

        # Copy design markdown
        md_path = artifacts.get("design_md", "")
        if md_path and Path(md_path).exists():
            dest = out_dir / "design.md"
            dest.write_text(Path(md_path).read_text(), encoding="utf-8")
            log.info("Exported design MD: %s", dest)
