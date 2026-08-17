"""Tests for component-level requirements decomposition and PlantUML export.

Covers ComponentDecomposition (identification, requirement derivation,
dependency mapping) and PlantUML export (standalone component diagram,
class-diagram enrichment).
"""

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.member import MethodNode, AttributeNode
from codegraph.models.namespace import NamespaceNode
from codegraph.export.component_decomposition import (
    ComponentDecomposition,
    ComponentInfo,
    RequirementInfo,
    export_component_plantuml,
    enrich_plantuml,
)
from codegraph.export.plantuml import export_plantuml


# ── Fixtures ───────────────────────────────────────────────────────────────


def _key_graph(graph: LayerGraph) -> LayerGraph:
    """WP A: assign canonical keys to every node in *graph* under the
    active identity scope (parent-relative children use their parent's
    key).  Mutates the entries in place and returns the graph."""
    from codegraph.identity import get_identity_scope, resolve_identity_for

    scope = get_identity_scope()
    if scope is None:
        return graph

    def walk(entries, parent_key=None):
        for entry in entries:
            node = entry.node
            t = type(node).__name__
            parents = {}
            if parent_key:
                if t == "LLR":
                    parents["parent_hlr_key"] = parent_key
                elif t in (
                    "TestNode", "TestFixtureNode",
                    "AssertionNode", "TestStepNode",
                ):
                    parents["parent_key"] = parent_key
            node.canonical_key = resolve_identity_for(
                node, scope, parents=parents
            ).key()
            walk(
                [
                    e
                    for type_children in entry.children.values()
                    for e in type_children.values()
                ],
                node.canonical_key,
            )

    walk(list(graph.entries.values()))
    return graph


@pytest.fixture
def simple_graph() -> LayerGraph:
    """A two-namespace graph with classes, interfaces, and methods."""
    # ── calc namespace ──
    calc_ns = NamespaceNode(
        name="calc", kind="namespace", source="test", qualified_name="calc",
        tags=["as-built"],
    )
    calc_cls = ClassNode(
        name="CalculatorEngine", kind="class", source="test",
        qualified_name="calc::CalculatorEngine",
        tags=["as-built"], visibility="public",
    )
    calc_iface = InterfaceNode(
        name="ICalculator", kind="interface", source="test",
        qualified_name="calc::ICalculator",
        tags=["as-built"], visibility="public",
    )
    calc_meth = MethodNode(
        name="add", kind="method", source="test",
        qualified_name="calc::CalculatorEngine::add",
        tags=["as-built"], visibility="public",
        type_signature="int", argsstring="(int a, int b)",
    )

    # ── store namespace ──
    store_ns = NamespaceNode(
        name="store", kind="namespace", source="test", qualified_name="store",
        tags=["as-built"],
    )
    store_cls = ClassNode(
        name="GraphRepository", kind="class", source="test",
        qualified_name="store::GraphRepository",
        tags=["as-built"], visibility="public",
    )
    store_meth = MethodNode(
        name="get_by_tag", kind="method", source="test",
        qualified_name="store::GraphRepository::get_by_tag",
        tags=["as-built"], visibility="public",
        type_signature="LayerGraph", argsstring="(str tag)",
    )

    # Build entries
    calc_meth_entry = CompositeEntry(node=calc_meth)
    calc_cls_entry = CompositeEntry(
        node=calc_cls,
        children={
            "MethodNode": {
                "calc::CalculatorEngine::add": calc_meth_entry,
            },
        },
    )
    calc_iface_entry = CompositeEntry(node=calc_iface)
    calc_ns_entry = CompositeEntry(
        node=calc_ns,
        children={
            "ClassNode": {"calc::CalculatorEngine": calc_cls_entry},
            "InterfaceNode": {"calc::ICalculator": calc_iface_entry},
        },
        references=[
            ("DEPENDS_ON", "store::GraphRepository", "ClassNode"),
        ],
    )

    store_meth_entry = CompositeEntry(node=store_meth)
    store_cls_entry = CompositeEntry(
        node=store_cls,
        children={
            "MethodNode": {
                "store::GraphRepository::get_by_tag": store_meth_entry,
            },
        },
    )
    store_ns_entry = CompositeEntry(
        node=store_ns,
        children={
            "ClassNode": {"store::GraphRepository": store_cls_entry},
        },
    )

    return _key_graph(LayerGraph(
        tags=frozenset(["as-built"]),
        entries={
            "calc": calc_ns_entry,
            "store": store_ns_entry,
        },
    ))


