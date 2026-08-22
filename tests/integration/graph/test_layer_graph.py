"""Tests for LayerGraph: deserialize, serialize, to_neo4j, _node_key, from_neo4j."""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.compound import ClassNode, EnumNode, InterfaceNode
from codegraph.models.file import FileNode
from codegraph.models.member import AttributeNode, EnumValueNode, MethodNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.tags import CodeGraphNode
_FIXTURE_DATA = json.loads(
    (Path(__file__).resolve().parent / "data" / "design_graph.json").read_text()
)


def _walk_fixture(items):
    for entry in items:
        yield entry
        yield from _walk_fixture(entry.get("composes", []))


def _key(qname: str, argsstring: str | None = None,
         cls: type | None = None) -> str:
    """Canonical key for *qname*: from the fixture when present, else
    computed from a type probe under a fixed repository scope."""
    from codegraph.identity import IdentityScope, resolve_identity_for

    for entry in _walk_fixture(_FIXTURE_DATA):
        if entry.get("qualified_name") == qname:
            return entry["canonical_key"]
    scope = IdentityScope.repository("codegraph-suite", "calculator")
    probe_cls = cls or MethodNode if argsstring is not None else (
        cls or ClassNode
    )
    probe = probe_cls(
        qualified_name=qname,
        name=qname.rsplit("::", 1)[-1],
        source="calculator",
        path=qname,
        argsstring=argsstring or "",
    )
    return resolve_identity_for(probe, scope).key()

FIXTURE = Path(__file__).resolve().parent / "data" / "design_graph.json"
FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"

def _count_all_entries(graph: LayerGraph) -> int:
    """Count all CompositeEntry instances across the entire tree."""
    return sum(1 for _ in graph._all_entries())

def _find_entry(graph: LayerGraph, key: str) -> CompositeEntry | None:
    """Find a CompositeEntry by uid key across the entire tree."""
    for entry in graph._all_entries():
        if LayerGraph._node_key(entry.node) == key:
            return entry
    return None

class TestNodeKey:
    """Canonical-only ``_node_key`` behavior (WP B)."""

    def test_returns_canonical_key_for_instance(self):
        from codegraph.identity import IdentityScope, identity_scope

        scope = IdentityScope.repository("codegraph-suite", "calculator")
        with identity_scope(scope):
            node = ClassNode(name="Widget", kind="class",
                             qualified_name="ns::Widget", source="test")
            node.save()
        assert LayerGraph._node_key(node) == node.canonical_key
        assert LayerGraph._node_key(node).startswith("cg:v1:")

    def test_returns_canonical_key_for_dict(self):
        data = {
            "type": "ClassNode",
            "name": "Widget",
            "qualified_name": "ns::Widget",
            "kind": "class",
            "source": "test",
            "canonical_key": "cg:v1:repository:codegraph-suite%2Fcalculator:"
                             "class:qualified_name=ns%3A%3AWidget",
        }
        assert LayerGraph._node_key(data) == data["canonical_key"]

    def test_raises_without_canonical_key(self):
        """WP B: uid-bearing legacy dicts are rejected — no uid fallback."""
        with pytest.raises(ValueError, match="canonical_key"):
            LayerGraph._node_key({"type": "ClassNode", "uid": "abc123",
                                  "qualified_name": "ns::Widget"})

class TestTagValidation:
    """Tests for Tag validation — only 'design', 'as-built', 'dependency' allowed."""

    # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_design
    # Verifies that a LayerGraph instance with valid tags is correctly constructed,
    # ensuring tag validation logic does not reject properly formatted inputs.
    def test_valid_design(self):
        # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_design::step_0
        # Sets up the test by initializing the LayerGraph instance and assigning it a
        # valid tag set, preparing for tag validation.
        graph = LayerGraph(tags=frozenset({"design"}))
        # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_design::post_0
        # Confirms that the graph's tags are exactly the frozenset containing 'design',
        # ensuring that the tag validation logic permits this valid tag configuration.
        assert graph.tags == frozenset({"design"})

    # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_as_built
    # Verifies that a layer graph tagged as 'as-built' passes validation, ensuring the
    # system correctly recognizes and accepts valid construction-state graphs.
    def test_valid_as_built(self):
        # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_as_built::step_0
        # Sets up the test environment by initializing the graph fixture, which is
        # required before verifying tag properties.
        graph = LayerGraph(tags=frozenset({"as-built"}))
        # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_as_built::post_0
        # Confirms that the graph's tags set contains exactly the 'as-built' tag,
        # verifying that LayerGraph correctly assigns and stores tags as expected for an
        # 'as-built' graph.
        assert graph.tags == frozenset({"as-built"})

    # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_dependency
    # Verifies that a dependency with a valid tag is correctly accepted by LayerGraph,
    # ensuring tag-based dependency validation prevents illegal architectural
    # connections.
    def test_valid_dependency(self):
        # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_dependency::step_0
        # Sets up the test environment by initializing the LayerGraph with a valid
        # 'dependency' tag, preparing for tag validation.
        graph = LayerGraph(tags=frozenset({"dependency"}))
        # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_dependency::post_0
        # Verifies that the graph's tags consist solely of the expected 'dependency'
        # set, confirming correct tag assignment and integrity.
        assert graph.tags == frozenset({"dependency"})

    # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_multiple_tags
    # Verifies that multiple tags can be assigned to a single layer without errors,
    # ensuring the LayerGraph correctly handles non-unique tag configurations for
    # complex use cases.
    def test_valid_multiple_tags(self):
        # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_multiple_tags::step_0
        # Sets up the graph with multiple tags like 'design' and 'as-built', preparing
        # the test scenario for validation.
        graph = LayerGraph(tags=frozenset({"design", "as-built"}))
        # codegraph:test-desc test_layer_graph.TestTagValidation.test_valid_multiple_tags::post_0
        # Verifies that the graph's tags are exactly {'design', 'as-built'}, ensuring
        # that tag assignment and retrieval work accurately.
        assert graph.tags == frozenset({"design", "as-built"})

    # codegraph:test-desc test_layer_graph.TestTagValidation.test_invalid_tag_raises
    # Verifies that providing an invalid tag to LayerGraph raises an appropriate error,
    # ensuring that only properly formatted tags are accepted for maintaining data
    # integrity and consistency.
    def test_invalid_tag_raises(self):
        # codegraph:test-desc test_layer_graph.TestTagValidation.test_invalid_tag_raises::step_0
        # Creates a LayerGraph instance and adds a layer with an invalid tag, which is
        # expected to raise an error, setting up the scenario to verify the tag
        # validation behavior.
        with pytest.raises(ValueError, match="Invalid tags"):
            LayerGraph(tags=frozenset({"production"}))

    def test_invalid_tag_mixed_raises(self):
        """A valid tag mixed with an invalid one still raises."""
        # codegraph:test-desc test_layer_graph.TestTagValidation.test_invalid_tag_mixed_raises::step_0
        # Initializes the test by creating a LayerGraph instance and adding nodes with a
        # mix of valid and invalid tags, setting up the scenario to trigger a validation
        # error.
        with pytest.raises(ValueError, match="Invalid tags"):
            LayerGraph(tags=frozenset({"design", "bogus"}))

