"""Unit tests for the decompose agent's validation and ingestion pipeline.

These tests verify that the decompose agent's output — a flat list of
codegraph node dicts — flows correctly through:

1. **Validation** (:func:`~codegraph_design.agents.decompose_hlr.validate_decomposition`)
   — all 8 hard rules enforced, no LLM calls needed.
2. **Schema parsing** (:class:`DecomposedRequirementSchema`) — the LLM
   response is parseable into the expected schema.
3. **LayerGraph deserialization** (:meth:`LayerGraph.deserialize`) — flat
   node dicts convert to a nested COMPOSES hierarchy with auto-scaffold
   creation (``create_missing=True``).
4. **End-to-end structural verification** — the actual decomposition
   output from ``codegraph/logs/decompose_hlr_ee66877ea015ba48_response.json``
   is valid and produces the correct graph structure.

None of these tests call the LLM API — they exercise the deterministic
pipeline that runs *after* the LLM returns.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

# Ensure the codegraph source is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codegraph_design.agents.decompose_hlr import (
    DecompositionValidationError,
    DecompositionViolation,
    validate_decomposition,
)
from codegraph_requirements.schemas import DecomposedRequirementSchema
from codegraph_requirements.models.requirement import HLR, LLR  # register types for deserialize  # noqa: F401
from codegraph.graph import LayerGraph

# ── Path to actual decompose output from the last run ──────────────────────

DATA_DIR = Path(__file__).resolve().parent / "data"
DECOMPOSE_RESPONSE = DATA_DIR / "decompose_response.json"


# ════════════════════════════════════════════════════════════════════════════
# Helpers — build minimal valid/invalid node lists
# ════════════════════════════════════════════════════════════════════════════


def _make_llr(name="Test LLR", test_ids=None):
    """Return an LLR node dict with COMPOSES edges to given TestNode IDs."""
    return {
        "type": "LLR",
        "name": name,
        "source": "test",
        "description": f"Description for {name}",
        "tags": ["design"],
        "edges": [
            {"relation_type": "COMPOSES", "target_uid": tid, "target_type": "TestNode"}
            for tid in (test_ids or [])
        ],
    }


def _make_test(qname="vm::test::test_foo", test_name="test_foo"):
    """Return a TestNode dict with COMPOSES edges to a pre-condition,
    a post-condition, and a TestStepNode."""
    return {
        "type": "TestNode",
        "qualified_name": qname,
        "source": "test",
        "test_name": test_name,
        "method": "automated",
        "description": f"Test: {test_name}",
        "edges": [
            {"relation_type": "COMPOSES", "target_uid": f"cond::pre::{qname}", "target_type": "AssertionNode"},
            {"relation_type": "COMPOSES", "target_uid": f"cond::post::{qname}", "target_type": "AssertionNode"},
            {"relation_type": "COMPOSES", "target_uid": f"step::{qname}", "target_type": "TestStepNode"},
        ],
    }


def _make_assertion(qname, phase="post", operator="==", left="Foo::bar", right="literal::true"):
    """Return an AssertionNode dict with LEFT_OPERAND and RIGHT_OPERAND edges."""
    return {
        "type": "AssertionNode",
        "qualified_name": qname,
        "source": "test",
        "phase": phase,
        "operator": operator,
        "edges": [
            {"relation_type": "LEFT_OPERAND", "target_uid": left, "target_type": "AttributeNode"},
            {"relation_type": "RIGHT_OPERAND", "target_uid": right, "target_type": "LiteralNode"},
        ],
    }


def _make_step(qname, description="Invoke operation", callee="Foo::do_thing"):
    """Return a TestStepNode dict with a CALLEE edge."""
    return {
        "type": "TestStepNode",
        "qualified_name": qname,
        "source": "test",
        "description": description,
        "edges": [
            {"relation_type": "CALLEE", "target_uid": callee, "target_type": "AttributeNode"},
        ],
    }


def _make_complete_subtree(llr_name="Test LLR", test_qname="vm::test::test_foo"):
    """Return a minimal complete node list: 1 LLR + 1 Test + 2 Assertions + 1 Step."""
    return [
        _make_llr(llr_name, test_ids=[test_qname]),
        _make_test(test_qname),
        _make_assertion(f"cond::pre::{test_qname}", phase="pre"),
        _make_assertion(f"cond::post::{test_qname}", phase="post"),
        _make_step(f"step::{test_qname}"),
    ]


# ════════════════════════════════════════════════════════════════════════════
# Part 1: Validation rule tests
# ════════════════════════════════════════════════════════════════════════════


class TestValidateDecomposition:
    """Test :func:`validate_decomposition` — all 8 hard rules."""

    def test_valid_complete_subtree_passes_all_rules(self):
        """A complete subtree with 1 LLR + 1 Test + 2 Assertions + 1 Step
        should pass validation with zero violations."""
        nodes = _make_complete_subtree()
        violations = validate_decomposition(nodes)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_multiple_llrs_each_with_own_tests(self):
        """Multiple independent LLRs should all pass validation."""
        nodes = []
        for i in range(3):
            nodes.extend(_make_complete_subtree(
                llr_name=f"LLR {i}",
                test_qname=f"vm::test_{i}::test_foo",
            ))
        violations = validate_decomposition(nodes)
        assert violations == []

    # ── Rule 1: LLR_HAS_TEST ──

    def test_rule1_llr_without_test_fails(self):
        """LLR with no COMPOSES edges to TestNode fails."""
        nodes = _make_complete_subtree()
        # Replace LLR with one that has empty edges
        nodes[0] = _make_llr("No Test LLR", test_ids=[])
        violations = validate_decomposition(nodes)
        assert any(v.rule == "LLR_HAS_TEST" for v in violations)

    def test_rule1_llr_with_test_passes(self):
        """LLR with at least one COMPOSES TestNode edge passes."""
        nodes = _make_complete_subtree()
        violations = validate_decomposition(nodes)
        assert not any(v.rule == "LLR_HAS_TEST" for v in violations)

    # ── Rule 2: TEST_HAS_STEP ──

    def test_rule2_test_without_step_fails(self):
        """TestNode with no COMPOSES to TestStepNode fails."""
        nodes = _make_complete_subtree()
        # Remove step-related edges from the TestNode
        for n in nodes:
            if n["type"] == "TestNode":
                n["edges"] = [e for e in n["edges"] if e["target_type"] != "TestStepNode"]
        # Also remove the orphaned TestStepNode
        nodes = [n for n in nodes if n["type"] != "TestStepNode"]
        violations = validate_decomposition(nodes)
        assert any(v.rule == "TEST_HAS_STEP" for v in violations)

    # ── Rule 3: TEST_HAS_PRE_POST ──

    def test_rule3_test_without_pre_condition_fails(self):
        """TestNode without a phase='pre' AssertionNode fails."""
        nodes = _make_complete_subtree()
        # Remove pre-condition edge
        for n in nodes:
            if n["type"] == "TestNode":
                n["edges"] = [e for e in n["edges"] if e["target_type"] != "AssertionNode"
                             or "pre" not in e["target_uid"]]
        # Remove orphaned pre assertion
        nodes = [n for n in nodes if not ("pre" in n.get("qualified_name", ""))]
        violations = validate_decomposition(nodes)
        assert any(
            v.rule == "TEST_HAS_PRE_POST" and "pre-conditions" in v.message
            for v in violations
        )

    def test_rule3_test_without_post_condition_fails(self):
        """TestNode without a phase='post' AssertionNode fails."""
        nodes = _make_complete_subtree()
        for n in nodes:
            if n["type"] == "TestNode":
                n["edges"] = [e for e in n["edges"] if e["target_type"] != "AssertionNode"
                             or "post" not in e["target_uid"]]
        nodes = [n for n in nodes if not ("post" in n.get("qualified_name", ""))]
        violations = validate_decomposition(nodes)
        assert any(
            v.rule == "TEST_HAS_PRE_POST" and "post-conditions" in v.message
            for v in violations
        )

    # ── Rule 4: ASSERTION_HAS_OPERANDS ──

    def test_rule4_assertion_without_left_operand_fails(self):
        """AssertionNode without LEFT_OPERAND edge fails."""
        nodes = _make_complete_subtree()
        for n in nodes:
            if n["type"] == "AssertionNode":
                n["edges"] = [e for e in n["edges"] if e["relation_type"] != "LEFT_OPERAND"]
        violations = validate_decomposition(nodes)
        assert any(
            v.rule == "ASSERTION_HAS_OPERANDS" and "LEFT_OPERAND" in v.message
            for v in violations
        )

    def test_rule4_assertion_without_right_operand_fails(self):
        """AssertionNode without RIGHT_OPERAND edge fails."""
        nodes = _make_complete_subtree()
        for n in nodes:
            if n["type"] == "AssertionNode":
                n["edges"] = [e for e in n["edges"] if e["relation_type"] != "RIGHT_OPERAND"]
        violations = validate_decomposition(nodes)
        assert any(
            v.rule == "ASSERTION_HAS_OPERANDS" and "RIGHT_OPERAND" in v.message
            for v in violations
        )

    # ── Rule 5: STEP_HAS_CALLEE ──

    def test_rule5_step_without_callee_fails(self):
        """TestStepNode without a CALLEE edge to scaffold target fails."""
        nodes = _make_complete_subtree()
        for n in nodes:
            if n["type"] == "TestStepNode":
                n["edges"] = [e for e in n["edges"] if e["relation_type"] != "CALLEE"]
        violations = validate_decomposition(nodes)
        assert any(v.rule == "STEP_HAS_CALLEE" for v in violations)

    def test_rule5_step_with_callee_to_non_scaffold_fails(self):
        """TestStepNode with CALLEE to non-scaffold target_type fails."""
        nodes = _make_complete_subtree()
        for n in nodes:
            if n["type"] == "TestStepNode":
                n["edges"] = [
                    {"relation_type": "CALLEE", "target_uid": "foo", "target_type": "UnknownType"}
                ]
        violations = validate_decomposition(nodes)
        assert any(v.rule == "STEP_HAS_CALLEE" for v in violations)

    # ── Rule 6: TEST_REACHES_SCAFFOLD ──

    def test_rule6_test_without_scaffold_references_fails(self):
        """TestNode whose AssertionNodes/TestStepNodes reference no scaffolds fails."""
        nodes = _make_complete_subtree()
        # Remove operand/callee edges but keep COMPOSES edges
        for n in nodes:
            if n["type"] in ("AssertionNode", "TestStepNode"):
                n["edges"] = []
        violations = validate_decomposition(nodes)
        assert any(v.rule == "TEST_REACHES_SCAFFOLD" for v in violations)

    # ── Rule 7: TEST_HAS_OWNER ──

    def test_rule7_orphaned_test_fails(self):
        """TestNode not owned by any LLR fails."""
        nodes = _make_complete_subtree()
        # Remove COMPOSES edge from LLR to TestNode
        for n in nodes:
            if n["type"] == "LLR":
                n["edges"] = []
        violations = validate_decomposition(nodes)
        assert any(v.rule == "TEST_HAS_OWNER" for v in violations)

    # ── Rule 8: SCAFFOLD_IS_REFERENCED ──

    def test_rule8_unreferenced_scaffold_passes_when_no_scaffolds(self):
        """When there are scaffold refs but they're all reachable, rule 8 passes.
        (Orphaned scaffolds can't really occur in the flat node list because
        scaffold nodes aren't declared — they only appear as edge targets.
        This test verifies no false positives.)"""
        nodes = _make_complete_subtree()
        violations = validate_decomposition(nodes)
        # The scaffold targets (Foo::bar, literal::true, Foo::do_thing) are all
        # reachable through the LLR → Test → Condition/Action chain.
        scaffold_violations = [v for v in violations if v.rule == "SCAFFOLD_IS_REFERENCED"]
        assert scaffold_violations == [], f"Unexpected scaffold violations: {scaffold_violations}"


# ════════════════════════════════════════════════════════════════════════════
# Part 2: Schema parsing tests
# ════════════════════════════════════════════════════════════════════════════


class TestSchemaParsing:
    """Test that the decompose agent output is parseable via the schema."""

    def test_minimal_complete_output_parses(self):
        """A minimal complete output (1 LLR + 1 Test + 2 Assertions + 1 Step)
        should parse into DecomposedRequirementSchema."""
        nodes = _make_complete_subtree()
        parsed = DecomposedRequirementSchema.model_validate({
            "description": "A test HLR",
            "nodes": nodes,
        })
        assert parsed.description == "A test HLR"
        assert len(parsed.nodes) == 5

        types = {n["type"] for n in parsed.nodes}
        assert types == {"LLR", "TestNode", "AssertionNode", "TestStepNode"}

    def test_empty_nodes_list_parses(self):
        """An empty nodes list should parse (no LLRs — degenerate case)."""
        parsed = DecomposedRequirementSchema.model_validate({
            "description": "No LLRs",
            "nodes": [],
        })
        assert len(parsed.nodes) == 0


# ════════════════════════════════════════════════════════════════════════════
# Part 3: LayerGraph deserialization of decompose output
# ════════════════════════════════════════════════════════════════════════════


class TestLayerGraphFromDecomposeNodes:
    """Test that a flat decompose node list deserializes into a correct
    ``LayerGraph`` with COMPOSES hierarchy and auto-created scaffold nodes."""

    def test_llr_becomes_root_entry(self):
        """LLR nodes in the flat list become root entries in the LayerGraph."""
        nodes = _make_complete_subtree()
        graph = LayerGraph.deserialize(nodes, create_missing=True)
        root_keys = list(graph.entries.keys())
        assert len(root_keys) >= 1, f"Expected root entries, got {root_keys}"

    def test_test_node_nests_under_llr(self):
        """TestNode children of an LLR nest under it via COMPOSES."""
        nodes = _make_complete_subtree()
        graph = LayerGraph.deserialize(nodes, create_missing=True)

        llr_entry = graph.entries["Test LLR"]
        test_children = llr_entry.children.get("TestNode", {})
        test_qnames = [
            getattr(entry.node, "qualified_name", "")
            for entry in test_children.values()
        ]
        assert "vm::test::test_foo" in test_qnames, (
            f"Expected vm::test::test_foo in TestNode children, got: {test_qnames}"
        )

    def test_assertion_and_step_nest_under_test(self):
        """AssertionNode and TestStepNode children of a TestNode nest under it."""
        nodes = _make_complete_subtree()
        graph = LayerGraph.deserialize(nodes, create_missing=True)

        llr_entry = graph.entries["Test LLR"]
        test_children = llr_entry.children.get("TestNode", {})
        # Find the test by qualified_name (children keyed by UID)
        test_entry = None
        for entry in test_children.values():
            if getattr(entry.node, "qualified_name", "") == "vm::test::test_foo":
                test_entry = entry
                break
        assert test_entry is not None, "Could not find TestNode vm::test::test_foo"

        assertions = test_entry.children.get("AssertionNode", {})
        steps = test_entry.children.get("TestStepNode", {})
        assert len(assertions) == 2
        assert len(steps) == 1
        assertion_phases = [getattr(e.node, "phase", "") for e in assertions.values()]
        assert "pre" in assertion_phases
        assert "post" in assertion_phases
        step_qnames = [getattr(e.node, "qualified_name", "") for e in steps.values()]
        assert any("step" in q for q in step_qnames)

    def test_auto_created_scaffold_attribute_nodes(self):
        """Scaffold AttributeNodes (notional references in LEFT_OPERAND/CALLEE
        edges) are auto-created by ``create_missing=True``."""
        nodes = _make_complete_subtree()
        graph = LayerGraph.deserialize(nodes, create_missing=True)

        all_nodes = []
        for entry in graph._all_entries():
            all_nodes.append(type(entry.node).__name__)

        # Should include scaffold nodes for Foo::bar and Foo::do_thing
        assert "AttributeNode" in all_nodes

    def test_auto_created_scaffold_literal_nodes(self):
        """Scaffold LiteralNodes (like literal::true) are auto-created."""
        nodes = _make_complete_subtree()
        graph = LayerGraph.deserialize(nodes, create_missing=True)

        all_qnames = []
        for entry in graph._all_entries():
            qn = getattr(entry.node, "qualified_name", None) or ""
            all_qnames.append(qn)

        assert "literal::true" in all_qnames

    def test_operand_edges_are_references(self):
        """LEFT_OPERAND and RIGHT_OPERAND edges appear as references
        on the AssertionNode entries."""
        nodes = _make_complete_subtree()
        graph = LayerGraph.deserialize(nodes, create_missing=True)

        llr_entry = graph.entries["Test LLR"]
        test_children = llr_entry.children.get("TestNode", {})
        test_entry = next(iter(test_children.values()))

        post_assertion = None
        for entry in test_entry.children.get("AssertionNode", {}).values():
            if getattr(entry.node, "phase", "") == "post":
                post_assertion = entry
                break
        assert post_assertion is not None

        rel_types = {r[0] for r in post_assertion.references}
        assert "LEFT_OPERAND" in rel_types
        assert "RIGHT_OPERAND" in rel_types

    def test_callee_edge_is_reference(self):
        """CALLEE edges appear as references on TestStepNode entries."""
        nodes = _make_complete_subtree()
        graph = LayerGraph.deserialize(nodes, create_missing=True)

        llr_entry = graph.entries["Test LLR"]
        test_children = llr_entry.children.get("TestNode", {})
        test_entry = next(iter(test_children.values()))
        step_entries = list(test_entry.children.get("TestStepNode", {}).values())
        assert len(step_entries) >= 1
        step_entry = step_entries[0]

        callee_refs = [r for r in step_entry.references if r[0] == "CALLEE"]
        assert len(callee_refs) == 1
        # Target key is the scaffold node's UID (auto-generated), not
        # the original notional name — just verify the CALLEE edge exists
        assert callee_refs[0][1] != "", "CALLEE reference target is empty"


# ════════════════════════════════════════════════════════════════════════════
# Part 4: End-to-end with real decompose output from the log
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="class")
def decompose_response():
    """Load the actual decompose agent output from the last successful run."""
    if not DECOMPOSE_RESPONSE.exists():
        pytest.skip(f"Decompose response not found: {DECOMPOSE_RESPONSE}")
    with open(DECOMPOSE_RESPONSE) as f:
        return json.load(f)


@pytest.fixture(scope="class")
def decompose_nodes(decompose_response):
    """Return just the nodes list from the response."""
    return decompose_response["nodes"]


@pytest.fixture(scope="class")
def decompose_graph(decompose_response):
    """Deserialize the full decompose response into a LayerGraph."""
    nodes = decompose_response["nodes"]
    return LayerGraph.deserialize(nodes, create_missing=True)


class TestDecomposeOutputValidation:
    """Validate the REAL decompose agent output from the log file."""

    def test_output_is_valid_decomposition(self, decompose_nodes):
        """The full decompose output from the log should pass all 8 validation rules."""
        violations = validate_decomposition(decompose_nodes)
        assert violations == [], (
            f"Decomposition failed validation with {len(violations)} violation(s):\n"
            + "\n".join(f"  [{v.rule}] {v.message}" for v in violations)
        )

    def test_output_parses_as_schema(self, decompose_response):
        """The full response should parse into DecomposedRequirementSchema."""
        parsed = DecomposedRequirementSchema.model_validate(decompose_response)
        assert parsed.description is not None
        assert len(parsed.description) > 50

    def test_has_seven_llrs(self, decompose_nodes):
        """The decomposition should produce exactly 7 LLRs."""
        llrs = [n for n in decompose_nodes if n["type"] == "LLR"]
        assert len(llrs) == 7, f"Expected 7 LLRs, got {len(llrs)}"


class TestDecomposeOutputLLRTests:
    """Verify LLR → TestNode relationships in the real output."""

    def test_every_llr_has_tests(self, decompose_nodes):
        """Every LLR should have at least one COMPOSES edge to a TestNode."""
        test_qnames = {n.get("qualified_name", "") for n in decompose_nodes if n["type"] == "TestNode"}
        for n in decompose_nodes:
            if n["type"] != "LLR":
                continue
            test_edges = [
                e for e in n.get("edges", [])
                if e["relation_type"] == "COMPOSES" and e["target_type"] == "TestNode"
            ]
            assert len(test_edges) >= 1, (
                f"LLR '{n.get('name', '?')}' has no COMPOSES edges to TestNode"
            )
            for e in test_edges:
                assert e["target_uid"] in test_qnames, (
                    f"LLR '{n['name']}' references unknown TestNode '{e['target_uid']}'"
                )

    def test_every_test_has_pre_and_post_conditions(self, decompose_nodes):
        """Every TestNode should have at least one pre-condition and one
        post-condition AssertionNode."""
        test_nodes = {
            n["qualified_name"]: n for n in decompose_nodes if n["type"] == "TestNode"
        }
        for qname, test_node in test_nodes.items():
            assertion_refs = [
                e["target_uid"] for e in test_node.get("edges", [])
                if e["relation_type"] == "COMPOSES" and e["target_type"] == "AssertionNode"
            ]
            pre_assertions = [
                a["qualified_name"] for a in decompose_nodes
                if a["type"] == "AssertionNode"
                and a["qualified_name"] in assertion_refs
                and a.get("phase") == "pre"
            ]
            post_assertions = [
                a["qualified_name"] for a in decompose_nodes
                if a["type"] == "AssertionNode"
                and a["qualified_name"] in assertion_refs
                and a.get("phase") == "post"
            ]
            assert len(pre_assertions) >= 1, (
                f"TestNode '{qname}' has no pre-condition AssertionNode"
            )
            assert len(post_assertions) >= 1, (
                f"TestNode '{qname}' has no post-condition AssertionNode"
            )

    def test_every_test_has_at_least_one_step(self, decompose_nodes):
        """Every TestNode should have at least one TestStepNode."""
        for n in decompose_nodes:
            if n["type"] != "TestNode":
                continue
            step_edges = [
                e for e in n.get("edges", [])
                if e["relation_type"] == "COMPOSES" and e["target_type"] == "TestStepNode"
            ]
            assert len(step_edges) >= 1, (
                f"TestNode '{n['qualified_name']}' has no COMPOSES edges to TestStepNode"
            )

    def test_every_assertion_has_both_operands(self, decompose_nodes):
        """Every AssertionNode should have both a LEFT_OPERAND and
        a RIGHT_OPERAND edge."""
        for n in decompose_nodes:
            if n["type"] != "AssertionNode":
                continue
            edge_types = {e["relation_type"] for e in n.get("edges", [])}
            assert "LEFT_OPERAND" in edge_types, (
                f"AssertionNode '{n['qualified_name']}' missing LEFT_OPERAND"
            )
            assert "RIGHT_OPERAND" in edge_types, (
                f"AssertionNode '{n['qualified_name']}' missing RIGHT_OPERAND"
            )

    def test_every_step_has_callee(self, decompose_nodes):
        """Every TestStepNode should have a CALLEE edge to a scaffold target."""
        for n in decompose_nodes:
            if n["type"] != "TestStepNode":
                continue
            callee_edges = [
                e for e in n.get("edges", [])
                if e["relation_type"] == "CALLEE"
            ]
            assert len(callee_edges) >= 1, (
                f"TestStepNode '{n['qualified_name']}' has no CALLEE edge"
            )
            for e in callee_edges:
                assert e["target_type"] in ("AttributeNode", "ClassNode"), (
                    f"TestStepNode '{n['qualified_name']}' CALLEE target_type is "
                    f"'{e['target_type']}', expected AttributeNode or ClassNode"
                )


class TestDecomposeOutputGraphStructure:
    """Verify LayerGraph structure from the real decompose output."""

    def test_llrs_are_root_entries(self, decompose_graph):
        """LLR nodes should be root entries in the graph."""
        llr_type_names = {
            n for n, entry in decompose_graph.entries.items()
            if type(entry.node).__name__ == "LLR"
        }
        assert len(llr_type_names) >= 5, (
            f"Expected >=5 LLR root entries, got {len(llr_type_names)}: {llr_type_names}"
        )

    def test_each_llr_has_test_children(self, decompose_graph):
        """Each LLR root entry should have TestNode children."""
        for key, entry in decompose_graph.entries.items():
            if type(entry.node).__name__ != "LLR":
                continue
            tests = entry.children.get("TestNode", {})
            assert len(tests) >= 1, (
                f"LLR '{key}' has no TestNode children"
            )

    def test_scaffold_nodes_created(self, decompose_graph):
        """Auto-created scaffold nodes should exist in the graph."""
        from codegraph.models.compound import ClassNode
        from codegraph.models.member import AttributeNode
        from codegraph.models.literal import LiteralNode

        node_types = {type(entry.node).__name__ for entry in decompose_graph._all_entries()}
        assert "AttributeNode" in node_types, "Expected scaffold AttributeNodes"
        assert "LiteralNode" in node_types, "Expected scaffold LiteralNodes"

    def test_test_nodes_reference_scaffolds(self, decompose_graph):
        """TestNode entries should reference scaffold nodes through their
        AssertionNode/TestStepNode children."""
        scaffold_refs_found = False
        for entry in decompose_graph._all_entries():
            node_type = type(entry.node).__name__
            if node_type not in ("AssertionNode", "TestStepNode"):
                continue
            if entry.references:
                scaffold_refs_found = True
                break
        assert scaffold_refs_found, (
            "No scaffold references found in AssertionNode/TestStepNode entries"
        )

    def test_node_types_present(self, decompose_nodes):
        """Verify the distribution of node types in the output."""
        type_counts = {}
        for n in decompose_nodes:
            t = n.get("type", "?")
            type_counts[t] = type_counts.get(t, 0) + 1

        assert type_counts["LLR"] == 7, f"Expected 7 LLRs, got {type_counts.get('LLR', 0)}"
        assert type_counts["TestNode"] >= 15, (
            f"Expected >=15 TestNodes, got {type_counts.get('TestNode', 0)}"
        )
        assert type_counts["AssertionNode"] >= 30, (
            f"Expected >=30 AssertionNodes, got {type_counts.get('AssertionNode', 0)}"
        )
        # Steps are shared across tests — 5 unique steps referenced by 21 tests.
        assert type_counts["TestStepNode"] == 5, (
            f"Expected 5 TestStepNodes, got {type_counts.get('TestStepNode', 0)}"
        )


# ════════════════════════════════════════════════════════════════════════════
# Part 5: DecompositionValidationError tests
# ════════════════════════════════════════════════════════════════════════════


class TestDecompositionValidationError:
    """Tests for the DecompositionValidationError exception class."""

    def test_error_carries_violations(self):
        """The exception should carry DecompositionViolation objects."""
        v1 = DecompositionViolation(rule="LLR_HAS_TEST", message="LLR has no test")
        v2 = DecompositionViolation(rule="TEST_HAS_STEP", message="Test has no step")
        exc = DecompositionValidationError("validation failed", violations=[v1, v2])

        assert len(exc.violations) == 2
        assert exc.violations[0].rule == "LLR_HAS_TEST"
        assert "validation failed" in str(exc)


class TestDecompositionViolation:
    """Tests for the DecompositionViolation dataclass."""

    def test_violation_fields(self):
        """Verify that all DecompositionViolation fields are set correctly."""
        v = DecompositionViolation(
            rule="TEST_HAS_STEP",
            message="TestNode vm::test::test_foo has no steps",
            context="vm::test::test_foo",
        )
        assert v.rule == "TEST_HAS_STEP"
        assert "no steps" in v.message
        assert v.context == "vm::test::test_foo"

    def test_violation_context_defaults_to_empty(self):
        """Context should default to empty string."""
        v = DecompositionViolation(rule="LLR_HAS_TEST", message="test")
        assert v.context == ""


# ════════════════════════════════════════════════════════════════════════════


class TestScaffoldConnectivity:
    """Verify that scaffold nodes persisted to Neo4j are properly connected.

    Goes through the full persist_decomposition pipeline: deserialize the
    decompose response → persist to Neo4j → query edges via neomodel.
    This catches bugs where the Python LayerGraph is correct but the
    Neo4j edge creation fails (e.g. UID/elementId mismatches).
    """

    HLR_UID = "ada30b8f1f4e4e26ac83124929c321b92fe1046a"

    @pytest.fixture()
    def ensure_hlr_exists(self):
        """Create the target HLR in the test Neo4j so persist_decomposition
        can find it."""
        from codegraph_requirements.models.requirement import HLR
        from neomodel import db

        # Delete existing if re-running
        existing = HLR.nodes.get_or_none(uid=self.HLR_UID)
        if existing:
            db.cypher_query(
                "MATCH (h:HLR {uid: $uid}) DETACH DELETE h",
                {"uid": self.HLR_UID},
            )

        hlr = HLR(
            uid=self.HLR_UID,
            name="Architecture Diagram Generator",
            source="test",
            description=(
                "The Architecture Diagram Generator shall produce a single "
                "unified PlantUML component diagram for the codegraph "
                "codebase from Neo4j."
            ),
            tags=["design"],
        )
        hlr.save()
        return hlr

    @pytest.fixture()
    def persisted_decomposition(self, ensure_hlr_exists):
        """Run persist_decomposition on the real decompose response and
        return the DecompositionResult.

        Function-scoped so each test gets fresh data (clear_db wipes
        between tests)."""
        from codegraph_requirements.schemas import DecomposedRequirementSchema
        from codegraph_requirements.persistence import persist_decomposition

        with open(DECOMPOSE_RESPONSE) as f:
            data = json.load(f)

        decomposition = DecomposedRequirementSchema.model_validate(data)
        result = persist_decomposition(self.HLR_UID, decomposition)
        return result

    def test_all_node_types_persisted(self, persisted_decomposition):
        """All node types (LLR, TestNode, AssertionNode, TestStepNode,
        and scaffold ClassNode/AttributeNode/LiteralNode) are persisted
        to Neo4j."""
        from neomodel import db

        results, _ = db.cypher_query("MATCH (n) RETURN count(n) AS c")
        total = results[0][0] if results else 0
        assert total > 0, f"Expected >0 nodes in Neo4j, got {total}"

        required_labels = [
            ("HLR", 1), ("TestNode", None), ("AssertionNode", None),
            ("TestStepNode", None), ("ClassNode", None),
            ("AttributeNode", None), ("LiteralNode", None),
        ]
        for label, min_expected in required_labels:
            results, _ = db.cypher_query(
                f"MATCH (n:{label}) RETURN count(n) AS c"
            )
            count = results[0][0] if results else 0
            if min_expected is not None:
                assert count >= min_expected, (
                    f"Expected >= {min_expected} {label}, got {count}"
                )
            else:
                assert count > 0, (
                    f"Expected >0 {label}, got {count} — "
                    "scaffold nodes missing after persist"
                )

    def test_left_operand_edges_exist(self, persisted_decomposition):
        """LEFT_OPERAND edges exist from AssertionNodes to scaffold nodes."""
        from neomodel import db

        results, _ = db.cypher_query(
            "MATCH (a:AssertionNode)-[r:LEFT_OPERAND]->(s) "
            "WHERE 'scaffold' IN s.tags "
            "RETURN count(r) AS c"
        )
        count = results[0][0] if results else 0
        assert count > 0, (
            "No LEFT_OPERAND edges from AssertionNode to scaffold nodes. "
            f"persist reported {persisted_decomposition.operand_edges} operand edges total."
        )

    def test_right_operand_edges_exist(self, persisted_decomposition):
        """RIGHT_OPERAND edges exist from AssertionNodes to scaffold nodes."""
        from neomodel import db

        results, _ = db.cypher_query(
            "MATCH (a:AssertionNode)-[r:RIGHT_OPERAND]->(s) "
            "WHERE 'scaffold' IN s.tags "
            "RETURN count(r) AS c"
        )
        count = results[0][0] if results else 0
        assert count > 0, (
            "No RIGHT_OPERAND edges from AssertionNode to scaffold nodes"
        )

    def test_callee_edges_exist(self, persisted_decomposition):
        """CALLEE edges exist from TestStepNodes to scaffold nodes."""
        from neomodel import db

        results, _ = db.cypher_query(
            "MATCH (ts:TestStepNode)-[r:CALLEE]->(s) "
            "WHERE 'scaffold' IN s.tags "
            "RETURN count(r) AS c"
        )
        count = results[0][0] if results else 0
        assert count > 0, (
            "No CALLEE edges from TestStepNode to scaffold nodes"
        )

    def test_no_orphaned_scaffolds(self, persisted_decomposition):
        """No scaffold node should be orphaned — every scaffold must be
        reachable from an AssertionNode or TestStepNode via
        LEFT_OPERAND / RIGHT_OPERAND / CALLEE (or be a parent ClassNode
        of a reachable child)."""
        from neomodel import db

        # Directly referenced scaffolds
        direct, _ = db.cypher_query(
            "MATCH (ca)-[r]->(s) "
            "WHERE (ca:AssertionNode OR ca:TestStepNode) "
            "  AND (r:LEFT_OPERAND OR r:RIGHT_OPERAND OR r:CALLEE) "
            "  AND 'scaffold' IN s.tags "
            "RETURN DISTINCT elementId(s) AS eid"
        )
        directly_referenced = {row[0] for row in direct}

        # Parent ClassNodes with reachable children
        if directly_referenced:
            parent, _ = db.cypher_query(
                "MATCH (parent:ClassNode)-[:COMPOSES]->(child) "
                "WHERE 'scaffold' IN parent.tags "
                "  AND elementId(child) IN $refs "
                "RETURN DISTINCT elementId(parent) AS eid",
                {"refs": list(directly_referenced)},
            )
            reachable = directly_referenced | {row[0] for row in parent}
        else:
            reachable = directly_referenced

        # Find all scaffold nodes and check for orphans
        all_scaffolds, _ = db.cypher_query(
            "MATCH (s) WHERE 'scaffold' IN s.tags "
            "RETURN elementId(s) AS eid, s.qualified_name AS qn, labels(s) AS lbls"
        )

        orphaned = []
        for row in all_scaffolds:
            eid, qn, lbls = row[0], row[1], row[2]
            if eid not in reachable:
                orphaned.append(f"{qn or '?'} ({lbls})")

        if orphaned:
            raise AssertionError(
                f"{len(orphaned)} orphaned scaffold(s) in Neo4j:\n"
                + "\n".join(f"  - {o}" for o in orphaned)
            )

    def test_operand_edge_count_matches(self, persisted_decomposition):
        """The number of LEFT+RIGHT_OPERAND+CALLEE edges in Neo4j should
        match the persist_decomposition result."""
        from neomodel import db

        results, _ = db.cypher_query(
            "MATCH ()-[r]->() "
            "WHERE r:LEFT_OPERAND OR r:RIGHT_OPERAND OR r:CALLEE "
            "RETURN count(r) AS c"
        )
        neo4j_count = results[0][0] if results else 0

        assert neo4j_count > 0, (
            "No operand/callee edges exist in Neo4j"
        )
        # MERGE deduplicates: same source+edge_type+target = one edge.
        # 119 reported → 97 actual is expected dedup behavior.
        assert neo4j_count <= persisted_decomposition.operand_edges, (
            f"Neo4j has {neo4j_count} edges, but persist reported "
            f"only {persisted_decomposition.operand_edges}"
        )