@pytest.fixture
def standalone_graph() -> LayerGraph:
    """A graph with standalone classes (no namespace wrapper)."""
    cls = ClassNode(
        name="App", kind="class", source="test", qualified_name="App",
        tags=["as-built"], visibility="public",
    )
    iface = InterfaceNode(
        name="IApp", kind="interface", source="test", qualified_name="IApp",
        tags=["as-built"], visibility="public",
    )

    cls_entry = CompositeEntry(node=cls)
    iface_entry = CompositeEntry(node=iface, references=[
        ("REALIZES", "App", "ClassNode"),
    ])

    return _key_graph(LayerGraph(
        tags=frozenset(["as-built"]),
        entries={"App": cls_entry, "IApp": iface_entry},
    ))


# ── ComponentDecomposition tests ──────────────────────────────────────────


class TestComponentDecomposition:
    """Unit tests for ComponentDecomposition."""

    def test_identifies_namespace_components(self, simple_graph):
        d = ComponentDecomposition(simple_graph)
        comps = d.decompose()

        # calc has 2 entities → qualifies (min=2)
        # store has 1 entity → filtered out
        assert "calc" in comps
        assert comps["calc"].name == "calc"

    def test_filters_tiny_components(self, simple_graph):
        # calc has 2 entities → qualifies at min=2, filtered at min=5
        d = ComponentDecomposition(simple_graph, min_component_size=5)
        comps = d.decompose()
        assert len(comps) == 0

    def test_store_qualifies_at_min_size_one(self, simple_graph):
        """store has 1 entity → qualifies at min_component_size=1."""
        d = ComponentDecomposition(simple_graph, min_component_size=1)
        comps = d.decompose()
        assert "store" in comps
        assert comps["store"].name == "store"

    def test_identifies_standalone_components(self, standalone_graph):
        d = ComponentDecomposition(standalone_graph, min_component_size=1)
        comps = d.decompose()

        assert "App" in comps
        assert comps["App"].name == "App"

    def test_derives_requirements_calc(self, simple_graph):
        d = ComponentDecomposition(simple_graph)
        comps = d.decompose()

        calc = comps["calc"]
        assert len(calc.requirements) >= 1

        # Should have domain-entity requirement (has ClassNode and InterfaceNode)
        descs = [r.description for r in calc.requirements]
        assert any("domain entities" in d for d in descs)

        # Should have public API requirement (has InterfaceNode)
        assert any("public API" in d for d in descs)

    def test_derives_requirements_store(self, simple_graph):
        d = ComponentDecomposition(simple_graph, min_component_size=1)
        comps = d.decompose()

        store = comps["store"]
        descs = [r.description for r in store.requirements]
        # Should have storage requirement (has "Repository" pattern)
        assert any("Persist" in desc for desc in descs)

    def test_maps_dependencies(self, simple_graph):
        d = ComponentDecomposition(simple_graph, min_component_size=1)
        comps = d.decompose()

        calc = comps["calc"]
        # calc references store::GraphRepository → dependency on store component
        assert "store" in calc.dependencies or any(
            "store" in dep for dep in calc.dependencies
        ), f"calc dependencies: {calc.dependencies}"

    def test_component_entries_sorted(self, simple_graph):
        d = ComponentDecomposition(simple_graph, min_component_size=1)
        entries = d.component_entries()

        # More entities/requirements should appear first
        assert len(entries) >= 2
        # calc has 2 compounds + requirements > store's 1 compound
        assert entries[0].name == "calc"

    def test_empty_graph(self):
        graph = LayerGraph(tags=frozenset(["as-built"]), entries={})
        d = ComponentDecomposition(graph)
        comps = d.decompose()
        assert len(comps) == 0


# ── PlantUML export tests ─────────────────────────────────────────────────


