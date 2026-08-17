"""Test MemoryGraph container — for_code_node, for_tag, convenience queries."""

import pytest


@pytest.fixture
def populated_graph(neo4j_connection):
    """Create a code node with multiple memory types linked."""
    from codegraph_memory import (
        DecisionNode, ConstraintNode, AssumptionNode, TradeoffNode,
        RationaleNode, InsightNode,
    )
    from codegraph.models.compound import ClassNode
    from codegraph.models.member import MethodNode

    db_layer = ClassNode.save_new(
        name="DatabaseLayer", kind="class",
        qualified_name="test::DatabaseLayer",
        tags=["design"], source="test",
    )
    query_method = MethodNode.save_new(
        name="execute_query", kind="method",
        qualified_name="test::DatabaseLayer::execute_query",
        tags=["design"], source="test",
    )
    db_layer.methods.connect(query_method)

    decision = DecisionNode.save_new(
        qualified_name="memory::test-db-choice",
        name="DB Choice",
        content="Use PostgreSQL for ACID guarantees.",
        tags=["design"], confidence=0.8, source="test",
    )
    decision.motivates_compound.connect(db_layer)

    constraint = ConstraintNode.save_new(
        qualified_name="memory::test-perf-sla",
        name="Performance SLA",
        content="Query latency < 50ms at p99.",
        tags=["design"], confidence=0.9, source="test",
    )
    constraint.constrains_compound.connect(db_layer)
    constraint.constrains_compound.connect(query_method)

    assumption = AssumptionNode.save_new(
        qualified_name="memory::test-cloud-stability",
        name="Cloud Stability",
        content="Same-region deployment, < 1ms latency.",
        tags=["design"], confidence=0.7, source="test",
    )
    assumption.assumes_compound.connect(db_layer)

    tradeoff = TradeoffNode.save_new(
        qualified_name="memory::test-orm-overhead",
        name="ORM Overhead",
        content="SQLAlchemy adds ~20ms per query.",
        tags=["as-built"], confidence=0.9, source="test",
    )
    tradeoff.trades_off_compound.connect(db_layer)

    insight = InsightNode.save_new(
        qualified_name="memory::test-prod-observation",
        name="Production Observation",
        content="ORM overhead significant for reporting dashboard.",
        tags=["as-built"], confidence=0.85, source="test",
    )
    insight.insight_into_compound.connect(db_layer)

    rationale = RationaleNode.save_new(
        qualified_name="memory::test-ci-portability",
        name="CI Portability",
        content="Database abstraction for CI portability with SQLite.",
        tags=["design", "as-built"], confidence=0.95, source="test",
    )
    rationale.explains_compound.connect(db_layer)

    return {
        "db_layer": db_layer,
        "query_method": query_method,
        "decision": decision,
        "constraint": constraint,
        "assumption": assumption,
        "tradeoff": tradeoff,
        "insight": insight,
        "rationale": rationale,
    }