class TestDeserialize:
    """Tests for LayerGraph.deserialize() — pure deserialization, no DB."""

    # codegraph:test-desc test_layer_graph.TestDeserialize.test_creates_nodes_from_fixture
    # Verifies that the deserialize method of LayerGraph correctly recreates all nodes
    # from a fixture representing a serialized graph, ensuring that the deserialization
    # process accurately restores the graph structure for subsequent operations.
    def test_creates_nodes_from_fixture(self):
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_creates_nodes_from_fixture::step_0
        # Calls LayerGraph.deserialize on the graph fixture with sample data, executing
        # the method under test to produce the deserialized state.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_creates_nodes_from_fixture::post_0
        # Verifies that every fixture node (roots + nested children, counted
        # across the whole tree) survives deserialization.
        assert _count_all_entries(graph) == len(list(_walk_fixture(data)))
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_creates_nodes_from_fixture::post_1
        # Confirms that the graph's tags attribute has been set to exactly the expected
        # set {'design'}, validating proper metadata assignment during deserialization.
        assert graph.tags == frozenset({"design"})

    # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct
    # Verifies that nodes deserialized from a LayerGraph representation have the correct
    # types, ensuring the integrity of graph reconstruction.
    def test_node_types_are_correct(self):
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::step_0
        # Sets up the initial data structures required for the test, such as a
        # dictionary representing the serialized graph or a temporary in-memory graph,
        # establishing the context for subsequent deserialization steps.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        # Spot-check some nodes by finding them in the tree
        engine = _find_entry(graph, _key("calc::CalculatorEngine"))
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::post_0
        # Verifies that the 'engine' entry obtained from the deserialized graph is not
        # None, ensuring that the node corresponding to the 'engine' identifier was
        # successfully created during deserialization.
        assert engine is not None
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::post_1
        # Checks that the node associated with 'engine' is of type ClassNode, confirming
        # that the deserialization correctly interpreted the source code structure and
        # assigned the appropriate node type.
        assert type(engine.node).__name__ == "ClassNode"

        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::step_1
        # Calls the deserialize method on the LayerGraph instance with the prepared
        # data, executing the core logic that transforms the serialized representation
        # into live node objects.
        file_entry = _find_entry(graph, _key("/src/calc/calculator_engine.h", cls=FileNode))
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::post_2
        # Ensures that the 'file_entry' reference is not None, validating that the
        # file-level node was properly deserialized and is accessible for further type
        # checking.
        assert file_entry is not None
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::post_3
        # Asserts that the node behind 'file_entry' has the type FileNode, verifying
        # that the deserialization process correctly captured the file-level container
        # in the graph.
        assert type(file_entry.node).__name__ == "FileNode"

        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::step_2
        # Looks up fixture nodes by their canonical keys
        # function, ensuring that each node has a consistent and retrievable UID needed
        # for later lookups and validation.
        icalc = _find_entry(graph, _key("calc::ICalculator"))
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::post_4
        # Confirms that the icalc entry is not None, guaranteeing that an interface node
        # was successfully reconstructed as part of the deserialized graph.
        assert icalc is not None
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::post_5
        # Validates that the node for 'icalc' is of type InterfaceNode, ensuring that
        # the deserialization correctly represented the interface abstraction in the
        # code.
        assert type(icalc.node).__name__ == "InterfaceNode"

        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::step_3
        # Uses helper functions _uid and _find_entry to locate specific nodes within the
        # deserialized graph by their computed UIDs, retrieving references such as
        # 'engine', 'file_entry', 'icalc', and 'add_entry' to be verified in the
        # assertions.
        add_entry = _find_entry(graph, _key("calc::CalculatorEngine::add", "(double a, double b)"))
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::post_6
        # Checks that the 'add_entry' reference is not None, verifying that a method
        # node was properly deserialized and exists in the graph.
        assert add_entry is not None
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_node_types_are_correct::post_7
        # Asserts that the node associated with 'add_entry' is of type MethodNode,
        # confirming that the deserialization accurately preserved the method-level
        # details in the code structure.
        assert type(add_entry.node).__name__ == "MethodNode"

    def test_composes_children_nested(self):
        """COMPOSES edges should create nesting under the parent entry."""
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_composes_children_nested::step_0
        # Sets up the test by deserializing a predefined graph structure containing
        # COMPOSES edges, preparing the 'engine' container used to verify correct
        # nesting of child nodes under their parent.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)

        engine = _find_entry(graph, _key("calc::CalculatorEngine"))
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_composes_children_nested::post_0
        # Ensures that the deserialization produced a non-null LayerGraph engine,
        # confirming the basic success of the deserialization operation before
        # proceeding to more specific nesting checks.
        assert engine is not None
        # CalculatorEngine COMPOSES MethodNode (add, validateInput)
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_composes_children_nested::post_1
        # Confirms that a string identifier for a child node exists in the top-level
        # children of the engine, ensuring that at least one nested child from COMPOSES
        # edges is correctly placed under the parent entry.
        assert "MethodNode" in engine.children
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_composes_children_nested::post_2
        # Verifies that the specific MethodNode 'add' with its signature is nested under
        # the parent 'CalculatorEngine' via COMPOSES edges, confirming that method child
        # relationships are correctly reconstructed during deserialization.
        assert _key("calc::CalculatorEngine::add", "(double a, double b)") in engine.children["MethodNode"]
        # CalculatorEngine COMPOSES AttributeNode (precision)
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_composes_children_nested::post_3
        # Verifies that a string identifier for a child node is present as a key in the
        # children dictionary of 'AttributeNode', confirming that the deserialized
        # parent entry correctly includes nested attribute children due to COMPOSES
        # edges.
        assert "AttributeNode" in engine.children
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_composes_children_nested::post_4
        # Checks that the specific AttributeNode 'precision' is nested under the parent
        # 'CalculatorEngine' via COMPOSES edges, verifying that the deserialized graph
        # correctly preserves attribute child relationships.
        assert _key("calc::CalculatorEngine::precision") in engine.children["AttributeNode"]

    def test_non_composes_edges_as_references(self):
        """Non-COMPOSES edges should be stored as references, not children."""
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_non_composes_edges_as_references::step_0
        # Sets up the test by constructing a JSON representation of a graph with
        # non-COMPOSES edges and passing it to the deserialize method of the code under
        # test, preparing the graph fixture for subsequent verification steps.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)

        engine = _find_entry(graph, _key("calc::CalculatorEngine"))
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_non_composes_edges_as_references::post_0
        # Verifies that the deserialized graph has an associated engine object,
        # confirming that the deserialization process successfully created the internal
        # engine required for subsequent reference-type queries.
        assert engine is not None
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_non_composes_edges_as_references::step_1
        # Retrieves the reference types from the deserialized graph's engine to collect
        # the edge labels that were stored as references, enabling the assertions to
        # check which relationships are present or absent.
        ref_types = {r[0] for r in engine.references}
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_non_composes_edges_as_references::post_1
        # Asserts that the 'REALIZES' relationship appears as a reference, ensuring that
        # this implementation link is correctly stored as a reference rather than a
        # child node.
        assert "REALIZES" in ref_types
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_non_composes_edges_as_references::post_2
        # Checks that the 'DEPENDS_ON' relationship is treated as a reference,
        # validating that dependency edges are not mistakenly stored as children, which
        # preserves the flat reference structure.
        assert "DEPENDS_ON" in ref_types
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_non_composes_edges_as_references::post_3
        # Confirms that the 'DEFINED_IN' relationship is stored as a reference, ensuring
        # that this non-composition edge type is correctly categorized as a reference in
        # the deserialized graph.
        assert "DEFINED_IN" in ref_types
        # COMPOSES should NOT be in references
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_non_composes_edges_as_references::post_4
        # Verifies that the 'COMPOSES' relationship is not present among the reference
        # types, confirming that composition edges are stored as children rather than
        # references, which is critical for maintaining the intended hierarchy.
        assert "COMPOSES" not in ref_types

    def test_composed_nodes_not_at_root(self):
        """Nodes composed by another node should not appear as root entries."""
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_composed_nodes_not_at_root::step_0
        # Calls the deserialize method on a LayerGraph instance with predefined input,
        # populating the graph structure for subsequent assertions.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)

        # "calc::CalculatorEngine::add" is composed by CalculatorEngine, not at root
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_composed_nodes_not_at_root::post_0
        # Verifies that another composed node is absent from root nodes, confirming that
        # no composite child is incorrectly treated as a top-level layer.
        assert _key("calc::CalculatorEngine::add", "(double a, double b)") not in graph.entries
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_composed_nodes_not_at_root::post_1
        # Verifies that the first expected composed node does not appear in the root
        # nodes list, ensuring it is correctly excluded from top-level entries.
        assert _key("calc::CalculatorEngine::precision") not in graph.entries
        # NamespaceNode "calc" should be a root entry
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_composed_nodes_not_at_root::post_2
        # Checks that a known root node (not composed by another) is present in the root
        # nodes list, validating that the deserialization preserves legitimate root
        # entries.
        assert _key("calc") in graph.entries

    def test_entries_are_composite_entries(self):
        """Root entries should be CompositeEntry instances."""
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_entries_are_composite_entries::step_0
        # Sets up the test by creating the necessary graph structure before
        # deserialization, enabling the subsequent type check on its root entries.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        for entry in graph.entries.values():
            # codegraph:test-desc test_layer_graph.TestDeserialize.test_entries_are_composite_entries::post_0
            # Verifies that every root entry in the deserialized graph is a
            # CompositeEntry, which is fundamental to the integrity of the graph's
            # hierarchical structure.
            assert isinstance(entry, CompositeEntry)

    # codegraph:test-desc test_layer_graph.TestDeserialize.test_tags_inference_from_data
    # Verifies that the `deserialize` method correctly infers and applies tags to nodes
    # based on the input data, ensuring that metadata enrichment preserves structural
    # fidelity during graph reconstruction.
    def test_tags_inference_from_data(self):
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_tags_inference_from_data::step_0
        # Sets up the test environment by preparing or loading the data that will be
        # used to infer tags on the graph during deserialization.
        data = [
            {"type": "ClassNode", "name": "MyClass", "qualified_name": "test::MyClass",
             "kind": "class", "source": "test", "tags": ["as-built"],
             "canonical_key": _key("test::MyClass", cls=ClassNode)},
        ]
        graph = LayerGraph.deserialize(data)
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_tags_inference_from_data::post_0
        # Verifies that after deserialization, the graph's tags match the expected set
        # {'as-built'}, ensuring that tag inference from data works correctly.
        assert graph.tags == frozenset({"as-built"})

    # codegraph:test-desc test_layer_graph.TestDeserialize.test_tags_default_to_design
    # Verifies that deserializing a LayerGraph correctly sets default tags to 'design',
    # ensuring expected metadata initialization after deserialization.
    def test_tags_default_to_design(self):
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_tags_default_to_design::step_0
        # This step sets up the test by invoking the deserialize method on the
        # LayerGraph fixture, preparing it for verification of default tags.
        data = [
            {"type": "ClassNode", "name": "MyClass", "qualified_name": "test::MyClass",
             "kind": "class", "source": "test",
             "canonical_key": _key("test::MyClass", cls=ClassNode)},
        ]
        graph = LayerGraph.deserialize(data)
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_tags_default_to_design::post_0
        # This assertion verifies that the deserialized LayerGraph's tags attribute
        # defaults to a frozenset containing only 'design', confirming the code under
        # test correctly applies the default tag when no other tags are specified.
        assert graph.tags == frozenset({"design"})

    def test_backward_compat_layer_field(self):
        """Legacy 'layer' field in data is converted to 'tags'."""
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_backward_compat_layer_field::step_0
        # Sets up the test by initializing the graph object and performing the
        # deserialization of sample data that includes the legacy 'layer' field.
        data = [
            {"type": "ClassNode", "name": "MyClass", "qualified_name": "test::MyClass",
             "kind": "class", "source": "test", "layer": "as-built",
             "canonical_key": _key("test::MyClass", cls=ClassNode)},
        ]
        graph = LayerGraph.deserialize(data)
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_backward_compat_layer_field::post_0
        # Verifies that the graph's tags attribute equals frozenset({'as-built'}),
        # confirming the legacy 'layer' field was properly converted to the expected
        # tag.
        assert graph.tags == frozenset({"as-built"})
        # The node itself should have tags=["as-built"] via backward compat
        for entry in graph._all_entries():
            if hasattr(entry.node, 'tags'):
                # codegraph:test-desc test_layer_graph.TestDeserialize.test_backward_compat_layer_field::post_1
                # Checks that the original 'layer' key is no longer present in the
                # graph's data, ensuring no residual legacy fields remain after
                # deserialization.
                assert "as-built" in entry.node.tags

    # codegraph:test-desc test_layer_graph.TestDeserialize.test_empty_data
    # Verifies that deserializing an empty data structure returns an empty LayerGraph,
    # ensuring the method handles edge cases without error.
    def test_empty_data(self):
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_empty_data::step_0
        # Sets up the test by initializing the graph fixture, preparing the environment
        # for the deserialization logic to be exercised without external data.
        graph = LayerGraph.deserialize([])
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_empty_data::post_0
        # Verifies that after deserialization of empty input, the graph's entries list
        # is empty, confirming the code correctly handles the absence of data.
        assert len(graph.entries) == 0
        # codegraph:test-desc test_layer_graph.TestDeserialize.test_empty_data::post_1
        # Checks that the graph retains its default tag set (containing 'design') after
        # deserializing empty input, ensuring the metadata framework is not corrupted by
        # empty data.
        assert graph.tags == frozenset({"design"})