class TestExportComponentPlantuml:
    """Tests for export_component_plantuml and enrich_plantuml."""

    def test_generates_valid_plantuml(self, simple_graph):
        puml = export_component_plantuml(
            simple_graph, min_component_size=1,
        )

        assert puml.startswith("@startuml")
        assert puml.endswith("@enduml")

        # Should have package declarations
        assert 'package "calc"' in puml
        assert 'package "store"' in puml

        # Should have requirement notes
        assert "Requirements" in puml
        assert "REQ-" in puml

    def test_respects_detail_level_high(self, simple_graph):
        puml = export_component_plantuml(
            simple_graph, detail_level="high",
        )
        # High level: no class declarations inside packages
        assert 'class "CalculatorEngine"' not in puml

    def test_respects_detail_level_medium(self, simple_graph):
        puml = export_component_plantuml(
            simple_graph, detail_level="medium",
        )
        # Medium: shows key classes
        assert 'class "CalculatorEngine"' in puml

    def test_shows_dependencies(self, simple_graph):
        puml = export_component_plantuml(
            simple_graph, min_component_size=1,
        )
        # Should have dependency arrow (calc → store)
        assert "depends on" in puml

    def test_precomputed_decomposition_accepted(self, simple_graph):
        d = ComponentDecomposition(simple_graph)
        d.decompose()
        puml = export_component_plantuml(simple_graph, decomposition=d)
        assert "@startuml" in puml

    def test_empty_graph_plantuml(self):
        graph = LayerGraph(tags=frozenset(["as-built"]), entries={})
        puml = export_component_plantuml(graph)
        assert "@startuml" in puml
        assert "@enduml" in puml
        # Should not crash

    def test_standalone_components(self, standalone_graph):
        puml = export_component_plantuml(
            standalone_graph, min_component_size=1,
        )
        assert 'package "App"' in puml
        assert 'package "IApp"' in puml


class TestEnrichPlantuml:
    """Tests for enrich_plantuml — wrapping an existing class diagram."""

    def test_enriches_with_component_notes(self, simple_graph):
        class_puml = export_plantuml(simple_graph)
        enriched = enrich_plantuml(class_puml, simple_graph)

        # Original content preserved
        assert "@startuml" in enriched or enriched.startswith("@startuml")

        # New component annotations added
        assert "Component Annotations" in enriched
        assert "Requirements" in enriched

    def test_enrich_preserves_original_classes(self, simple_graph):
        class_puml = export_plantuml(simple_graph)
        enriched = enrich_plantuml(class_puml, simple_graph)

        # Original package names should still appear
        assert "calc" in enriched
        assert "store" in enriched

    def test_enrich_no_components_is_noop(self, simple_graph):
        """Enrich with min_component_size too high → no components → no change."""
        class_puml = export_plantuml(simple_graph)
        enriched = enrich_plantuml(
            class_puml, simple_graph, min_component_size=100,
        )
        # Should still produce valid PlantUML
        assert "@startuml" in enriched or enriched.startswith("@startuml")


# ── RequirementInfo / ComponentInfo data-class tests ──────────────────────


class TestDataClasses:
    """Basic sanity checks for the data classes."""

    def test_requirement_info_defaults(self):
        req = RequirementInfo(id="REQ-01", description="Manage entities")
        assert req.rationale == ""
        assert req.evidence == []

    def test_component_info_defaults(self):
        comp = ComponentInfo(name="test", qualified_name="test")
        assert comp.description == ""
        assert comp.requirements == []
        assert comp.key_classes == []
        assert comp.dependencies == []

    def test_component_info_full(self):
        comp = ComponentInfo(
            name="Graph Engine",
            qualified_name="graph",
            description="Core graph operations",
            requirements=[
                RequirementInfo(
                    id="REQ-01",
                    description="Store graph entities",
                    rationale="Neo4j persistence layer",
                    evidence=["GraphRepository"],
                ),
            ],
            key_classes=["graph::LayerGraph", "graph::CompositeEntry"],
            dependencies=["store"],
        )
        assert len(comp.requirements) == 1
        assert len(comp.key_classes) == 2
        assert "store" in comp.dependencies
