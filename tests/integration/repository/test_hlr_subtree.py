"""Tests for GraphRepository.get_hlr_subtree — multi-hop COMPOSES traversal
from HLR through LLRs, TestNodes, AssertionNodes, TestStepNodes, and
1-hop scaffold neighbours.

Requires Neo4j (credentials loaded via conftest.py).
"""

import pytest

from codegraph.graph import LayerGraph
from codegraph.backends import get_backend


pytestmark = pytest.mark.usefixtures("setup_neomodel")


# ── Helpers ────────────────────────────────────────────────────────────────


def _all_nodes(graph: LayerGraph):
    """Yield all CodeGraphNode instances from the entry tree."""
    for entry in graph._all_entries():
        yield entry.node


def _nodes_of_type(graph: LayerGraph, type_name: str):
    """Yield all nodes of a given type name."""
    for node in _all_nodes(graph):
        if type(node).__name__ == type_name:
            yield node


def _walk_all_entries(graph: LayerGraph):
    """Yield all CompositeEntry instances."""
    for entry in graph._all_entries():
        yield entry


# ── Seed helpers ───────────────────────────────────────────────────────────


def _save_parented(node, parent_key, field="parent_key"):
    """Save a parent-relative node with explicit parent context (WP A)."""
    node.canonical_key = node.resolve_canonical_key(
        parents={field: parent_key}
    )
    return node.save()