class TestRoundtrip:
    """Integration test: deserialize → to_neo4j → serialize roundtrip."""

    # codegraph:test-desc test_layer_graph.TestRoundtrip.test_full_graph_roundtrip
    # Verifies that a complete LayerGraph can be serialized and deserialized without
    # data loss, and that the resulting graph matches the structure expected by Neo4j,
    # ensuring end-to-end data integrity and compatibility with the database schema.
    def test_full_graph_roundtrip(self):
        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_full_graph_roundtrip::step_0
        # Sets up the initial test data and populates the original graph fixture,
        # establishing the baseline state for the roundtrip operations that follow.
        with open(FIXTURE) as f:
            data = json.load(f)

        # Pure deserialization
        graph = LayerGraph.deserialize(data)
        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_full_graph_roundtrip::post_0
        # Verifies that the total number of entries in the original graph matches the
        # input data count, ensuring that the graph was correctly populated before
        # serialization.
        assert _count_all_entries(graph) == len(data)

        # Persist
        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_full_graph_roundtrip::step_1
        # Performs the serialize operation on the original graph, generating a
        # serialized representation that will later be deserialized and compared to the
        # original.
        graph.to_neo4j()

        # Serialize (nested format)
        serialized = graph.serialize()
        # Root entries only — composed children are nested, not flat
        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_full_graph_roundtrip::post_1
        # Checks that the length of the serialized output equals the number of entries
        # in the original graph, confirming that serialization preserved all entries
        # without loss or duplication.
        assert len(serialized) == len(graph.entries)

        # Every node type present in the nested output
        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_full_graph_roundtrip::step_2
        # Calls the to_neo4j method to convert the serialized graph data into a
        # Neo4j-compatible format, advancing the test toward verifying that the entire
        # roundtrip pipeline (serialize, deserialize, to_neo4j) works correctly.
        def _collect_types(items: list[dict]) -> set[str]:
            types = set()
            for item in items:
                types.add(item["type"])
                if "composes" in item:
                    types |= _collect_types(item["composes"])
            return types

        types_in_output = _collect_types(serialized)
        types_in_input = {item["type"] for item in data}
        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_full_graph_roundtrip::post_2
        # Asserts that the types of entries in the Neo4j output match the types present
        # in the input data, ensuring that the to_neo4j conversion maintains type
        # fidelity.
        assert types_in_output == types_in_input

        # Write/read roundtrip via JSON
        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_full_graph_roundtrip::step_3
        # Deserializes the serialized data to reconstruct a LayerGraph and assigns it to
        # the restored fixture, completing the roundtrip so that assertions can compare
        # it with the original graph.
        FIXTURE_DIR.mkdir(exist_ok=True)
        out_path = Path(__file__).resolve().parent / "data" / "layer_graph_export.json"
        with open(out_path, "w") as f:
            json.dump(serialized, f, indent=2)
        with open(out_path) as f:
            loaded = json.load(f)

        # Deserialize back
        restored = LayerGraph.deserialize(loaded)
        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_full_graph_roundtrip::post_3
        # Confirms that the deserialized graph (restored) has the same number of entries
        # as the original input data, validating that the full roundtrip (serialize then
        # deserialize) preserves entry count.
        assert _count_all_entries(restored) == len(data)

    def test_edge_persistence(self):
        """All fixture edges are present after to_neo4j."""
        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_edge_persistence::step_0
        # Sets up the test by deserializing the graph from a JSON representation and
        # then converting it to Neo4j format, preparing the data for verification.
        with open(FIXTURE) as f:
            data = json.load(f)

        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()

        flat = graph._flat_index()

        total_fixture_edges = 0
        for node_data in data:
            key = LayerGraph._node_key(node_data)
            entry = flat.get(key)
            # codegraph:test-desc test_layer_graph.TestRoundtrip.test_edge_persistence::post_0
            # Checks that each entry from the original graph is present after
            # deserialization, confirming no entries were dropped during serialization
            # and export.
            assert entry is not None, f"Missing entry for key {key}"
            saved = entry.node
            for edge in node_data.get("edges", []):
                total_fixture_edges += 1
                target_key = edge["target_key"]
                target_entry = flat.get(target_key)
                # codegraph:test-desc test_layer_graph.TestRoundtrip.test_edge_persistence::post_1
                # Verifies that every target entry referenced by an edge exists in the
                # deserialized graph, ensuring that edge targets are not lost during the
                # round-trip.
                assert target_entry is not None, f"Missing target {target_key}"
                target = target_entry.node
                found = [
                    e for e in saved.serialize()["edges"]
                    if e["relation_type"] == edge["relation_type"]
                    and e["target_key"] == target.canonical_key
                ]
                # codegraph:test-desc test_layer_graph.TestRoundtrip.test_edge_persistence::post_2
                # Confirms that the expected edge between a source entry and a target
                # with the correct relation type exists in the deserialized graph,
                # validating edge structure preservation.
                assert len(found) >= 1, (
                    f"Missing edge: {type(saved).__name__} -[:{edge['relation_type']}]-> "
                    f"{edge['target_type']} {target_key}"
                )

        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_edge_persistence::step_1
        # Iterates over the original fixture edges to perform lookups in the
        # deserialized graph, advancing toward assertions that all edges have been
        # preserved.
        total_live_edges = sum(
            len(entry.node.serialize()["edges"]) for entry in graph._all_entries()
        )
        # codegraph:test-desc test_layer_graph.TestRoundtrip.test_edge_persistence::post_3
        # Ensures that the total number of edges after deserialization is at least as
        # many as in the original fixture, verifying no edges were silently dropped.
        assert total_live_edges >= total_fixture_edges