class TestMemoryGraph:
    """Test MemoryGraph container methods."""

    def test_for_code_node(self, populated_graph):
        """for_code_node returns all memory nodes linked to a code node."""
        from codegraph_memory import MemoryGraph

        graph = MemoryGraph.for_code_node("test::DatabaseLayer")
        assert len(graph) >= 6  # decision, constraint, assumption, tradeoff, insight, rationale

        # Check types are correctly inflated
        types = {type(e.memory).__name__ for e in graph}
        assert "DecisionNode" in types
        assert "ConstraintNode" in types
        assert "AssumptionNode" in types
        assert "TradeoffNode" in types
        assert "InsightNode" in types
        assert "RationaleNode" in types

    def test_for_tag(self, populated_graph):
        """for_tag returns all memory nodes matching a tag."""
        from codegraph_memory import MemoryGraph

        graph = MemoryGraph.for_tag("design")
        assert len(graph) >= 4  # decision, constraint, assumption, rationale

        for entry in graph:
            assert "design" in entry.memory.tags

    def test_for_tag_as_built(self, populated_graph):
        """for_tag with 'as-built' returns as-built tagged memories."""
        from codegraph_memory import MemoryGraph

        graph = MemoryGraph.for_tag("as-built")
        assert len(graph) >= 3  # tradeoff, insight, rationale

        for entry in graph:
            assert "as-built" in entry.memory.tags

    def test_constraints_for(self, populated_graph):
        """constraints_for returns all constraints for a code node."""
        from codegraph_memory import MemoryGraph

        constraints = MemoryGraph.constraints_for(populated_graph["db_layer"])
        assert len(constraints) == 1
        assert constraints[0].qualified_name == "memory::test-perf-sla"

    def test_decisions_for(self, populated_graph):
        """decisions_for returns all decisions for a code node."""
        from codegraph_memory import MemoryGraph

        decisions = MemoryGraph.decisions_for(populated_graph["db_layer"])
        assert len(decisions) == 1
        assert decisions[0].qualified_name == "memory::test-db-choice"

    def test_insights_for(self, populated_graph):
        """insights_for returns all insights for a code node."""
        from codegraph_memory import MemoryGraph

        insights = MemoryGraph.insights_for(populated_graph["db_layer"])
        assert len(insights) == 1
        assert insights[0].qualified_name == "memory::test-prod-observation"

    def test_rationales_for(self, populated_graph):
        """rationales_for returns all rationales for a code node."""
        from codegraph_memory import MemoryGraph

        rationales = MemoryGraph.rationales_for(populated_graph["db_layer"])
        assert len(rationales) == 1
        assert rationales[0].qualified_name == "memory::test-ci-portability"

    def test_assumptions_for(self, populated_graph):
        """assumptions_for returns all assumptions for a code node."""
        from codegraph_memory import MemoryGraph

        assumptions = MemoryGraph.assumptions_for(populated_graph["db_layer"])
        assert len(assumptions) == 1
        assert assumptions[0].qualified_name == "memory::test-cloud-stability"

    def test_tradeoffs_for(self, populated_graph):
        """tradeoffs_for returns all tradeoffs for a code node."""
        from codegraph_memory import MemoryGraph

        tradeoffs = MemoryGraph.tradeoffs_for(populated_graph["db_layer"])
        assert len(tradeoffs) == 1
        assert tradeoffs[0].qualified_name == "memory::test-orm-overhead"

    def test_affected_decisions(self, populated_graph):
        """affected_decisions traverses COMPOSES to find linked memories."""
        from codegraph_memory import MemoryGraph

        # DatabaseLayer composes execute_query method.
        # Constraint links to both.  Should find at least the constraint.
        affected = MemoryGraph.affected_decisions(populated_graph["db_layer"])
        assert len(affected) >= 1

    def test_serialize_deserialize(self, populated_graph):
        """serialize/deserialize roundtrips memory data."""
        from codegraph_memory import MemoryGraph

        graph = MemoryGraph.for_code_node("test::DatabaseLayer")
        serialized = graph.serialize()
        assert len(serialized) >= 6

        # ── Verify every entry has the required fields ────────────
        required_fields = {
            "type", "canonical_key", "confidence", "content", "name",
            "qualified_name", "source", "tags", "decided_at", "updated_at",
            "edges", "linked_code_uid", "linked_code_qualified_name", "relation_type",
        }
        for entry in serialized:
            assert required_fields.issubset(entry.keys()), (
                f"Missing fields in {entry['type']}: "
                f"{required_fields - entry.keys()}"
            )
            # type must be a known memory node class
            assert entry["type"] in {
                "DecisionNode", "ConstraintNode", "RationaleNode",
                "AssumptionNode", "TradeoffNode", "InsightNode",
            }, f"Unknown type: {entry['type']}"
            # uid must be a non-empty hex string
            assert isinstance(entry["canonical_key"], str) and entry["canonical_key"].startswith("cg:v1:")
            # edges must be a list
            assert isinstance(entry["edges"], list)
            # linked_code fields must be present (set by for_code_node)
            assert entry["linked_code_qualified_name"] == "test::DatabaseLayer"
            assert entry["relation_type"] is not None

        # ── Verify all six memory types are present ───────────────
        types = {e["type"] for e in serialized}
        assert types == {
            "DecisionNode", "ConstraintNode", "RationaleNode",
            "AssumptionNode", "TradeoffNode", "InsightNode",
        }, f"Expected all 6 types, got: {types}"

        # ── Verify relationship types match memory types ──────────
        type_to_rel = {
            "DecisionNode": "MOTIVATES",
            "ConstraintNode": "CONSTRAINS",
            "RationaleNode": "EXPLAINS",
            "AssumptionNode": "ASSUMES",
            "TradeoffNode": "TRADES_OFF",
            "InsightNode": "INSIGHT_INTO",
        }
        for entry in serialized:
            assert entry["relation_type"] == type_to_rel[entry["type"]], (
                f"{entry['type']} has relation_type={entry['relation_type']}, "
                f"expected {type_to_rel[entry['type']]}"
            )

        # ── Verify ConstraintNode has two edges (class + method) ─
        constraint = next(
            e for e in serialized if e["type"] == "ConstraintNode"
        )
        assert len(constraint["edges"]) == 2, (
            f"ConstraintNode should have 2 edges (ClassNode + MethodNode), "
            f"got {len(constraint['edges'])}"
        )
        edge_types = {e["target_type"] for e in constraint["edges"]}
        assert edge_types == {"ClassNode", "MethodNode"}

        # ── Roundtrip: deserialize → re-serialize ─────────────────
        restored = MemoryGraph.deserialize(serialized)
        assert len(restored) == len(serialized)

        re_serialized = restored.serialize()
        assert len(re_serialized) == len(serialized)

        # Compare field-by-field.  Only `edges` differs because
        # deserialized nodes are in-memory (not persisted in Neo4j),
        # so serialize_edges() returns [].  All other fields — including
        # timestamps — survive the roundtrip because deserialize()
        # inflates them from the dict.
        for orig, restored_entry in zip(serialized, re_serialized):
            for key in orig:
                if key == "edges":
                    continue
                # Compare as strings to handle datetime serialization
                assert str(restored_entry[key]) == str(orig[key]), (
                    f"Field '{key}' mismatch for {orig['type']}: "
                    f"{orig[key]} != {restored_entry[key]}"
                )
            # edges should be empty on deserialized (not persisted)
            assert restored_entry["edges"] == []

        # ── Verify restored types match ───────────────────────────
        restored_types = {e.memory.__class__.__name__ for e in restored}
        assert restored_types == types

    def test_serialize_empty_graph(self, neo4j_connection):
        """Serializing a code node with no memories produces empty list."""
        from codegraph_memory import MemoryGraph
        from codegraph.models.compound import ClassNode

        cls = ClassNode.save_new(
            name="EmptyForSerialize", kind="class",
            qualified_name="test::EmptyForSerialize",
            tags=["design"], source="test",
        )

        graph = MemoryGraph.for_code_node("test::EmptyForSerialize")
        serialized = graph.serialize()
        assert serialized == []
        assert len(graph) == 0

        # Roundtrip empty
        restored = MemoryGraph.deserialize(serialized)
        assert len(restored) == 0
        assert restored.serialize() == []

    def test_serialize_for_tag(self, populated_graph):
        """for_tag serialization includes linked_code fields when include_code=True."""
        from codegraph_memory import MemoryGraph

        # Without include_code — linked_code fields are absent (not added)
        graph = MemoryGraph.for_tag("design")
        serialized = graph.serialize()
        assert len(serialized) >= 4  # decision, constraint, assumption, rationale
        for entry in serialized:
            # linked_code fields are only added when they have values
            assert "linked_code_uid" not in entry
            assert "linked_code_qualified_name" not in entry
            assert "relation_type" not in entry

        # With include_code=True — linked_code fields populated where available
        graph_with_code = MemoryGraph.for_tag("design", include_code=True)
        serialized_with_code = graph_with_code.serialize()
        entries_with_code = [
            e for e in serialized_with_code
            if "linked_code_qualified_name" in e
            and e["linked_code_qualified_name"] is not None
        ]
        assert len(entries_with_code) >= 1

    def test_serialize_to_markdown_file(self, populated_graph, tmp_path):
        """Serialized output can be saved as a markdown code block for review."""
        import json
        from codegraph_memory import MemoryGraph

        graph = MemoryGraph.for_code_node("test::DatabaseLayer")
        serialized = graph.serialize()

        # Write as markdown with JSON code block
        md_path = tmp_path / "memory_graph_serialize_output.md"
        lines = [
            "# MemoryGraph Serialize Output",
            "",
            "Auto-generated golden file from test run.",
            "",
            "```json",
            json.dumps(serialized, indent=2, default=str),
            "```",
            "",
        ]
        md_path.write_text("\n".join(lines))

        # Verify the file is valid markdown with parseable JSON
        content = md_path.read_text()
        assert "```json" in content
        assert "```" in content

        # Extract and re-parse the JSON
        json_start = content.index("```json\n") + len("```json\n")
        json_end = content.index("\n```", json_start)
        json_str = content[json_start:json_end]
        parsed = json.loads(json_str)
        assert len(parsed) == len(serialized)

        # Roundtrip through the saved file
        restored = MemoryGraph.deserialize(parsed)
        assert len(restored) == len(graph)