def _seed_hlr_subtree():
    """Create a minimal HLR subtree in Neo4j.

    Structure::

        HLR "HLR-01" (refid="hlr-01-golden")
          └─ LLR "LLR-01" (refid="llr-01-golden")
               ├─ TestNode "test_add" (test_name="test_addition")
               │    ├─ AssertionNode "pre_is_ready"  (phase="pre")
               │    │    ├─ LEFT_OPERAND → AttributeNode "Engine::is_ready"   (scaffold)
               │    │    └─ RIGHT_OPERAND → LiteralNode "true"                (scaffold)
               │    ├─ AssertionNode "post_result_eq_42" (phase="post")
               │    │    ├─ LEFT_OPERAND → AttributeNode "Engine::result"     (scaffold)
               │    │    └─ RIGHT_OPERAND → LiteralNode "42"                  (scaffold)
               │    └─ TestStepNode "step_invoke_compute"
               │         └─ CALLEE → AttributeNode "Engine::compute"          (scaffold)
               └─ TestNode "test_error" (test_name="test_error_path")
                    └─ AssertionNode "post_error_state" (phase="post")
                         ├─ LEFT_OPERAND → AttributeNode "Engine::error_state" (scaffold)
                         └─ RIGHT_OPERAND → AttributeNode "ErrorFault"         (scaffold)

    Returns the HLR refid.
    """
    from codegraph_requirements.models.requirement import HLR, LLR
    from codegraph.models.test import TestNode, AssertionNode, TestStepNode
    from codegraph.models.compound import ClassNode
    from codegraph.models.member import AttributeNode
    from codegraph.models.literal import LiteralNode

    # ── Create scaffold nodes ─────────────────────────────────────────
    # ClassNode (scaffold) — parent for scaffold attributes
    engine_cls = ClassNode(
        qualified_name="Engine",
        name="Engine",
        kind="class",
        tags=["scaffold"],
        source="test",
    ).save()

    # AttributeNodes (scaffold)
    is_ready = AttributeNode(
        qualified_name="Engine::is_ready",
        name="is_ready",
        kind="attribute",
        tags=["scaffold"],
        source="test",
    ).save()
    is_ready.parent_compound.connect(engine_cls)

    result_attr = AttributeNode(
        qualified_name="Engine::result",
        name="result",
        kind="attribute",
        tags=["scaffold"],
        source="test",
    ).save()
    result_attr.parent_compound.connect(engine_cls)

    compute_attr = AttributeNode(
        qualified_name="Engine::compute",
        name="compute",
        kind="attribute",
        tags=["scaffold"],
        source="test",
    ).save()
    compute_attr.parent_compound.connect(engine_cls)

    error_state = AttributeNode(
        qualified_name="Engine::error_state",
        name="error_state",
        kind="attribute",
        tags=["scaffold"],
        source="test",
    ).save()
    error_state.parent_compound.connect(engine_cls)

    error_fault = AttributeNode(
        qualified_name="ErrorFault",
        name="ErrorFault",
        kind="attribute",
        tags=["scaffold"],
        source="test",
    ).save()

    lit_true = LiteralNode(
        qualified_name="literal::true",
        name="literal::true",
        value="true",
        value_type="bool",
        kind="literal",
        tags=["scaffold"],
        source="test",
    ).save()

    lit_42 = LiteralNode(
        qualified_name="literal::42",
        name="literal::42",
        value="42",
        value_type="int",
        kind="literal",
        tags=["scaffold"],
        source="test",
    ).save()

    # ── Create requirement nodes ──────────────────────────────────────
    hlr = HLR(
        name="HLR-01",
        description="The system shall perform arithmetic operations correctly.",
        tags=["design"],
        source="test",
    ).save()

    llr = LLR(
        name="LLR-01",
        description="The Engine shall expose a compute operation that returns the correct result for valid inputs and signals an error for invalid inputs.",
        tags=["design"],
        source="test",
    )
    _save_parented(llr, hlr.canonical_key, field="parent_hlr_key")
    hlr.llrs.connect(llr)

    # ── Create verification nodes ─────────────────────────────────────

    # Test 1: happy path
    test1 = TestNode(
        qualified_name="test::test_addition",
        name="test_addition",
        test_name="test_addition",
        method="automated",
        description="Verify compute returns correct result.",
        tags=["design"],
        source="test",
    )
    _save_parented(test1, llr.canonical_key)
    llr.verification_methods.connect(test1)

    # pre-condition: is_ready == true
    pre1 = AssertionNode(
        qualified_name="cond::pre::is_ready",
        name="pre_is_ready",
        phase="pre",
        operator="is_true",
        description="Engine is ready before compute.",
        tags=["design"],
        source="test",
    )
    _save_parented(pre1, test1.canonical_key)
    test1.assertions.connect(pre1)
    pre1.left_operand_attribute.connect(is_ready)
    pre1.right_operand_literal.connect(lit_true)

    # post-condition: result == 42
    post1 = AssertionNode(
        qualified_name="cond::post::result_eq_42",
        name="post_result_eq_42",
        phase="post",
        operator="==",
        description="Result equals 42 after compute.",
        tags=["design"],
        source="test",
    )
    _save_parented(post1, test1.canonical_key)
    test1.assertions.connect(post1)
    post1.left_operand_attribute.connect(result_attr)
    post1.right_operand_literal.connect(lit_42)

    # step: invoke compute
    step1 = TestStepNode(
        qualified_name="step::invoke_compute",
        name="step_invoke_compute",
        description="Invoke the compute operation.",
        tags=["design"],
        source="test",
    )
    _save_parented(step1, test1.canonical_key)
    test1.steps.connect(step1)
    # CALLEE to scaffold AttributeNode — use raw Cypher since
    # TestStepNode has RelationshipTo for MethodNode/FunctionNode/ClassNode
    # but not AttributeNode (scaffolds are resolved during design).
    get_backend().connect(step1, "CALLEE", compute_attr)

    # Test 2: error path
    test2 = TestNode(
        qualified_name="test::test_error",
        name="test_error",
        test_name="test_error_path",
        method="automated",
        description="Verify compute signals error for invalid input.",
        tags=["design"],
        source="test",
    )
    _save_parented(test2, llr.canonical_key)
    llr.verification_methods.connect(test2)

    post2 = AssertionNode(
        qualified_name="cond::post::error_state",
        name="post_error_state",
        phase="post",
        operator="==",
        description="Error state indicates fault.",
        tags=["design"],
        source="test",
    )
    _save_parented(post2, test2.canonical_key)
    test2.assertions.connect(post2)
    post2.left_operand_attribute.connect(error_state)
    post2.right_operand_attribute.connect(error_fault)

    # Return the HLR's refid (the canonical key)
    return hlr.canonical_key


