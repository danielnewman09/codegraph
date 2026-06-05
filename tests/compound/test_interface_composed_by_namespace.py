"""Unit test: InterfaceNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on InterfaceNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import InterfaceNode
from codegraph.models.namespace import NamespaceNode


def test_interface_composed_by_namespace():
    ns_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    iface_node = InterfaceNode(
        name="ICalculator",
        kind="interface",
        brief_description="Calculator interface contract",
    ).save()

    # Connect from parent side
    ns_node.interfaces.connect(iface_node)

    # Verify incoming COMPOSES from child side
    parents = iface_node.parent_namespace.all()
    assert len(parents) == 1
    assert parents[0]._uid_value() == ns_node._uid_value()


if __name__ == "__main__":
    test_interface_composed_by_namespace()