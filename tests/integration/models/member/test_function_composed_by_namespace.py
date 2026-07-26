"""Unit test: FunctionNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on FunctionNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.member import FunctionNode
from codegraph.models.namespace import NamespaceNode
from codegraph.persistence.repository import GraphRepository


# codegraph:test-desc member.test_function_composed_by_namespace.test_function_composed_by_namespace
# Verifies that a FunctionNode composed into a NamespaceNode correctly models the
# relationship between a function and its containing namespace, ensuring that the code
# graph accurately reflects source-level scoping.
def test_function_composed_by_namespace():
    # codegraph:test-desc member.test_function_composed_by_namespace.test_function_composed_by_namespace::step_0
    # Sets up the test environment by creating the namespace and function node fixtures
    # and establishing their parent-child relationship, preparing the test for
    # assertions on the composition.
    ns_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
        source="test",
    ).save()

    func_node = FunctionNode(
        name="formatResult",
        kind="function",
        type_signature="string",
        argsstring="(double value)",
        visibility="public",
        source="test",
    ).save()

    # Connect from parent side
    ns_node.functions.connect(func_node)

    # Verify incoming COMPOSES from child side
    parents = GraphRepository.incoming_composers(func_node, NamespaceNode)
    # codegraph:test-desc member.test_function_composed_by_namespace.test_function_composed_by_namespace::post_0
    # Ensures that the function node has exactly one parent, validating that the
    # composition link between namespace and function is correctly established without
    # extra connections.
    assert len(parents) == 1
    # codegraph:test-desc member.test_function_composed_by_namespace.test_function_composed_by_namespace::post_1
    # Verifies that the function node's parent is exactly the expected namespace node,
    # confirming the correctness of the composition relationship.
    assert parents[0]._uid_value() == ns_node._uid_value()


if __name__ == "__main__":
    test_function_composed_by_namespace()