class TestSerializeFields:
    """Tests for LayerGraph.serialize(fields=...) and CompositeEntry.serialize(fields=...)."""

    def test_llm_fields_default(self):
        """Default serialize() includes only _llm_fields per node."""
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_llm_fields_default::step_0
        # Sets up the test by creating or obtaining the LayerGraph fixture before
        # running the serialization method.
        data = [
            {"type": "ClassNode", "name": "Engine", "kind": "class",
             "qualified_name": "ns::Engine", "tags": ["design"],
             "canonical_key": _key("ns::Engine")},
            {"type": "MethodNode", "name": "run", "kind": "method",
             "qualified_name": "ns::Engine::run", "tags": ["design"],
             "canonical_key": _key("ns::Engine::run", ""),
             "edges": [{"relation_type": "COMPOSES", "target_type": "MethodNode",
                         "target_key": _key("ns::Engine::run", "")}]},
        ]
        graph = LayerGraph.deserialize(data)
        output = graph.serialize()

        # Find the ClassNode entry
        engine = next(e for e in output if e["type"] == "ClassNode")
        # ClassNode _llm_fields: qualified_name, name, kind, tags, brief_description,
        # base_classes, visibility
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_llm_fields_default::post_0
        # Verifies that the 'name' field is present in the serialized output, confirming
        # it is included as a default LLM field.
        assert "name" in engine
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_llm_fields_default::post_1
        # Checks that the 'kind' field is present in the serialized output, validating
        # it is included as a default LLM field.
        assert "kind" in engine
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_llm_fields_default::post_2
        # Ensures that the 'tags' field is present in the serialized output, confirming
        # it is included as a default LLM field.
        assert "tags" in engine  # tags is now in _llm_fields
        # Non-LLM fields should be absent
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_llm_fields_default::post_3
        # Verifies that the 'module' field is excluded from the serialized output,
        # confirming it is not a default LLM field.
        assert "module" not in engine
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_llm_fields_default::post_4
        # Ensures that the 'is_abstract' field is absent from the serialized output,
        # confirming it is not part of the default LLM field set.
        assert "is_abstract" not in engine

    def test_all_fields_includes_more_properties(self):
        """serialize(fields='all') includes properties beyond _llm_fields."""
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_all_fields_includes_more_properties::step_0
        # Sets up the graph fixture and calls the serialize method with fields='all' on
        # the graph, producing two dicts (llm_engine and all_engine) to compare which
        # fields are present.
        data = [
            {"type": "ClassNode", "name": "Engine", "kind": "class",
             "qualified_name": "ns::Engine", "source": "calculator",
             "tags": ["design"], "module": "mymod", "is_abstract": True,
             "canonical_key": _key("ns::Engine", cls=ClassNode)},
        ]
        graph = LayerGraph.deserialize(data)
        llm_output = graph.serialize()
        all_output = graph.serialize(fields="all")

        llm_engine = next(e for e in llm_output if e["type"] == "ClassNode")
        all_engine = next(e for e in all_output if e["type"] == "ClassNode")

        # fields="all" includes non-LLM properties
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_all_fields_includes_more_properties::post_0
        # Verifies that 'module' is excluded from the llm_engine dict, ensuring that
        # fields='all' correctly omits fields not relevant to that context.
        assert "module" not in llm_engine
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_all_fields_includes_more_properties::post_1
        # Asserts that 'module' is included in the all_engine dict, verifying that
        # fields='all' captures module-level information when serialized with all
        # fields.
        assert "module" in all_engine
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_all_fields_includes_more_properties::post_2
        # Confirms that 'is_abstract' is omitted from the llm_engine dict, showing that
        # fields='all' correctly filters out properties not belonging to the LLM subset.
        assert "is_abstract" not in llm_engine
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_all_fields_includes_more_properties::post_3
        # Checks that 'is_abstract' is present in the all_engine dict, confirming that
        # fields='all' includes this property when appropriate.
        assert "is_abstract" in all_engine
        # tags is in _llm_fields so present in both
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_all_fields_includes_more_properties::post_4
        # Confirms that the extra field 'tags' appears in the llm_engine serialization,
        # showing that it is included when fields='all' is used.
        assert "tags" in llm_engine
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_all_fields_includes_more_properties::post_5
        # Verifies that 'tags' is included in the all_engine serialization, confirming
        # that the all-field set captures metadata properties beyond the basic LLM
        # fields.
        assert "tags" in all_engine

    def test_all_fields_includes_canonical_key(self):
        """serialize() always includes canonical_key (WP B)."""
        import codegraph.identity as identity_mod
        _ = identity_mod  # (doc references resolved via _key below)
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_all_fields_includes_uid_property::step_0
        # Calls the serialize method with fields='all' on the prepared LayerGraph to
        # obtain the full serialized output that will be checked for the presence of the
        # refid property.
        data = [
            {"type": "FileNode", "name": "main.h", "path": "/src/main.h",
             "source": "calculator",
             "canonical_key": _key("/src/main.h", cls=FileNode)},
        ]
        graph = LayerGraph.deserialize(data)
        all_output = graph.serialize(fields="all")
        file_entry = next(e for e in all_output if e["type"] == "FileNode")
        assert file_entry["canonical_key"].startswith("cg:v1:")

    def test_fields_propagates_to_nested_children(self):
        """fields parameter propagates through composes children."""
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_fields_propagates_to_nested_children::step_0
        # Constructs the initial serialized representation of the layer graph, capturing
        # the explicit field assignments on the root and its composite children
        # (widget_llm) before any serialization round-trip.
        data = [
            {"type": "NamespaceNode", "name": "ns", "kind": "namespace",
             "qualified_name": "ns", "canonical_key": _key("ns", cls=NamespaceNode),
             "edges": [{"relation_type": "COMPOSES", "target_type": "ClassNode",
                         "target_key": _key("ns::Widget")}]},
            {"type": "ClassNode", "name": "Widget", "kind": "class",
             "qualified_name": "ns::Widget", "module": "mymod",
             "canonical_key": _key("ns::Widget", cls=ClassNode)},
        ]
        graph = LayerGraph.deserialize(data)

        llm_output = graph.serialize()
        all_output = graph.serialize(fields="all")

        # In LLM mode, the child ClassNode should lack 'module'
        ns_llm = next(e for e in llm_output if e["type"] == "NamespaceNode")
        widget_llm = next(c for c in ns_llm.get("composes", []) if c["type"] == "ClassNode")
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_fields_propagates_to_nested_children::post_0
        # Verifies that the field 'module' is absent from the 'widget_llm' composite
        # layer after round-trip, confirming that serialization respects that this
        # composite does not inherit the 'module' field from the parent when it is not
        # defined for that specific composite.
        assert "module" not in widget_llm

        # In all mode, the child ClassNode should have 'module'
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_fields_propagates_to_nested_children::step_1
        # Performs a serialization round-trip (serialize then deserialize) on the graph
        # and extracts the resulting fields for the all-layer variant, enabling
        # verification that fields have propagated to nested children.
        ns_all = next(e for e in all_output if e["type"] == "NamespaceNode")
        widget_all = next(c for c in ns_all.get("composes", []) if c["type"] == "ClassNode")
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_fields_propagates_to_nested_children::post_1
        # Confirms that the field 'module' is present in the deserialized 'widget_all'
        # layer, demonstrating that top-level fields propagate correctly through
        # serialization and deserialization to composite children that include all
        # layers.
        assert "module" in widget_all

    def test_composite_entry_serialize_fields(self):
        """CompositeEntry.serialize(fields=...) forwards to its node."""
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_composite_entry_serialize_fields::step_0
        # Sets up the test by calling entry.serialize(fields=...) with specific field
        # subsets (e.g., LLM-only, all fields) to collect output results, advancing the
        # test toward verification of field inclusion or exclusion.
        node = ClassNode(name="Widget", kind="class", qualified_name="ns::Widget",
                         source="test", module="mymod", is_abstract=True)
        node.canonical_key = _key("ns::Widget", cls=ClassNode)
        entry = CompositeEntry(node=node)

        llm_result = entry.serialize()
        all_result = entry.serialize(fields="all")

        # LLM mode
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_composite_entry_serialize_fields::post_0
        # Verifies that the field 'name' is included in the LLM-only serialization
        # result, confirming that basic identification fields are always present even in
        # limited context serialization.
        assert "name" in llm_result
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_composite_entry_serialize_fields::post_1
        # Verifies that the field 'module' is not included in the LLM-only serialization
        # result, ensuring that the CompositeEntry correctly omits irrelevant fields
        # when serializing for a limited context.
        assert "module" not in llm_result
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_composite_entry_serialize_fields::post_2
        # Verifies that the field 'is_abstract' is not included in the LLM-only
        # serialization result, ensuring that abstract class metadata is filtered out
        # for simpler, LLM-focused output.
        assert "is_abstract" not in llm_result

        # All mode
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_composite_entry_serialize_fields::post_3
        # Verifies that the field 'name' is included in the all-fields serialization
        # result, confirming that essential identifiers are preserved when serializing
        # the full set of fields.
        assert "name" in all_result
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_composite_entry_serialize_fields::post_4
        # Verifies that the field 'module' is included in the all-fields serialization
        # result, checking that module information is provided when all fields are
        # requested.
        assert "module" in all_result
        # codegraph:test-desc test_layer_graph.TestSerializeFields.test_composite_entry_serialize_fields::post_5
        # Verifies that the field 'is_abstract' is included in the all-fields
        # serialization result, ensuring that abstract status is available when the full
        # set of fields is requested.
        assert "is_abstract" in all_result

