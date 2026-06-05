"""Unit test: UnionNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on UnionNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import UnionNode
from codegraph.models.namespace import NamespaceNode


def test_union_composed_by_namespace():
    ns_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    union_node = UnionNode(
        name="ValueOrError",
        kind="union",
        brief_description="Value or error union type",
    ).save()

    # Connect from parent side
    ns_node.unions.connect(union_node)

    # Verify incoming COMPOSES from child side
    parents = union_node.parent_namespace.all()
    assert len(parents) == 1
    assert parents[0]._uid_value() == ns_node._uid_value()


if __name__ == "__main__":
    test_union_composed_by_namespace()