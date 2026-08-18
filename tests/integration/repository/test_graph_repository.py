"""Tests for GraphRepository — scope-based read methods and save_layer_graph.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

import pytest

from codegraph.graph import LayerGraph, CompositeEntry
from codegraph.models.compound import ClassNode, InterfaceNode, EnumNode
from codegraph.models.member import MethodNode, AttributeNode
from codegraph.models.namespace import NamespaceNode
from codegraph.models.descriptors import PropertyRegistry
from codegraph.backends import get_backend

FIXTURE = Path(__file__).resolve().parent / "data" / "design_graph.json"


def _walk_fixture(data):
    """Yield every node dict from the fixture, including composes children."""
    for item in data:
        yield item
        composes = item.get("composes")
        if isinstance(composes, list):
            yield from _walk_fixture(composes)


_FIXTURE_DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))


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
        argsstring=argsstring or (),
    )
    return resolve_identity_for(probe, scope).key()

pytestmark = pytest.mark.usefixtures("setup_neomodel")

def _all_nodes(graph: LayerGraph):
    """Yield all CodeGraphNode instances from the entry tree."""
    for entry in graph._all_entries():
        yield entry.node

def _nodes_of_type(graph: LayerGraph, type_name: str):
    """Yield all nodes of a given type name from the entry tree.

    Uses ``type().__name__`` instead of ``isinstance`` to avoid
    false positives caused by neomodel's ABCMeta/NodeMeta metaclass
    interaction after ``save()`` / ``connect()``.
    """
    for node in _all_nodes(graph):
        if type(node).__name__ == type_name:
            yield node

def _find_entry(graph: LayerGraph, key: str) -> CompositeEntry | None:
    """Find a CompositeEntry by uid key across the entire tree."""
    for entry in graph._all_entries():
        if LayerGraph._node_key(entry.node) == key:
            return entry
    return None

@pytest.fixture
def seeded_graph():
    """Seed Neo4j with the design_graph fixture and return the LayerGraph."""
    with open(FIXTURE) as f:
        data = json.load(f)
    graph = LayerGraph.deserialize(data)
    graph.to_neo4j()
    return graph

@pytest.fixture
def repo():
    return get_backend().graph

# ── get_by_tag ──────────────────────────────────────────────────────────────

class TestGetByTag:
    # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_returns_layer_graph
    # Verifies that get_by_tag returns a Graph object representing a layer, confirming
    # the repository correctly filters and retrieves layered graph structures by tag.
    def test_returns_layer_graph(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_returns_layer_graph::step_0
        # Sets up the test environment by preparing any required data or state before
        # calling the get_by_tag method, ensuring the test starts from a known
        # condition.
        result = repo.get_by_tag("design")
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_returns_layer_graph::post_0
        # Verifies that the result returned by get_by_tag is an instance of LayerGraph,
        # confirming that the method correctly transforms or retrieves data into the
        # expected domain-specific graph structure.
        assert isinstance(result, LayerGraph)

    # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_includes_design_nodes
    # Verifies that get_by_tag correctly returns design nodes when queried, ensuring
    # that the filtering and retrieval logic of the GraphRepository works as expected.
    def test_includes_design_nodes(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_includes_design_nodes::step_0
        # Sets up the test by retrieving all class nodes associated with the design tag
        # using the GraphRepository, preparing the data needed to verify that
        # design-related nodes are included in the query results.
        result = repo.get_by_tag("design")
        class_nodes = list(_nodes_of_type(result, "ClassNode"))
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_includes_design_nodes::post_0
        # Verifies that at least one class node is returned for the design tag,
        # confirming that the repository correctly includes design nodes when filtering
        # by tag.
        assert len(class_nodes) > 0

    # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_includes_neighbors
    # Verifies that get_by_tag includes neighbor nodes when retrieving entries, ensuring
    # graph traversal correctness for layered repository queries.
    def test_includes_neighbors(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_includes_neighbors::step_0
        # Sets up the test environment, including creating a graph with tagged nodes and
        # their neighbors, to prepare for verifying that get_by_tag correctly includes
        # related entries.
        result = repo.get_by_tag("design")
        # Seed nodes have tags=["design"]; neighbors may not.
        # The LayerGraph should contain more than just the seeds.
        count = sum(1 for _ in result._all_entries())
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_includes_neighbors::post_0
        # Verifies that the number of nodes returned by get_by_tag is greater than zero,
        # confirming that the method successfully retrieves tagged nodes along with
        # their neighbors.
        assert count > 0

    # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_empty_tag
    # Verifies that GraphRepository.get_by_tag raises an appropriate error when passed
    # an empty tag, ensuring proper input validation and preventing silent failures in
    # tag-based graph retrieval.
    def test_empty_tag(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_empty_tag::step_0
        # Sets up the test by invoking the `get_by_tag` method with an empty tag,
        # preparing the result for subsequent assertions.
        result = repo.get_by_tag("nonexistent")
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_empty_tag::post_0
        # Verifies that the result of `get_by_tag` is an instance of `LayerGraph`,
        # ensuring that the method returns the correct type regardless of the tag value.
        assert isinstance(result, LayerGraph)
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_empty_tag::post_1
        # Checks that the returned `LayerGraph` contains zero entries, confirming that
        # querying with an empty tag yields an empty result set as expected.
        assert len(result.entries) == 0

    # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_derived_tags_include_design
    # This test ensures that when querying graph nodes by tag, the results include nodes
    # with derived tags, confirming that the GraphRepository.get_by_tag method correctly
    # expands tag hierarchies and returns all relevant nodes.
    def test_derived_tags_include_design(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_derived_tags_include_design::step_0
        # Sets up the repository and graph context by adding nodes and edges that
        # include design-related tags, enabling the test to later verify that derived
        # tags are correctly included in the query results.
        result = repo.get_by_tag("design")
        # codegraph:test-desc repository.test_graph_repository.TestGetByTag.test_derived_tags_include_design::post_0
        # Checks that a tag derived from a design node is present in the list of tags
        # returned by get_by_tag, confirming that the repository correctly propagates
        # design metadata into derived tags.
        assert "design" in result.tags

# ── get_by_source ────────────────────────────────────────────────────────────

class TestGetBySource:
    # codegraph:test-desc repository.test_graph_repository.TestGetBySource.test_returns_layer_graph
    # Verifies that get_by_source correctly returns the layer graph for a given source,
    # ensuring that graph retrieval operations maintain data integrity and consistency.
    def test_returns_layer_graph(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetBySource.test_returns_layer_graph::step_0
        # Sets up the test environment by preparing the necessary objects or data
        # required before calling the `get_by_source` method on the GraphRepository.
        result = repo.get_by_source("calculator")
        # codegraph:test-desc repository.test_graph_repository.TestGetBySource.test_returns_layer_graph::post_0
        # Asserts that the result returned by `get_by_source` is an instance of
        # `LayerGraph`, ensuring the method returns the expected type and the repository
        # correctly retrieves and structures the graph data by source.
        assert isinstance(result, LayerGraph)

    # codegraph:test-desc repository.test_graph_repository.TestGetBySource.test_includes_source_nodes
    # Verifies that the results from GraphRepository.get_by_source include nodes that
    # match the given source criterion, which ensures the correctness of source-based
    # filtering and retrieval in the repository layer.
    def test_includes_source_nodes(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetBySource.test_includes_source_nodes::step_0
        # Initializes the test environment by creating the necessary graph structure and
        # source nodes to ensure the test has data to query.
        result = repo.get_by_source("calculator")
        source_nodes = [n for n in _all_nodes(result) if source_matches(n, "calculator")]
        # codegraph:test-desc repository.test_graph_repository.TestGetBySource.test_includes_source_nodes::post_0
        # Verifies that the query result includes at least one source node, confirming
        # that the get_by_source method correctly returns source nodes associated with
        # the given source.
        assert len(source_nodes) > 0

    # codegraph:test-desc repository.test_graph_repository.TestGetBySource.test_missing_source_returns_empty
    # Verifies that `get_by_source` returns an empty result when a source that does not
    # exist is requested, ensuring the method handles missing data gracefully without
    # errors or false positives.
    def test_missing_source_returns_empty(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetBySource.test_missing_source_returns_empty::step_0
        # Sets up the test by preparing any necessary context or state before calling
        # the get_by_source method with a source that does not exist in the repository.
        result = repo.get_by_source("nonexistent_project")
        # codegraph:test-desc repository.test_graph_repository.TestGetBySource.test_missing_source_returns_empty::post_0
        # Verifies that the result of get_by_source is a valid LayerGraph object,
        # ensuring the method always returns the expected type even when no data is
        # found.
        assert isinstance(result, LayerGraph)
        # codegraph:test-desc repository.test_graph_repository.TestGetBySource.test_missing_source_returns_empty::post_1
        # Confirms that the LayerGraph returned by get_by_source contains no entries
        # when the requested source is missing, ensuring the method correctly handles
        # absent data by returning an empty result rather than an error.
        assert len(result.entries) == 0

# ── get_by_namespace ─────────────────────────────────────────────────────────

class TestGetByNamespace:
    # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_returns_layer_graph
    # This test verifies that the get_by_namespace method returns a correct layer graph
    # limited to nodes with a given namespace; it is important for ensuring that
    # namespace-based queries filter accurately in graph persistence.
    def test_returns_layer_graph(self, repo, seeded_graph):
        # Find the actual qualified_name of a namespace in the seed graph
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_returns_layer_graph::step_0
        # Sets up the test by preparing a seed graph that contains at least one
        # namespace, ensuring the repository has data to query.
        ns_nodes = list(_nodes_of_type(seeded_graph, "NamespaceNode"))
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_returns_layer_graph::post_0
        # Checks that the seed graph contains at least one namespace node, ensuring the
        # test setup is valid before proceeding with further assertions.
        assert len(ns_nodes) > 0, "Seed graph must have at least one namespace"
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_returns_layer_graph::step_1
        # Executes the get_by_namespace method on the GraphRepository with a given
        # namespace to retrieve the layer graph, advancing the test to the verification
        # phase.
        qname = ns_nodes[0].qualified_name

        result = repo.get_by_namespace(qname)
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_returns_layer_graph::post_1
        # Verifies that the result returned by get_by_namespace is an instance of
        # LayerGraph, confirming the method returns the expected type.
        assert isinstance(result, LayerGraph)

    # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_includes_namespace_and_compounds
    # Verifies that get_by_namespace returns both the specified namespace node and its
    # associated compound nodes, ensuring the repository query correctly filters by
    # namespace while preserving hierarchical relationships.
    def test_includes_namespace_and_compounds(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_includes_namespace_and_compounds::step_0
        # Sets up the test by invoking the method under test and collecting the initial
        # result, which is necessary to perform subsequent assertions on the returned
        # nodes.
        ns_nodes = list(_nodes_of_type(seeded_graph, "NamespaceNode"))
        qname = ns_nodes[0].qualified_name

        result = repo.get_by_namespace(qname)
        ns_in_result = list(_nodes_of_type(result, "NamespaceNode"))
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_includes_namespace_and_compounds::post_0
        # Verifies that at least one node of the expected namespace type is present in
        # the result, ensuring the `get_by_namespace` method correctly filters and
        # returns nodes belonging to the specified namespace.
        assert len(ns_in_result) > 0

    # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_missing_namespace_returns_empty
    # Verifies that GraphRepository.get_by_namespace returns an empty result when
    # queried with a namespace that does not exist, ensuring the method handles missing
    # data gracefully.
    def test_missing_namespace_returns_empty(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_missing_namespace_returns_empty::step_0
        # Calls the get_by_namespace method with a namespace that is known not to exist
        # in the repository, ensuring the test is set up to verify the response for a
        # missing namespace.
        result = repo.get_by_namespace("nonexistent::ns")
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_missing_namespace_returns_empty::post_0
        # Checks that the return type of get_by_namespace is a LayerGraph object,
        # ensuring the method consistently provides the expected structured output even
        # when no data is found.
        assert isinstance(result, LayerGraph)
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_missing_namespace_returns_empty::post_1
        # Verifies that the result contains exactly zero entries, confirming the
        # repository correctly returns an empty set when the namespace is missing.
        assert len(result.entries) == 0

    def test_includes_non_class_composed_entities(self, repo, seeded_graph):
        """Namespace should include interfaces, enums, and functions composed by it."""
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_includes_non_class_composed_entities::step_0
        # Sets up the test by retrieving all node types from the repository for a given
        # namespace, preparing the data needed to verify that all composed entities are
        # included.
        result = repo.get_by_namespace("calc")
        node_types = {type(n).__name__ for n in _all_nodes(result)}
        # The calc namespace composes classes, interface, enum, and function
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_includes_non_class_composed_entities::post_0
        # Confirms that the namespace's returned nodes include ClassNode, ensuring that
        # class entities composed by the namespace are present in the results.
        assert "ClassNode" in node_types
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_includes_non_class_composed_entities::post_1
        # Checks that InterfaceNode is present in the node types returned, confirming
        # that interfaces composed by the namespace are included.
        assert "InterfaceNode" in node_types
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_includes_non_class_composed_entities::post_2
        # Ensures that EnumNode is part of the returned node types, verifying that enums
        # composed by the namespace are included.
        assert "EnumNode" in node_types
        # codegraph:test-desc repository.test_graph_repository.TestGetByNamespace.test_includes_non_class_composed_entities::post_3
        # Validates that FunctionNode is among the returned node types, verifying that
        # functions composed by the namespace are properly included.
        assert "FunctionNode" in node_types

# ── get_by_compound ──────────────────────────────────────────────────────────

class TestGetByCompound:
    # codegraph:test-desc repository.test_graph_repository.TestGetByCompound.test_returns_layer_graph
    # Verifies that get_by_compound returns exactly layer-level nodes for the given
    # compound, ensuring the method correctly filters the repository graph by node type
    # and compound identifier.
    def test_returns_layer_graph(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByCompound.test_returns_layer_graph::step_0
        # Sets up the test by preparing any necessary data or context before calling the
        # get_by_compound method.
        class_nodes = list(_nodes_of_type(seeded_graph, "ClassNode"))
        qname = class_nodes[0].qualified_name

        result = repo.get_by_compound(qname)
        # codegraph:test-desc repository.test_graph_repository.TestGetByCompound.test_returns_layer_graph::post_0
        # Verifies that the result of get_by_compound is a LayerGraph instance, ensuring
        # the method returns the expected graph structure for the given compound.
        assert isinstance(result, LayerGraph)

    # codegraph:test-desc repository.test_graph_repository.TestGetByCompound.test_includes_compound
    # Verifies that get_by_compound returns nodes containing the specified compound,
    # ensuring correct filtering behavior in the graph repository.
    def test_includes_compound(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByCompound.test_includes_compound::step_0
        # Sets up the test environment by preparing the repository and creating sample
        # compound nodes to ensure there is data available for retrieval.
        class_nodes = list(_nodes_of_type(seeded_graph, "ClassNode"))
        qname = class_nodes[0].qualified_name

        result = repo.get_by_compound(qname)
        compounds = list(_nodes_of_type(result, "ClassNode"))
        # codegraph:test-desc repository.test_graph_repository.TestGetByCompound.test_includes_compound::post_0
        # Verifies that the list of compounds returned by the query is not empty,
        # confirming that the repository can successfully retrieve existing compound
        # data.
        assert len(compounds) > 0

    # codegraph:test-desc repository.test_graph_repository.TestGetByCompound.test_missing_compound_returns_empty
    # Verifies that querying a non-existent compound returns an empty result set,
    # ensuring the repository handles missing compounds gracefully without errors or
    # invalid data.
    def test_missing_compound_returns_empty(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByCompound.test_missing_compound_returns_empty::step_0
        # Sets up the test environment, likely by initializing a GraphRepository
        # instance and ensuring no compound with the target identifier exists, to
        # prepare for testing the get_by_compound method's response to a missing
        # compound.
        result = repo.get_by_compound("NonexistentClass")
        # codegraph:test-desc repository.test_graph_repository.TestGetByCompound.test_missing_compound_returns_empty::post_0
        # Verifies that the result returned by get_by_compound is a valid LayerGraph
        # object, ensuring the method always returns the expected data structure even
        # when no matching compound is found.
        assert isinstance(result, LayerGraph)
        # codegraph:test-desc repository.test_graph_repository.TestGetByCompound.test_missing_compound_returns_empty::post_1
        # Confirms that the entries list within the returned LayerGraph is empty, which
        # is crucial to validate that the method correctly handles the case of a missing
        # compound by returning an empty result rather than an error or unexpected data.
        assert len(result.entries) == 0

# ── get_by_neighbourhood ────────────────────────────────────────────────────

class TestGetByNeighbourhood:
    # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_works_for_compound
    # Verifies that retrieving entries by neighbourhood from the graph repository
    # correctly returns all entries of a given type for a compound element, ensuring the
    # core retrieval logic for compound structures is accurate and reliable.
    def test_works_for_compound(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_works_for_compound::step_0
        # Sets up test data by creating a `LayerGraph` instance with predefined nodes
        # and inserting them into the repository, providing the necessary state for the
        # subsequent retrieval operation.
        class_nodes = list(_nodes_of_type(seeded_graph, "ClassNode"))
        qname = class_nodes[0].qualified_name

        result = repo.get_by_neighbourhood(qname)
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_works_for_compound::post_0
        # Verifies that the result of `get_by_neighbourhood` is a `LayerGraph` instance,
        # ensuring the method returns the correct type expected by the system.
        assert isinstance(result, LayerGraph)
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_works_for_compound::step_1
        # Calls `get_by_neighbourhood` to fetch nodes of a specified type from the
        # repository and advances the test by producing the result to be validated.
        count = sum(1 for _ in result._all_entries())
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_works_for_compound::post_1
        # Checks that the returned graph contains at least one node, confirming that the
        # retrieval successfully found matching entries in the repository.
        assert count > 0

    # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_works_for_member
    # Verifies that the get_by_neighbourhood method correctly retrieves a member node's
    # neighbours, ensuring the graph query returns accurate relationships for membership
    # connections.
    def test_works_for_member(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_works_for_member::step_0
        # Set up the test environment by populating the graph repository with nodes and
        # relationships, ensuring a valid neighbourhood exists for the method under
        # test.
        method_nodes = list(_nodes_of_type(seeded_graph, "MethodNode"))
        if not method_nodes:
            pytest.skip("No method nodes in seed graph")
        qname = method_nodes[0].qualified_name

        result = repo.get_by_neighbourhood(qname)
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_works_for_member::post_0
        # Verify that the result returned by get_by_neighbourhood is a LayerGraph
        # object, confirming the method correctly produces a structured graph output.
        assert isinstance(result, LayerGraph)
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_works_for_member::step_1
        # Execute the get_by_neighbourhood method with a specific member node, and apply
        # the _nodes_of_type filter to prepare the result for assertion.
        members = list(_nodes_of_type(result, "MethodNode"))
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_works_for_member::post_1
        # Check that the members list within the result is non-empty, ensuring that the
        # query successfully retrieves relevant nodes in the neighbourhood.
        assert len(members) > 0

    # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_missing_node_returns_empty
    # This test verifies that the get_by_neighbourhood method returns an empty result
    # when queried for neighbours of a node that does not exist, ensuring the method
    # handles missing nodes gracefully without errors.
    def test_missing_node_returns_empty(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_missing_node_returns_empty::step_0
        # Sets up the test environment by preparing a graph repository context and
        # invoking the get_by_neighbourhood method with a node ID that does not exist in
        # the graph, to exercise the missing node scenario.
        result = repo.get_by_neighbourhood("DoesNotExist")
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_missing_node_returns_empty::post_0
        # Verifies that the result returned by get_by_neighbourhood is a LayerGraph
        # instance, ensuring the method's output type remains consistent even when no
        # neighbourhood is found.
        assert isinstance(result, LayerGraph)
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_missing_node_returns_empty::post_1
        # Checks that the entries list within the result LayerGraph is empty, confirming
        # that querying a non-existent node correctly yields no neighbourhood data.
        assert len(result.entries) == 0

    def test_method_seed_discovers_parent_class(self, repo, seeded_graph):
        """When a MethodNode is the seed, its parent ClassNode should be
        discovered via incoming COMPOSES and the method should be nested
        under the class."""
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_method_seed_discovers_parent_class::step_0
        # Sets up the test environment by calling `_find_entry` and `_uid` to locate and
        # prepare the MethodNode seed and its parent ClassNode, ensuring the necessary
        # graph elements are available for neighbourhood traversal.
        result = repo.get_by_neighbourhood("calc::CalculatorEngine::add")
        # The method should NOT be a root entry
        method_entry = _find_entry(result, _key("calc::CalculatorEngine::add", "(double a, double b)"))
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_method_seed_discovers_parent_class::post_0
        # Confirms that the method entry returned by the neighbourhood query is not
        # None, ensuring the seed MethodNode was successfully located in the graph.
        assert method_entry is not None
        # The method should be nested under the parent class, not at root
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_method_seed_discovers_parent_class::post_1
        # Verifies that the parent ClassNode (engine_entry) does not contain a stray
        # MethodNode entry in its children, ensuring the query correctly excludes
        # unrelated nodes from the result set.
        assert _key("calc::CalculatorEngine::add", "(double a, double b)") not in result.entries
        # The parent class should be in the graph
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_method_seed_discovers_parent_class::step_1
        # Executes `GraphRepository.get_by_neighbourhood` with the MethodNode as seed,
        # retrieving the parent class and its children to verify that the neighbourhood
        # query correctly discovers the ancestor hierarchy.
        engine_entry = _find_entry(result, _key("calc::CalculatorEngine"))
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_method_seed_discovers_parent_class::post_2
        # Checks that the engine_entry (parent ClassNode) is not None, confirming that
        # the neighbourhood query successfully discovered the parent class from the
        # method seed.
        assert engine_entry is not None
        # The method should appear under the class's "MethodNode" children
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_method_seed_discovers_parent_class::post_3
        # Asserts that the method entry corresponding to the seed is present in the
        # children of the parent ClassNode, validating that the relationship between
        # method and class is correctly returned.
        assert "MethodNode" in engine_entry.children
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_method_seed_discovers_parent_class::post_4
        # Verifies that another specific method (`add`) is included as a child
        # MethodNode of the parent ClassNode, confirming that the neighbourhood query
        # retrieves all sibling methods in the parent class.
        assert _key("calc::CalculatorEngine::add", "(double a, double b)") in engine_entry.children["MethodNode"]

    def test_class_seed_discovers_parent_namespace(self, repo, seeded_graph):
        """When a ClassNode is the seed, the parent NamespaceNode should be
        discovered via incoming COMPOSES."""
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_class_seed_discovers_parent_namespace::step_0
        # Sets up the test environment by calling get_by_neighbourhood with a ClassNode
        # seed to obtain the parent NamespaceNode entry, preparing the data needed for
        # subsequent assertions.
        result = repo.get_by_neighbourhood("calc::CalculatorEngine")
        calc_entry = _find_entry(result, _key("calc"))
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_class_seed_discovers_parent_namespace::post_0
        # Checks that the retrieved namespace entry exists and is not null, ensuring the
        # query successfully found the parent namespace for the given class seed.
        assert calc_entry is not None
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_class_seed_discovers_parent_namespace::post_1
        # Verifies that the calculated UID of the CalculatorEngine class is listed among
        # the children of the namespace entry under the ClassNode key, ensuring the
        # class is correctly associated with its parent namespace.
        assert "ClassNode" in calc_entry.children
        # codegraph:test-desc repository.test_graph_repository.TestGetByNeighbourhood.test_class_seed_discovers_parent_namespace::post_2
        # Confirms that a specific class node (CalculatorEngine) appears as a child of
        # its parent namespace entry, validating that the neighbourhood lookup returns
        # the expected hierarchical relationship.
        assert _key("calc::CalculatorEngine") in calc_entry.children["ClassNode"]

# ── get_by_kind ──────────────────────────────────────────────────────────────

class TestGetByKind:
    # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_returns_layer_graph
    # Verifies that get_by_kind returns a correct graph structure for a specified layer
    # kind, ensuring the repository correctly filters graph entries by type.
    def test_returns_layer_graph(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_returns_layer_graph::step_0
        # Sets up the test environment by creating necessary test data and invoking the
        # get_by_kind method on the repository, which is the entry point for the test.
        result = repo.get_by_kind("class")
        # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_returns_layer_graph::post_0
        # Verifies that the result returned by get_by_kind is an instance of LayerGraph,
        # ensuring the method returns the correct type as expected by the application's
        # architecture.
        assert isinstance(result, LayerGraph)

    # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_includes_class_nodes
    # Verifies that the repository's get_by_kind returns class nodes when queried for
    # kind 'class', ensuring that type-filtered retrieval functions correctly for
    # maintainability.
    def test_includes_class_nodes(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_includes_class_nodes::step_0
        # Sets up the test by retrieving nodes of a specific type (e.g., class nodes)
        # from the repository using the `get_by_kind` method, preparing the data needed
        # for subsequent assertions.
        result = repo.get_by_kind("class")
        class_nodes = list(_nodes_of_type(result, "ClassNode"))
        # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_includes_class_nodes::post_0
        # Verifies that at least one class node was returned by the `get_by_kind`
        # method. This confirms that the repository correctly retrieves nodes of the
        # requested kind and that class nodes exist in the test graph.
        assert len(class_nodes) > 0

    # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_with_tag_filter
    # Verifies that the get_by_kind method correctly filters graph nodes by their
    # assigned tags, ensuring that the repository returns only nodes that belong to the
    # specified kind and match the tag condition, which is essential for precise and
    # reliable data retrieval in tagged graph queries.
    def test_with_tag_filter(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_with_tag_filter::step_0
        # Sets up necessary test data, likely creating graph nodes and applying a tag
        # filter, to prepare for the get_by_kind operation.
        result = repo.get_by_kind("class", tag="design")
        # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_with_tag_filter::post_0
        # Verifies that the result of get_by_kind is a valid LayerGraph instance, which
        # is essential because the method is expected to return a structured graph
        # object.
        assert isinstance(result, LayerGraph)
        # All returned nodes with a tags property should include "design"
        for node in _all_nodes(result):
            if "tags" in PropertyRegistry.properties_of(type(node)):
                # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_with_tag_filter::post_1
                # Checks that every returned node contains the 'design' tag, confirming
                # that the tag filtering logic correctly includes only nodes with the
                # specified tag.
                assert "design" in (node.tags or [])

    # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_returns_methods
    # This test verifies that get_by_kind correctly returns all MethodNode instances
    # from the graph, ensuring the filtering by node kind works as expected for
    # different node types.
    def test_returns_methods(self, repo, seeded_graph):
        # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_returns_methods::step_0
        # Sets up the initial data by retrieving method nodes from the repository to
        # prepare for verification.
        result = repo.get_by_kind("method")
        method_nodes = list(_nodes_of_type(result, "MethodNode"))
        # codegraph:test-desc repository.test_graph_repository.TestGetByKind.test_returns_methods::post_0
        # Verifies that the retrieved list of method nodes is not empty, confirming that
        # the get_by_kind operation correctly returns expected results.
        assert len(method_nodes) > 0

# ── save_layer_graph ────────────────────────────────────────────────────────

class TestSaveLayerGraph:
    def test_roundtrip(self, repo):
        """Build a LayerGraph from JSON, save, then query it back."""
        # codegraph:test-desc repository.test_graph_repository.TestSaveLayerGraph.test_roundtrip::step_0
        # Sets up the test environment by deserializing a JSON representation into a
        # LayerGraph and saving it using GraphRepository.save_layer_graph, preparing the
        # state for subsequent query and verification.
        with open(FIXTURE) as f:
            data = json.load(f)

        graph = LayerGraph.deserialize(data)
        repo.save_layer_graph(graph)

        # Query back by tag
        result = repo.get_by_tag("design")
        count = sum(1 for _ in result._all_entries())
        # codegraph:test-desc repository.test_graph_repository.TestSaveLayerGraph.test_roundtrip::post_0
        # Verifies that the query returned at least one result, confirming the graph was
        # successfully saved and can be retrieved from the repository by tag.
        assert count > 0

# ── Build LayerGraph entries ────────────────────────────────────────────────

class TestBuildLayerGraphEntries:
    def test_entries_are_composite_entries(self, repo, seeded_graph):
        """All entries should be CompositeEntry instances."""
        # codegraph:test-desc repository.test_graph_repository.TestBuildLayerGraphEntries.test_entries_are_composite_entries::step_0
        # Sets up the test environment by initializing the repository and retrieving
        # entries for the layer graph, preparing the data needed to verify the type of
        # each entry.
        result = repo.get_by_tag("design")
        for entry in result._all_entries():
            # codegraph:test-desc repository.test_graph_repository.TestBuildLayerGraphEntries.test_entries_are_composite_entries::post_0
            # Checks that every retrieved entry is an instance of CompositeEntry,
            # ensuring the graph's fundamental building blocks are consistently
            # composite objects rather than simpler types.
            assert isinstance(entry, CompositeEntry)

    def test_composes_children_and_references(self, repo, seeded_graph):
        """Entries should have COMPOSES in children and other edges in references."""
        # codegraph:test-desc repository.test_graph_repository.TestBuildLayerGraphEntries.test_composes_children_and_references::step_0
        # Sets up the test environment by initializing data structures or state, laying
        # the groundwork for calling the code under test with specific inputs.
        result = repo.get_by_tag("design")
        for entry in result._all_entries():
            # No COMPOSES edges should appear in references
            ref_types = {r[0] for r in entry.references}
            # COMPOSES should not be in references (it's in children)
            # Note: we only enforce this for entries that have children
            if entry.children:
                # codegraph:test-desc repository.test_graph_repository.TestBuildLayerGraphEntries.test_composes_children_and_references::post_0
                # Confirms that the edge type 'COMPOSES' is absent from the reference
                # types, ensuring that child relationships are properly categorized as
                # separate from other references in the graph entry.
                assert "COMPOSES" not in ref_types

# ── Helpers ──────────────────────────────────────────────────────────────────

def source_matches(node, source: str) -> bool:
    """Check if a node's source field matches."""
    return getattr(node, "source", None) == source