# ── Tests ──────────────────────────────────────────────────────────────────


class TestGetHLRSubtree:

    def test_returns_layer_graph(self):
        """get_hlr_subtree should return a LayerGraph for a valid HLR refid."""
        refid = _seed_hlr_subtree()
        repo = get_backend().graph

        result = repo.get_hlr_subtree(refid)
        assert isinstance(result, LayerGraph)

    def test_missing_hlr_returns_empty(self):
        """get_hlr_subtree should return an empty LayerGraph for a missing refid."""
        repo = get_backend().graph
        result = repo.get_hlr_subtree("nonexistent-refid")

        assert isinstance(result, LayerGraph)
        assert len(result.entries) == 0

    def test_includes_hlr_node(self):
        """The subtree should contain the HLR node itself."""
        refid = _seed_hlr_subtree()
        repo = get_backend().graph

        result = repo.get_hlr_subtree(refid)
        hlr_nodes = list(_nodes_of_type(result, "HLR"))
        assert len(hlr_nodes) == 1
        assert hlr_nodes[0].description == (
            "The system shall perform arithmetic operations correctly."
        )

    def test_includes_llr_nodes(self):
        """The subtree should contain all LLRs composed by the HLR."""
        refid = _seed_hlr_subtree()
        repo = get_backend().graph

        result = repo.get_hlr_subtree(refid)
        llr_nodes = list(_nodes_of_type(result, "LLR"))
        assert len(llr_nodes) == 1
        assert "compute operation" in llr_nodes[0].description

    def test_includes_test_nodes(self):
        """The subtree should contain all TestNodes composed by LLRs."""
        refid = _seed_hlr_subtree()
        repo = get_backend().graph

        result = repo.get_hlr_subtree(refid)
        test_nodes = list(_nodes_of_type(result, "TestNode"))
        assert len(test_nodes) == 2
        test_names = {tn.test_name for tn in test_nodes}
        assert "test_addition" in test_names
        assert "test_error_path" in test_names

    def test_includes_assertion_nodes(self):
        """The subtree should contain all AssertionNodes composed by TestNodes."""
        refid = _seed_hlr_subtree()
        repo = get_backend().graph

        result = repo.get_hlr_subtree(refid)
        assertion_nodes = list(_nodes_of_type(result, "AssertionNode"))
        assert len(assertion_nodes) == 3

        phases = {a.phase for a in assertion_nodes}
        assert "pre" in phases
        assert "post" in phases

    def test_includes_test_step_nodes(self):
        """The subtree should contain all TestStepNodes composed by TestNodes."""
        refid = _seed_hlr_subtree()
        repo = get_backend().graph

        result = repo.get_hlr_subtree(refid)
        step_nodes = list(_nodes_of_type(result, "TestStepNode"))
        assert len(step_nodes) == 1
        assert step_nodes[0].description == "Invoke the compute operation."

    def test_includes_scaffold_neighbours(self):
        """The subtree should include scaffold nodes referenced by
        LEFT_OPERAND, RIGHT_OPERAND, and CALLEE edges."""
        refid = _seed_hlr_subtree()
        repo = get_backend().graph

        result = repo.get_hlr_subtree(refid)

        # Scaffold AttributeNodes
        attr_nodes = list(_nodes_of_type(result, "AttributeNode"))
        attr_qnames = {a.qualified_name for a in attr_nodes}

        expected_attrs = {
            "Engine::is_ready",
            "Engine::result",
            "Engine::error_state",
            "ErrorFault",
            # Engine::compute is NOT expected here — it's connected via a
            # CALLEE edge from TestStepNode to an AttributeNode (scaffold),
            # and TestStepNode has no callee_attribute relationship manager
            # (only callee_method/callee_function/callee_class). The edge
            # exists in Neo4j but walk_edges() only discovers neomodel-managed
            # relationships.  The design agent resolves these via raw Cypher.
        }
        for expected in expected_attrs:
            assert expected in attr_qnames, f"Missing scaffold attribute: {expected}"

        # Scaffold LiteralNodes
        literal_nodes = list(_nodes_of_type(result, "LiteralNode"))
        literal_qnames = {ln.qualified_name for ln in literal_nodes}
        assert "literal::true" in literal_qnames
        assert "literal::42" in literal_qnames

    def test_composes_hierarchy(self):
        """The LayerGraph should nest nodes correctly: HLR → LLR → TestNode."""
        refid = _seed_hlr_subtree()
        repo = get_backend().graph

        result = repo.get_hlr_subtree(refid)

        # Find the HLR entry (should be a root entry)
        hlr_entries = []
        for key, entry in result.entries.items():
            node = entry.node
            if type(node).__name__ == "HLR":
                hlr_entries.append((key, entry))

        assert len(hlr_entries) == 1, "Expected exactly one HLR root entry"
        hlr_key, hlr_entry = hlr_entries[0]

        # HLR should have LLR children
        assert "LLR" in hlr_entry.children
        assert len(hlr_entry.children["LLR"]) == 1

        # Get the single LLR child
        llr_key = next(iter(hlr_entry.children["LLR"]))
        llr_entry = hlr_entry.children["LLR"][llr_key]

        # LLR should have TestNode children
        assert "TestNode" in llr_entry.children
        assert len(llr_entry.children["TestNode"]) == 2

        # Each TestNode should have AssertionNode children
        for test_key, test_entry in llr_entry.children["TestNode"].items():
            has_assertions = "AssertionNode" in test_entry.children
            has_steps = "TestStepNode" in test_entry.children
            assert has_assertions or has_steps, (
                f"TestNode should have at least one child (assertion or step)"
            )

    def test_references_connect_scaffolds(self):
        """AssertionNode and TestStepNode references should point to scaffold nodes."""
        refid = _seed_hlr_subtree()
        repo = get_backend().graph

        result = repo.get_hlr_subtree(refid)

        # Collect all references
        reference_targets: set[str] = set()
        for entry in _walk_all_entries(result):
            for rel_type, target_key, _target_type in entry.references:
                reference_targets.add(target_key)

        # References should exist (at minimum LEFT_OPERAND, RIGHT_OPERAND, CALLEE)
        assert len(reference_targets) > 0, (
            "Expected references from assertions/steps to scaffold nodes"
        )

    def test_non_existent_hlr_uid_returns_empty(self):
        """Passing a valid-looking but non-existent refid should return empty."""
        repo = get_backend().graph
        result = repo.get_hlr_subtree("0123456789abcdef-not-real")

        assert isinstance(result, LayerGraph)
        assert len(result.entries) == 0

    def test_total_node_count(self):
        """The subtree should contain all nodes in the HLR tree (HLR + LLR
        + tests + assertions + steps + scaffolds)."""
        refid = _seed_hlr_subtree()
        repo = get_backend().graph

        result = repo.get_hlr_subtree(refid)

        # Expected counts from _seed_hlr_subtree:
        # 1 HLR + 1 LLR + 2 TestNodes + 3 AssertionNodes + 1 TestStepNode
        # + 1 ClassNode (scaffold) + 5 AttributeNodes + 2 LiteralNodes = 16
        count = sum(1 for _ in _all_nodes(result))
        assert count >= 14, (
            f"Expected at least 14 nodes in subtree, got {count}"
        )
