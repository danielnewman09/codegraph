"""Unit test: ClassNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on ClassNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import ClassNode
from codegraph.models.namespace import NamespaceNode
from codegraph.backends import get_backend
from codegraph.persistence.repository import GraphRepository


# codegraph:test-desc compound.test_class_composed_by_namespace.test_class_composed_by_namespace
# Verifies that a ClassNode composed with a NamespaceNode correctly integrates and
# produces the expected combined behavior, ensuring the composition mechanics function
# properly for compound structures.
def test_class_composed_by_namespace():
    # codegraph:test-desc compound.test_class_composed_by_namespace.test_class_composed_by_namespace::step_0
    # Sets up the composition of the ClassNode inside the NamespaceNode by establishing
    # the parent-child relationship, preparing the context for subsequent assertions.
    ns_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
        source="test",
    ).save()

    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
        source="test",
    ).save()

    # Connect from parent side
    ns_node.classes.connect(class_node)

    # Verify incoming COMPOSES from child side
    parents = get_backend().graph.incoming_composers(class_node, NamespaceNode)
    # codegraph:test-desc compound.test_class_composed_by_namespace.test_class_composed_by_namespace::post_0
    # Verifies that the ClassNode has exactly one parent after composition, confirming
    # that the namespace is correctly set as the sole parent, which is essential for
    # maintaining the intended hierarchy.
    assert len(parents) == 1
    # codegraph:test-desc compound.test_class_composed_by_namespace.test_class_composed_by_namespace::post_1
    # Verifies that the parent of the ClassNode is exactly the NamespaceNode, ensuring
    # the composition link points to the correct namespace node, which is critical for
    # accurate graph traversal and relationship integrity.
    assert parents[0].canonical_key == ns_node.canonical_key


if __name__ == "__main__":
    test_class_composed_by_namespace()