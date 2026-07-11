"""Integration tests for the design reconciliation pipeline.

These tests verify that the design agent's reconciliation step — which
updates scaffold nodes in place to become design nodes — produces a
Neo4j graph with **valid, non-conflicting labels** on every node.

The pipeline:

1. **Persist decomposition** from the decompose agent's output
   (``decompose_response.json``) into Neo4j — this creates scaffold
   ``AttributeNode`` / ``ClassNode`` / ``LiteralNode`` nodes with
   ``tags=["scaffold"]``.

2. **Reconcile design** from the design agent's output
   (``design_response.json``) — this matches design nodes to scaffold
   nodes by last segment name and updates them in place, including
   label migration (e.g. ``AttributeNode`` → ``MethodNode``).

3. **Verify label validity** — query Neo4j for nodes whose label sets
   do not match any valid model class combination.

The key bug being tested: scaffold ``AttributeNode`` nodes matched to
design ``MethodNode`` nodes must end up with ONLY ``MethodNode`` +
``MemberNode`` labels, NOT ``MethodNode`` + ``MemberNode`` +
``AttributeNode`` (three-label conflict).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent / "data"
DECOMPOSE_RESPONSE = DATA_DIR / "decompose_response.json"
DESIGN_RESPONSE = DATA_DIR / "design_response.json"

HLR_UID = "ee66877ea015ba4846c010687319a855b5450a57"


# ════════════════════════════════════════════════════════════════════════════
# Valid label set definitions (mirrors model hierarchy)
# ════════════════════════════════════════════════════════════════════════════

# Each entry is a frozenset of labels that a node of that type should have.
# A node's labels must be EXACTLY one of these sets (or a subset within
# the same family if the DB doesn't have the parent label — relax to
# allow the concrete label alone).

_VALID_COMPOUND_LABELS: list[frozenset[str]] = [
    frozenset({"ClassNode", "CompoundNode"}),
    frozenset({"InterfaceNode", "CompoundNode"}),
    frozenset({"EnumNode", "CompoundNode"}),
    frozenset({"UnionNode", "CompoundNode"}),
    frozenset({"ModuleNode", "CompoundNode"}),
    frozenset({"ClassNode"}),        # may exist without parent
    frozenset({"InterfaceNode"}),    # may exist without parent
    frozenset({"EnumNode"}),         # may exist without parent
    frozenset({"UnionNode"}),        # may exist without parent
    frozenset({"ModuleNode"}),       # may exist without parent
]

_VALID_MEMBER_LABELS: list[frozenset[str]] = [
    frozenset({"MethodNode", "MemberNode"}),
    frozenset({"AttributeNode", "MemberNode"}),
    frozenset({"EnumValueNode", "MemberNode"}),
    frozenset({"FunctionNode", "MemberNode"}),
    frozenset({"DefineNode", "MemberNode"}),
    frozenset({"MethodNode"}),       # may exist without parent
    frozenset({"AttributeNode"}),    # may exist without parent
    frozenset({"EnumValueNode"}),    # may exist without parent
    frozenset({"FunctionNode"}),     # may exist without parent
    frozenset({"DefineNode"}),       # may exist without parent
]

_VALID_SINGLE_LABELS: list[frozenset[str]] = [
    frozenset({"ImplementationNode"}),
    frozenset({"NamespaceNode"}),
    frozenset({"FileNode"}),
    frozenset({"ParameterNode"}),
    frozenset({"LiteralNode"}),
    frozenset({"TestNode"}),
    frozenset({"AssertionNode"}),
    frozenset({"TestStepNode"}),
    frozenset({"TestFixtureNode"}),
    frozenset({"HLR"}),
    frozenset({"LLR"}),
    frozenset({"Component"}),
    frozenset({"ProjectMeta"}),
    frozenset({"Language"}),
    frozenset({"Dependency"}),
]

ALL_VALID_LABEL_SETS = (
    _VALID_COMPOUND_LABELS + _VALID_MEMBER_LABELS + _VALID_SINGLE_LABELS
)


def _node_labels_valid(labels: list[str]) -> tuple[bool, str]:
    """Return (is_valid, reason) for a Neo4j node's label list.

    A node's label set is valid if it matches (or is a subset of) exactly
    one valid label set pattern.  The key conflict is when a single node
    has labels from TWO different concrete types in the same family
    (e.g. ``MethodNode`` + ``AttributeNode``).
    """
    label_set = frozenset(labels)
    for valid_set in ALL_VALID_LABEL_SETS:
        if label_set.issubset(valid_set):
            return True, ""
    return False, f"labels {sorted(labels)} do not match any valid model"


def _find_conflicting_nodes():
    """Query Neo4j for all nodes with non-lookup labels and return
    (qualified_name, labels, reason) for every invalid node."""
    from neomodel import db

    results, _ = db.cypher_query(
        "MATCH (n) "
        "RETURN coalesce(n.qualified_name, '(none)') AS qn, labels(n) AS lbls "
        "ORDER BY qn"
    )
    conflicts = []
    for row in results:
        qn, lbls = row[0], row[1]
        if not lbls:
            continue
        is_valid, reason = _node_labels_valid(lbls)
        if not is_valid:
            conflicts.append((qn, lbls, reason))
    return conflicts


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def ensure_hlr_exists():
    """Create the target HLR in the test Neo4j so persist_decomposition
    can find it."""
    from codegraph_requirements.models.requirement import HLR
    from neomodel import db

    existing = HLR.nodes.get_or_none(uid=HLR_UID)
    if existing:
        db.cypher_query(
            "MATCH (h:HLR {uid: $uid}) DETACH DELETE h",
            {"uid": HLR_UID},
        )

    hlr = HLR(
        uid=HLR_UID,
        name="Architecture Diagram Generator",
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
def persisted_decomposition(ensure_hlr_exists):
    """Persist the decompose response to Neo4j (creates scaffold nodes)."""
    from codegraph_requirements.schemas import DecomposedRequirementSchema
    from codegraph_requirements.persistence import persist_decomposition

    with open(DECOMPOSE_RESPONSE) as f:
        data = json.load(f)

    decomposition = DecomposedRequirementSchema.model_validate(data)
    result = persist_decomposition(HLR_UID, decomposition)
    return result


@pytest.fixture()
def design_data():
    """Load the design response JSON."""
    with open(DESIGN_RESPONSE) as f:
        return json.load(f)


# ════════════════════════════════════════════════════════════════════════════
# Part 1: Label validity after design reconciliation
# ════════════════════════════════════════════════════════════════════════════


class TestDesignLabelMigration:
    """Verify that reconciling design nodes onto scaffold nodes produces
    valid Neo4j labels — no node has conflicting concrete-type labels
    (e.g. ``MethodNode`` + ``AttributeNode``)."""

    def test_after_decompose_labels_are_valid(self, persisted_decomposition):
        """After persist_decomposition (scaffold only), all nodes should
        have valid labels."""
        conflicts = _find_conflicting_nodes()
        assert conflicts == [], (
            f"Found {len(conflicts)} node(s) with invalid labels "
            "after decomposition persist:\n"
            + "\n".join(
                f"  {qn}: {lbls} — {reason}"
                for qn, lbls, reason in conflicts
            )
        )

    def test_after_design_reconciliation_labels_are_valid(
        self, persisted_decomposition, design_data
    ):
        """After design reconciliation, all nodes MUST have valid labels.

        This is the critical test: the design reconciliation step
        migrates scaffold ``AttributeNode`` → design ``MethodNode``
        and other type conversions in place.  If label removal fails,
        nodes end up with both ``AttributeNode`` and ``MethodNode``
        labels, which breaks graph resolution.
        """
        from codegraph_design.agents.design_oo import (
            _reconcile_design_with_scaffold,
        )

        design_nodes = design_data["design"]
        recon = _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        # Basic sanity: reconciliation should succeed
        assert recon["nodes_updated"] >= 1, (
            "Expected at least 1 scaffold node to be updated to design"
        )
        assert recon["scaffold_retaged"] >= 1, (
            "Expected at least 1 scaffold node to be retagged to design"
        )

        # The real check: no conflicting labels
        conflicts = _find_conflicting_nodes()
        assert conflicts == [], (
            f"Found {len(conflicts)} node(s) with invalid labels "
            "after design reconciliation:\n"
            + "\n".join(
                f"  {qn}: {lbls} — {reason}"
                for qn, lbls, reason in conflicts
            )
        )

    def test_method_nodes_do_not_have_attribute_label(
        self, persisted_decomposition, design_data
    ):
        """Specifically verify that MethodNodes do NOT also have
        the AttributeNode label — the known regression."""
        from codegraph_design.agents.design_oo import (
            _reconcile_design_with_scaffold,
        )
        from neomodel import db

        design_nodes = design_data["design"]
        _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        # Find all nodes that have both MethodNode and AttributeNode labels
        results, _ = db.cypher_query(
            "MATCH (n:MethodNode:AttributeNode) "
            "RETURN n.qualified_name AS qn, labels(n) AS lbls"
        )
        bad = [(row[0], row[1]) for row in results]
        assert bad == [], (
            f"Found {len(bad)} MethodNode(s) that also have AttributeNode label "
            f"after reconciliation:\n"
            + "\n".join(f"  {qn}: {lbls}" for qn, lbls in bad)
        )

    def test_no_compound_cross_type_conflicts(
        self, persisted_decomposition, design_data
    ):
        """Verify no compound node has labels from two different
        compound types (e.g. ClassNode + InterfaceNode)."""
        from codegraph_design.agents.design_oo import (
            _reconcile_design_with_scaffold,
        )
        from neomodel import db

        design_nodes = design_data["design"]
        _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        compound_types = ["ClassNode", "InterfaceNode", "EnumNode",
                          "UnionNode", "ModuleNode"]

        for i, t1 in enumerate(compound_types):
            for t2 in compound_types[i + 1:]:
                results, _ = db.cypher_query(
                    f"MATCH (n:{t1}:{t2}) "
                    "RETURN n.qualified_name AS qn, labels(n) AS lbls"
                )
                bad = [(row[0], row[1]) for row in results]
                assert bad == [], (
                    f"Found {len(bad)} node(s) with both {t1} and {t2} labels:\n"
                    + "\n".join(f"  {qn}: {lbls}" for qn, lbls in bad)
                )

    def test_no_member_cross_type_conflicts(
        self, persisted_decomposition, design_data
    ):
        """Verify no member node has labels from two different
        member types (e.g. MethodNode + AttributeNode, or
        MethodNode + FunctionNode)."""
        from codegraph_design.agents.design_oo import (
            _reconcile_design_with_scaffold,
        )
        from neomodel import db

        design_nodes = design_data["design"]
        _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        member_types = ["MethodNode", "AttributeNode", "EnumValueNode",
                        "FunctionNode", "DefineNode"]

        for i, t1 in enumerate(member_types):
            for t2 in member_types[i + 1:]:
                results, _ = db.cypher_query(
                    f"MATCH (n:{t1}:{t2}) "
                    "RETURN n.qualified_name AS qn, labels(n) AS lbls"
                )
                bad = [(row[0], row[1]) for row in results]
                assert bad == [], (
                    f"Found {len(bad)} node(s) with both {t1} and {t2} labels:\n"
                    + "\n".join(f"  {qn}: {lbls}" for qn, lbls in bad)
                )


# ════════════════════════════════════════════════════════════════════════════
# Part 2: Design node creation and count sanity
# ════════════════════════════════════════════════════════════════════════════


class TestDesignReconciliationCounts:
    """Verify basic counts after design reconciliation."""

    def test_design_nodes_exist_in_neo4j(
        self, persisted_decomposition, design_data
    ):
        """After reconciliation, key design classes should exist."""
        from codegraph_design.agents.design_oo import (
            _reconcile_design_with_scaffold,
        )
        from neomodel import db

        design_nodes = design_data["design"]
        _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        expected_classes = [
            "diagram_gen::ArchitectureDiagramGenerator",
            "diagram_gen::ModuleQuery",
            "diagram_gen::PackageNode",
            "diagram_gen::ArchitectureOptions",
            "diagram_gen::DiagramRenderer",
            "diagram_gen::CodegraphQuery",
            "diagram_gen::FileSystem",
            "diagram_gen::Dependency",
        ]
        for qn in expected_classes:
            results, _ = db.cypher_query(
                "MATCH (n {qualified_name: $qn}) "
                "RETURN labels(n) AS lbls",
                {"qn": qn},
            )
            assert len(results) == 1, (
                f"Expected 1 node for '{qn}', got {len(results)}"
            )

    def test_scaffold_tag_replaced_with_design(
        self, persisted_decomposition, design_data
    ):
        """After reconciliation, nodes that were matched to design
        should have tags=["design"], not ["scaffold"]."""
        from codegraph_design.agents.design_oo import (
            _reconcile_design_with_scaffold,
        )
        from neomodel import db

        design_nodes = design_data["design"]
        recon = _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        # All nodes that are referenced by design verification edges
        # should be retagged from scaffold → design
        assert recon["scaffold_retaged"] >= 1

        # Check that architecture diagram generator is tagged design
        results, _ = db.cypher_query(
            "MATCH (n {qualified_name: 'diagram_gen::ArchitectureDiagramGenerator'}) "
            "RETURN n.tags AS tags"
        )
        assert len(results) >= 1
        tags = results[0][0] or []
        assert "design" in tags
        assert "scaffold" not in tags

    def test_node_count_grows_after_design(self, persisted_decomposition, design_data):
        """Design reconciliation should add new nodes (unmatched design
        compounds) — total node count should increase."""
        from codegraph_design.agents.design_oo import (
            _reconcile_design_with_scaffold,
        )
        from neomodel import db

        results_before, _ = db.cypher_query("MATCH (n) RETURN count(n) AS c")
        count_before = results_before[0][0]

        design_nodes = design_data["design"]
        _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        results_after, _ = db.cypher_query("MATCH (n) RETURN count(n) AS c")
        count_after = results_after[0][0]

        assert count_after > count_before, (
            f"Expected node count to increase after design reconciliation, "
            f"but {count_before} → {count_after}"
        )
