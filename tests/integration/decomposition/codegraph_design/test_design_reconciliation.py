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

from codegraph.backends import get_backend
from codegraph.constants import NODE_KIND_KEYS
from codegraph.models.compound import ClassNode
from codegraph_design.agents.design_oo import (
    _link_design_dependencies,
    _reconcile_design_with_scaffold,
)
from codegraph_requirements.models.requirement import HLR
from codegraph_requirements.persistence import persist_decomposition
from codegraph_requirements.schemas import DecomposedRequirementSchema

DATA_DIR = Path(__file__).resolve().parent / "data"
DECOMPOSE_RESPONSE = DATA_DIR / "decompose_response.json"
DESIGN_RESPONSE = DATA_DIR / "design_response.json"

HLR_UID = (
    "cg:v1:repository:codegraph-suite%2Fcodegraph:requirement-hlr:"
    "qualified_name=Architecture%20Diagram%20Generator"
)


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
    """Query for all nodes and return (qualified_name, labels, reason)
    for every invalid node.

    Uses the GraphRepository API — no raw Cypher.
    """
    graph = get_backend().graph

    # Collect all nodes via known kinds (covers as-built code nodes)
    # plus requirement kinds (HLR, LLR).
    _REQUIREMENT_KINDS = {"hlr", "llr"}
    all_kinds = sorted(NODE_KIND_KEYS | _REQUIREMENT_KINDS)

    seen: set[str] = set()
    all_nodes: list[tuple[str, list[str]]] = []

    for kind in all_kinds:
        for node in graph.find_all_by_kind(kind):
            uid = node.canonical_key or ""
            if not uid or uid in seen:
                continue
            seen.add(uid)
            labels = graph.get_labels(uid)
            qn = getattr(node, "qualified_name", "") or "(none)"
            all_nodes.append((qn, sorted(labels)))

    all_nodes.sort(key=lambda x: x[0])

    conflicts = []
    for qn, lbls in all_nodes:
        if not lbls:
            continue
        is_valid, reason = _node_labels_valid(lbls)
        if not is_valid:
            conflicts.append((qn, lbls, reason))
    return conflicts


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def ensure_hlr_exists():
    """Create the target HLR in Neo4j so persist_decomposition
    can find it."""
    existing = get_backend().graph.find_by_key(HLR_UID)
    if existing:
        get_backend().graph.delete_by_key(HLR_UID)

    hlr = HLR(
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
def persisted_decomposition(ensure_hlr_exists):
    """Persist the decompose response to Neo4j (creates scaffold nodes)."""
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
        design_nodes = design_data["design"]
        _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        # Find all nodes that have both MethodNode and AttributeNode labels
        graph = get_backend().graph
        results = graph.find_nodes_with_labels(["MethodNode", "AttributeNode"])
        bad = [(r["qualified_name"], r["labels"]) for r in results]
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
        design_nodes = design_data["design"]
        _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        graph = get_backend().graph
        compound_types = ["ClassNode", "InterfaceNode", "EnumNode",
                          "UnionNode", "ModuleNode"]

        for i, t1 in enumerate(compound_types):
            for t2 in compound_types[i + 1:]:
                results = graph.find_nodes_with_labels([t1, t2])
                bad = [(r["qualified_name"], r["labels"]) for r in results]
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
        design_nodes = design_data["design"]
        _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        graph = get_backend().graph
        member_types = ["MethodNode", "AttributeNode", "EnumValueNode",
                        "FunctionNode", "DefineNode"]

        for i, t1 in enumerate(member_types):
            for t2 in member_types[i + 1:]:
                results = graph.find_nodes_with_labels([t1, t2])
                bad = [(r["qualified_name"], r["labels"]) for r in results]
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
        graph = get_backend().graph
        for qn in expected_classes:
            node = graph.find_by_qualified_name(qn)
            assert node is not None, (
                f"Expected node for '{qn}', but not found"
            )

    def test_scaffold_tag_replaced_with_design(
        self, persisted_decomposition, design_data
    ):
        """After reconciliation, nodes that were matched to design
        should have tags=["design"], not ["scaffold"]."""
        design_nodes = design_data["design"]
        recon = _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        # All nodes that are referenced by design verification edges
        # should be retagged from scaffold → design
        assert recon["scaffold_retaged"] >= 1

        graph = get_backend().graph
        node = graph.find_by_qualified_name(
            "diagram_gen::ArchitectureDiagramGenerator"
        )
        assert node is not None
        tags = list(node.tags) if node.tags else []
        assert "design" in tags
        assert "scaffold" not in tags

    def test_node_count_grows_after_design(self, persisted_decomposition, design_data):
        """Design reconciliation should add new nodes (unmatched design
        compounds) — total node count should increase."""
        graph = get_backend().graph
        count_before = graph.count_all_nodes()

        design_nodes = design_data["design"]
        _reconcile_design_with_scaffold(HLR_UID, design_nodes)

        count_after = graph.count_all_nodes()

        assert count_after > count_before, (
            f"Expected node count to increase after design reconciliation, "
            f"but {count_before} → {count_after}"
        )


# ════════════════════════════════════════════════════════════════════════════
# Part 3: DEPENDS_ON edge creation (explicit edges arrays + type-signature scan)
# ════════════════════════════════════════════════════════════════════════════


class TestDesignDependencyEdges:
    """Verify that _link_design_dependencies creates DEPENDS_ON edges
    from both explicit edges arrays and type-signature scanning."""

    def test_explicit_edges_create_depends_on_relations(
        self, persisted_decomposition,
    ):
        """Explicit edges arrays in design nodes must produce DEPENDS_ON
        edges in Neo4j — the primary source of dependency information.

        This tests the fix where _link_design_dependencies was only
        scanning type_signature/argsstring text fields and ignoring
        the edges array that the agent explicitly declares."""

        # Create source and target nodes.  The as-built target simulates
        # an existing entity (like cpp_sqlite::Database) that the design
        # depends on but doesn't create.
        for qn, source, tags in [
            ("test::MigrationManager", "test", ["design"]),
            ("test::MigrationResult", "test", ["design"]),
            ("test::Database", "test", ["as-built"]),
        ]:
            ClassNode.save_new(
                qualified_name=qn,
                name=qn.split("::")[-1],
                source=source,
                tags=tags,
            )

        # Flat design — the agent explicitly declares edges to both
        # another design compound and an existing as-built entity.
        flat_design = [{
            "type": "ClassNode",
            "qualified_name": "test::MigrationManager",
            "name": "MigrationManager",
            "kind": "class",
            "source": "test",
            "edges": [
                {
                    "relation_type": "DEPENDS_ON",
                    "target_uid": "test::MigrationResult",
                    "target_type": "ClassNode",
                },
                {
                    "relation_type": "DEPENDS_ON",
                    "target_uid": "test::Database",
                    "target_type": "ClassNode",
                },
            ],
        }]

        edges_created = _link_design_dependencies(flat_design)

        assert edges_created == 2, (
            f"Expected 2 DEPENDS_ON edges from explicit arrays, "
            f"got {edges_created}"
        )

        # Verify edges exist.
        graph = get_backend().graph
        source = graph.find_by_qualified_name("test::MigrationManager")
        assert source is not None
        targets = graph.outgoing_by_relation(source, "DEPENDS_ON")
        target_qns = sorted(
            getattr(t, "qualified_name", "") for t in targets
        )
        assert target_qns == ["test::Database", "test::MigrationResult"], (
            f"Unexpected DEPENDS_ON targets: {target_qns}"
        )

    def test_type_signature_scanning_creates_depends_on_relations(
        self, persisted_decomposition,
    ):
        """Type-signature scanning (the legacy path) also produces
        DEPENDS_ON edges — ensures the scanning path still works."""

        # Create nodes.
        for qn, source, tags in [
            ("test::MigrationManager", "test", ["design"]),
            ("test::Database", "test", ["as-built"]),
        ]:
            ClassNode.save_new(
                qualified_name=qn,
                name=qn.split("::")[-1],
                source=source,
                tags=tags,
            )

        # Flat design — no explicit edges array, but member type_signature
        # references 'test::Database'.
        flat_design = [{
            "type": "ClassNode",
            "qualified_name": "test::MigrationManager",
            "name": "MigrationManager",
            "kind": "class",
            "source": "test",
            "composes": [{
                "type": "AttributeNode",
                "qualified_name": "test::MigrationManager::db",
                "name": "db",
                "kind": "attribute",
                "type_signature": "cpp_sqlite::Database&",
                "source": "test",
            }, {
                "type": "MethodNode",
                "qualified_name": "test::MigrationManager::apply",
                "name": "apply",
                "kind": "method",
                "argsstring": "(test::Database &db)",
                "source": "test",
            }],
        }]

        edges_created = _link_design_dependencies(flat_design)

        # "cpp_sqlite::Database" won't resolve (not in Neo4j),
        # but "test::Database" will.
        assert edges_created == 1, (
            f"Expected 1 DEPENDS_ON edge from type-signature scanning, "
            f"got {edges_created}"
        )

        graph = get_backend().graph
        source = graph.find_by_qualified_name("test::MigrationManager")
        assert source is not None
        targets = graph.outgoing_by_relation(source, "DEPENDS_ON")
        target_qns = [getattr(t, "qualified_name", "") for t in targets]
        assert "test::Database" in target_qns, (
            "DEPENDS_ON edge from type-signature scan was not created"
        )
