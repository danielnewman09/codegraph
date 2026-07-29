"""Unit test: UnionNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on UnionNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import UnionNode
from codegraph.models.namespace import NamespaceNode
from codegraph.backends import get_backend
from codegraph.persistence.repository import GraphRepository


# codegraph:test-desc compound.test_union_composed_by_namespace.test_union_composed_by_namespace
# Verifies that a UnionNode composed by a NamespaceNode correctly reflects its parent
# namespace, ensuring the union composition logic works as intended.
def test_union_composed_by_namespace():
    # codegraph:test-desc compound.test_union_composed_by_namespace.test_union_composed_by_namespace::step_0
    # Sets up the test environment by initializing the union_node and ns_node fixtures,
    # preparing them for subsequent assertions.
    ns_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
        source="test",
    ).save()

    union_node = UnionNode(
        name="ValueOrError",
        kind="union",
        brief_description="Value or error union type",
        source="test",
    ).save()

    # Connect from parent side
    ns_node.unions.connect(union_node)

    # Verify incoming COMPOSES from child side
    parents = get_backend().graph.incoming_composers(union_node, NamespaceNode)
    # codegraph:test-desc compound.test_union_composed_by_namespace.test_union_composed_by_namespace::post_0
    # Checks that the union_node has exactly one parent, confirming that the namespace
    # correctly assigned a single parent relationship to the union.
    assert len(parents) == 1
    # codegraph:test-desc compound.test_union_composed_by_namespace.test_union_composed_by_namespace::post_1
    # Verifies that the single parent of the union_node is the expected namespace node
    # (ns_node), ensuring the union's parent is correctly set to its composing
    # namespace.
    assert parents[0]._uid_value() == ns_node._uid_value()


if __name__ == "__main__":
    test_union_composed_by_namespace()