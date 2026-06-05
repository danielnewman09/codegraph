"""Unit test: EnumNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on EnumNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import EnumNode
from codegraph.models.namespace import NamespaceNode


def test_enum_composed_by_namespace():
    ns_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    enum_node = EnumNode(
        name="Operation",
        kind="enum",
        brief_description="Supported arithmetic operations",
    ).save()

    # Connect from parent side
    ns_node.enums.connect(enum_node)

    # Verify incoming COMPOSES from child side
    parents = enum_node.parent_namespace.all()
    assert len(parents) == 1
    assert parents[0]._uid_value() == ns_node._uid_value()


if __name__ == "__main__":
    test_enum_composed_by_namespace()