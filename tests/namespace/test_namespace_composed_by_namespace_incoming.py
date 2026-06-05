"""Unit test: NamespaceNode incoming COMPOSES from parent NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on NamespaceNode
correctly returns the parent NamespaceNode when connected via COMPOSES
(self-referential nesting).

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.namespace import NamespaceNode


def test_namespace_composed_by_parent_namespace():
    outer_ns = NamespaceNode(
        name="outer",
        kind="namespace",
        description="Outer namespace",
    ).save()

    inner_ns = NamespaceNode(
        name="inner",
        kind="namespace",
        description="Inner nested namespace",
    ).save()

    # Connect from parent side
    outer_ns.namespaces.connect(inner_ns)

    # Verify incoming COMPOSES from child side
    parents = inner_ns.parent_namespace.all()
    assert len(parents) == 1
    assert parents[0]._uid_value() == outer_ns._uid_value()


if __name__ == "__main__":
    test_namespace_composed_by_parent_namespace()