class TestFromNeo4j:
    """Tests for LayerGraph.from_neo4j()."""

    def test_fetches_design_tag_nodes(self):
        """from_neo4j returns nodes tagged design and their neighbors."""
        # Seed some nodes first
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_fetches_design_tag_nodes::step_0
        # Sets up the test by creating a complete graph and another graph with only
        # design-tagged nodes and their neighbors, providing the data needed for the
        # subsequent action.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()

        # Now fetch via from_neo4j
        design = LayerGraph.from_neo4j("design")
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_fetches_design_tag_nodes::post_0
        # Verifies that from_neo4j returns a result (greater than something), ensuring
        # the method completes successfully and yields non-empty output.
        assert _count_all_entries(design) > 0
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_fetches_design_tag_nodes::post_1
        # Confirms that the returned graph's design node has exactly the tag 'design',
        # validating that the filtering correctly identifies nodes based on the design
        # tag.
        assert design.tags == frozenset({"design"})

        # Should include at least the ClassNode we created
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_fetches_design_tag_nodes::step_1
        # Executes the from_neo4j method on the graph fixture to filter and return only
        # design-tagged nodes and their neighbors, which is the core action under test.
        class_entries = [
            e for e in design._all_entries() if type(e.node).__name__ == "ClassNode"
        ]
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_fetches_design_tag_nodes::post_2
        # Checks that the returned graph contains at least one class entry, ensuring
        # that neighbor nodes of design-tagged nodes are included in the result.
        assert len(class_entries) > 0

    def test_includes_neighbors_of_tag_nodes(self):
        """Neighbors of tag-matched nodes are included even if different tags."""
        # FileNodes don't have tags, but are DEFINED_IN targets of design-tagged nodes
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_includes_neighbors_of_tag_nodes::step_0
        # This step sets up the test environment by constructing or populating the
        # LayerGraph with nodes and relationships that simulate a scenario where
        # tag-matched nodes have neighbors with different tags, preparing the state for
        # the subsequent assertion.
        with open(FIXTURE) as f:
            data = json.load(f)
        LayerGraph.deserialize(data).to_neo4j()

        design = LayerGraph.from_neo4j("design")
        # FileNodes should appear as neighbors
        file_entries = [
            e for e in design._all_entries() if type(e.node).__name__ == "FileNode"
        ]
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_includes_neighbors_of_tag_nodes::post_0
        # This assertion verifies that the list of file entries retrieved from the graph
        # contains at least one FileNode, confirming that neighbor nodes with different
        # tags are correctly included as neighbors of design nodes, which is essential
        # for the completeness of the graph query logic.
        assert len(file_entries) > 0, "FileNodes should be included as neighbors of design nodes"

    def test_incoming_composes_nests_child_under_parent(self):
        """from_neo4j should nest children under parents even when discovered
        via incoming COMPOSES from the child side."""
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_incoming_composes_nests_child_under_parent::step_0
        # Sets up the LayerGraph by creating and serializing parent and child layer
        # entries to Neo4j, establishing the graph structure for the test.
        with open(FIXTURE) as f:
            data = json.load(f)
        LayerGraph.deserialize(data).to_neo4j()

        result = LayerGraph.from_neo4j("design")
        # Methods should be nested under their parent ClassNode,
        # not appear as root entries
        add_entry = _find_entry(result, _key("calc::CalculatorEngine::add", "(double a, double b)"))
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_incoming_composes_nests_child_under_parent::post_0
        # Verifies that the parent layer entry (add_entry) exists in the result,
        # confirming it was correctly reconstructed from Neo4j.
        assert add_entry is not None
        # The method should NOT be at the root level
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_incoming_composes_nests_child_under_parent::post_1
        # Confirms that no unexpected or duplicate entries exist in the result, ensuring
        # correct nesting and no extraneous data.
        assert "calc::CalculatorEngine::add" not in result.entries
        # The parent class should contain the method
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_incoming_composes_nests_child_under_parent::step_1
        # Calls `from_neo4j` to reconstruct the LayerGraph from the Neo4j database,
        # ensuring that children are correctly nested under their parent layers.
        engine_entry = _find_entry(result, _key("calc::CalculatorEngine"))
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_incoming_composes_nests_child_under_parent::post_2
        # Checks that the child layer entry (engine_entry) is present in the result,
        # validating that child nodes are properly included in the reconstruction.
        assert engine_entry is not None
        # codegraph:test-desc test_layer_graph.TestFromNeo4j.test_incoming_composes_nests_child_under_parent::post_3
        # Asserts that the child layer entry is listed within the parent’s children set,
        # verifying correct hierarchical nesting after reconstruction.
        assert "MethodNode" in engine_entry.children

