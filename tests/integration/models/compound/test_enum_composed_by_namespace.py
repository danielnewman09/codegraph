"""Unit test: EnumNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on EnumNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import EnumNode
from codegraph.models.namespace import NamespaceNode
from codegraph.backends import get_backend
from codegraph.persistence.repository import GraphRepository


# codegraph:test-desc compound.test_enum_composed_by_namespace.test_enum_composed_by_namespace
# Verifies that an EnumNode can be correctly composed within a NamespaceNode, ensuring
# the enumeration is properly nested and recognized as part of the namespace hierarchy.
def test_enum_composed_by_namespace():
    # codegraph:test-desc compound.test_enum_composed_by_namespace.test_enum_composed_by_namespace::step_0
    # Sets up the test by creating the namespace node and enum node fixtures,
    # establishing the composition relationship that will be validated later.
    ns_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
        source="test",
    ).save()

    enum_node = EnumNode(
        name="Operation",
        kind="enum",
        brief_description="Supported arithmetic operations",
        source="test",
    ).save()

    # Connect from parent side
    ns_node.enums.connect(enum_node)

    # Verify incoming COMPOSES from child side
    parents = get_backend().graph.incoming_composers(enum_node, NamespaceNode)
    # codegraph:test-desc compound.test_enum_composed_by_namespace.test_enum_composed_by_namespace::post_0
    # Asserts that the number of parent nodes of the enum is exactly 1, verifying that
    # the enum is exclusively composed within the namespace without unintended
    # additional parents.
    assert len(parents) == 1
    # codegraph:test-desc compound.test_enum_composed_by_namespace.test_enum_composed_by_namespace::post_1
    # Asserts that the enum node's 'parents' list contains exactly one element,
    # confirming the namespace is the sole parent, which ensures correct hierarchical
    # linking.
    assert parents[0].canonical_key == ns_node.canonical_key


if __name__ == "__main__":
    test_enum_composed_by_namespace()