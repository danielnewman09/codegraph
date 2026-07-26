"""Unit test: NamespaceNode incoming COMPOSES from parent NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on NamespaceNode
correctly returns the parent NamespaceNode when connected via COMPOSES
(self-referential nesting).

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.namespace import NamespaceNode
from codegraph.persistence.repository import GraphRepository


# codegraph:test-desc namespace.test_namespace_composed_by_namespace_incoming.test_namespace_composed_by_parent_namespace
# Verifies that a NamespaceNode correctly composes its qualified name from the namespace
# that contains it (the parent namespace), ensuring accurate hierarchy representation.
def test_namespace_composed_by_parent_namespace():
    # codegraph:test-desc namespace.test_namespace_composed_by_namespace_incoming.test_namespace_composed_by_parent_namespace::step_0
    # Sets up the test by creating the outer_ns and inner_ns fixtures and initiating the
    # namespace composition operation. This step prepares the data structures needed to
    # later verify the incoming namespace relationships.
    outer_ns = NamespaceNode(
        name="outer",
        kind="namespace",
        description="Outer namespace",
        source="test",
    ).save()

    inner_ns = NamespaceNode(
        name="inner",
        kind="namespace",
        description="Inner nested namespace",
        source="test",
    ).save()

    # Connect from parent side
    outer_ns.namespaces.connect(inner_ns)

    # Verify incoming COMPOSES from child side
    parents = GraphRepository.incoming_composers(inner_ns, NamespaceNode)
    # codegraph:test-desc namespace.test_namespace_composed_by_namespace_incoming.test_namespace_composed_by_parent_namespace::post_0
    # Verifies that outer_ns has exactly one parent namespace. This confirms that the
    # namespace composition correctly identifies that outer_ns is contained within
    # another namespace, which is essential for accurate dependency analysis.
    assert len(parents) == 1
    # codegraph:test-desc namespace.test_namespace_composed_by_namespace_incoming.test_namespace_composed_by_parent_namespace::post_1
    # Asserts that the single parent namespace of outer_ns is the expected one. This
    # ensures the namespace hierarchy is correctly resolved, which is critical for
    # understanding the code structure and dependencies.
    assert parents[0]._uid_value() == outer_ns._uid_value()


if __name__ == "__main__":
    test_namespace_composed_by_parent_namespace()