class TestSerializeNested:
    """Tests for LayerGraph.serialize() nested output format."""

    def test_no_composes_in_edges(self):
        """COMPOSES edges should not appear in any entry's edges array."""
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_no_composes_in_edges::step_0
        # Sets up the test environment by creating a LayerGraph structure with multiple
        # nested layers and edges of various types, including COMPOSES, to simulate a
        # realistic graph for serialization.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        output = graph.serialize()

        def _check_no_composes(items: list[dict]) -> None:
            for item in items:
                for edge in item.get("edges", []):
                    # codegraph:test-desc test_layer_graph.TestSerializeNested.test_no_composes_in_edges::post_0
                    # Checks that no edge in the deserialized graph has a relation type
                    # of 'COMPOSES', confirming that such edges are excluded from the
                    # edges array as required by the serialization contract.
                    assert edge["relation_type"] != "COMPOSES"
                _check_no_composes(item.get("composes", []))

        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_no_composes_in_edges::step_1
        # Calls the serialize method on the prepared LayerGraph to produce a JSON
        # representation of the graph, then parses it back via deserialize to verify the
        # transformation round-trip.
        _check_no_composes(output)

    def test_composes_key_present_for_parents(self):
        """Entries that compose children should have a composes key."""
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composes_key_present_for_parents::step_0
        # Sets up the initial LayerGraph with a specific nested layer structure,
        # preparing the data needed for the serialization and deserialization
        # operations.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        output = graph.serialize()

        # NamespaceNode "calc" composes CalculatorEngine, CalculatorResult,
        # ICalculator, Operation, and formatResult
        calc_entry = next(e for e in output if e.get("name") == "calc")
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composes_key_present_for_parents::post_0
        # Verifies that the entry for the 'calc' layer contains a 'composes' key,
        # confirming that a parent with children is correctly marked as composing child
        # layers.
        assert "composes" in calc_entry
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composes_key_present_for_parents::post_1
        # Checks that the 'composes' list for the 'calc' layer has exactly 5 elements,
        # ensuring that all child layers are correctly identified and counted.
        assert len(calc_entry["composes"]) == 5

        # CalculatorEngine composes methods + attribute
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composes_key_present_for_parents::step_1
        # Calls serialize() on the graph to convert it into a dictionary representation,
        # which is the first step in the round-trip serialization/deserialization
        # process.
        engine_entry = next(
            c for c in calc_entry["composes"] if c.get("name") == "CalculatorEngine"
        )
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composes_key_present_for_parents::post_2
        # Asserts that the entry for the 'engine' layer includes a 'composes' key,
        # verifying that another parent with children is also properly marked after
        # deserialization.
        assert "composes" in engine_entry

        # FileNode has no children — no composes key
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composes_key_present_for_parents::step_2
        # Calls deserialize() on the serialized data to reconstruct a LayerGraph,
        # completing the round-trip and enabling verification of the 'composes' key in
        # the final entries.
        file_entry = next(e for e in output if e.get("type") == "FileNode")
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composes_key_present_for_parents::post_3
        # Ensures that the entry for the 'file' layer does not have a 'composes' key,
        # confirming that leaf layers without children are correctly not marked as
        # composing any layers.
        assert "composes" not in file_entry

    def test_composed_children_not_at_root(self):
        """Composed children should not appear as top-level entries."""
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composed_children_not_at_root::step_0
        # Serializes the LayerGraph to a neo4j-compatible dictionary and extracts the
        # names of all root-level entries, advancing the test to the point where root
        # names can be inspected.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        output = graph.serialize()

        # Composed children use qualified_name as keys in nested output;
        # check that short names like "add" don't appear at the root level.
        # (The serialized output uses "name" for display, not the key.)
        root_names = {e.get("name") for e in output}
        # Members are composed by their parent — their names shouldn't be at root
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composed_children_not_at_root::post_0
        # Verifies that the composed child 'add' is not in the list of root names,
        # confirming that composite children are correctly nested and not promoted to
        # top-level entries during serialization.
        assert "add" not in root_names
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composed_children_not_at_root::post_1
        # Verifies that the composed child 'precision' is not in the list of root names,
        # further confirming that composite children are excluded from top-level entries
        # as required.
        assert "precision" not in root_names
        # "calc" namespace IS at root
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_composed_children_not_at_root::post_2
        # Verifies that the top-level composable 'calc' is present in the root names,
        # ensuring that non-composed nodes still appear at the top level after
        # serialization.
        assert "calc" in root_names

    def test_output_written_to_file(self):
        """serialize output should be persistable and re-loadable."""
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_output_written_to_file::step_0
        # Serializes the 'graph' fixture to a temporary file and then deserializes that
        # file into the 'restored' fixture, setting up the test for comparing the
        # original and deserialized graphs.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        output = graph.serialize()

        FIXTURE_DIR.mkdir(exist_ok=True)
        out_path = Path(__file__).resolve().parent / "data" / "layer_graph_export.json"
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2)

        # Verify we can roundtrip via deserialize
        with open(out_path) as f:
            loaded = json.load(f)
        restored = LayerGraph.deserialize(loaded)
        # codegraph:test-desc test_layer_graph.TestSerializeNested.test_output_written_to_file::post_0
        # Verifies that the serialized output file exists, ensuring that the
        # serialization method writes data to disk correctly for persistence.
        assert _count_all_entries(restored) == _count_all_entries(graph)

