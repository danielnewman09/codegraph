"""Unit test: InterfaceNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on InterfaceNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import InterfaceNode
from codegraph.models.namespace import NamespaceNode
from codegraph.backends import get_backend
from codegraph.persistence.repository import GraphRepository


# codegraph:test-desc compound.test_interface_composed_by_namespace.test_interface_composed_by_namespace
# Verifies that an InterfaceNode can be properly composed from a NamespaceNode, ensuring
# correct structural relationships in the code graph.
def test_interface_composed_by_namespace():
    # codegraph:test-desc compound.test_interface_composed_by_namespace.test_interface_composed_by_namespace::step_0
    # Sets up the test by creating the necessary node instances and performing the
    # composition operation that will be verified by subsequent assertions.
    ns_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
        source="test",
    ).save()

    iface_node = InterfaceNode(
        name="ICalculator",
        kind="interface",
        brief_description="Calculator interface contract",
        source="test",
    ).save()

    # Connect from parent side
    ns_node.interfaces.connect(iface_node)

    # Verify incoming COMPOSES from child side
    parents = get_backend().graph.incoming_composers(iface_node, NamespaceNode)
    # codegraph:test-desc compound.test_interface_composed_by_namespace.test_interface_composed_by_namespace::post_0
    # Verifies that the InterfaceNode has exactly one parent node, ensuring the
    # composition establishes the expected hierarchical relationship.
    assert len(parents) == 1
    # codegraph:test-desc compound.test_interface_composed_by_namespace.test_interface_composed_by_namespace::post_1
    # Verifies that the parent relationship matches the expected value, confirming the
    # interface is correctly linked to its namespace.
    assert parents[0]._uid_value() == ns_node._uid_value()


if __name__ == "__main__":
    test_interface_composed_by_namespace()