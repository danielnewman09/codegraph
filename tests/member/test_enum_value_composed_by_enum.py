"""Unit test: EnumValueNode incoming COMPOSES from EnumNode.

Tests that the parent_enum RelationshipFrom descriptor on EnumValueNode
correctly returns the parent EnumNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import EnumNode
from codegraph.models.member import EnumValueNode


def test_enum_value_composed_by_enum():
    enum_node = EnumNode(
        name="Operation",
        kind="enum",
        brief_description="Supported arithmetic operations",
    ).save()

    value_node = EnumValueNode(
        name="ADD",
        kind="enumvalue",
        visibility="public",
    ).save()

    # Connect from parent side
    enum_node.values.connect(value_node)

    # Verify incoming COMPOSES from child side
    parents = value_node.parent_enum.all()
    assert len(parents) == 1
    assert parents[0]._uid_value() == enum_node._uid_value()


if __name__ == "__main__":
    test_enum_value_composed_by_enum()