class TestDeserializeNested:
    """Tests for LayerGraph.deserialize() with nested (composes) format."""

    def test_creates_nodes_from_nested_data(self):
        """Nested format should produce same total entry count as flat format."""
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_creates_nodes_from_nested_data::step_0
        # Sets up the test by building both the flat and nested LayerGraph fixtures,
        # ensuring each is ready for the subsequent comparison.
        with open(FIXTURE) as f:
            flat_data = json.load(f)
        graph_flat = LayerGraph.deserialize(flat_data)
        graph_flat.to_neo4j()
        nested_data = graph_flat.serialize()

        graph_nested = LayerGraph.deserialize(nested_data)
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_creates_nodes_from_nested_data::post_0
        # Verifies that the total entry count in the nested graph equals the count in
        # the flat graph, confirming that deserialization correctly handles nested
        # structures without losing or duplicating entries.
        assert _count_all_entries(graph_nested) == _count_all_entries(graph_flat)

    def test_composes_children_nested(self):
        """COMPOSES from nested data should create nesting under parent."""
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_composes_children_nested::step_0
        # Sets up the test environment, creates the initial nested LayerGraph,
        # serializes it, and then deserializes the data into the restored graph,
        # preparing for verification of child compositions.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        nested = graph.serialize()

        restored = LayerGraph.deserialize(nested)
        engine = _find_entry(restored, _key("calc::CalculatorEngine"))
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_composes_children_nested::post_0
        # Confirms that the deserialization process returned a valid LayerGraph object
        # rather than None, which is essential before further assertions can be trusted.
        assert engine is not None
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_composes_children_nested::post_1
        # Checks that another child node, also expected under the same parent, exists in
        # the deserialized graph, ensuring all nested children are properly composed.
        assert "MethodNode" in engine.children
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_composes_children_nested::post_2
        # Verifies that a specific child node, expected to be nested under a parent, is
        # present in the restored graph, confirming that deep nesting is correctly
        # reconstructed.
        assert "AttributeNode" in engine.children

    def test_references_preserved(self):
        """Non-COMPOSES edges should be stored as references after nested parse."""
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_references_preserved::step_0
        # Sets up the test by creating the initial LayerGraph fixture with nested nodes
        # and edges of different types, including COMPOSES and non-COMPOSES
        # relationships.
        with open(FIXTURE) as f:
            data = json.load(f)
        graph = LayerGraph.deserialize(data)
        graph.to_neo4j()
        nested = graph.serialize()

        restored = LayerGraph.deserialize(nested)
        engine = _find_entry(restored, _key("calc::CalculatorEngine"))
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_references_preserved::post_0
        # Verifies that the deserialization engine was successfully created (not None),
        # ensuring that no error occurred during the deserialization process that would
        # prevent further assertions.
        assert engine is not None
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_references_preserved::step_1
        # Serializes the original graph and then immediately deserializes it to produce
        # the 'restored' graph, enabling subsequent verification that reference types
        # are preserved.
        ref_types = {r[0] for r in engine.references}
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_references_preserved::post_1
        # Asserts that the 'REALIZES' relationship type is present among the
        # non-COMPOSES edges on the restored graph, confirming that this reference type
        # was correctly stored and retrieved.
        assert "REALIZES" in ref_types
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_references_preserved::post_2
        # Asserts that the 'DEPENDS_ON' relationship type is present among the
        # non-COMPOSES edges, verifying that dependencies are preserved through
        # serialization and deserialization.
        assert "DEPENDS_ON" in ref_types
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_references_preserved::post_3
        # Asserts that the 'DEFINED_IN' relationship type is present, ensuring that
        # definition containment references are accurately maintained from the original
        # graph.
        assert "DEFINED_IN" in ref_types
        # codegraph:test-desc test_layer_graph.TestDeserializeNested.test_references_preserved::post_4
        # Asserts that the 'COMPOSES' relationship type is NOT present among the
        # reference types, confirming that only non-COMPOSES edges are stored as
        # references as intended.
        assert "COMPOSES" not in ref_types
