"""Unit test: EnumValueNode incoming COMPOSES from EnumNode.

Tests that the parent_enum RelationshipFrom descriptor on EnumValueNode
correctly returns the parent EnumNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import EnumNode
from codegraph.models.member import EnumValueNode
from codegraph.persistence.repository import GraphRepository


# codegraph:test-desc member.test_enum_value_composed_by_enum.test_enum_value_composed_by_enum
# Verifies that an EnumValueNode properly belongs to its parent EnumNode, ensuring the
# composition relationship is correctly established and maintained.
def test_enum_value_composed_by_enum():
    # codegraph:test-desc member.test_enum_value_composed_by_enum.test_enum_value_composed_by_enum::step_0
    # Sets up the test environment by initializing the enum node and value node
    # fixtures, laying the groundwork for verifying the parent-child relationship.
    enum_node = EnumNode(
        name="Operation",
        kind="enum",
        brief_description="Supported arithmetic operations",
        source="test",
    ).save()

    value_node = EnumValueNode(
        name="ADD",
        kind="enumvalue",
        visibility="public",
        source="test",
    ).save()

    # Connect from parent side
    enum_node.values.connect(value_node)

    # Verify incoming COMPOSES from child side
    parents = GraphRepository.incoming_composers(value_node, EnumNode)
    # codegraph:test-desc member.test_enum_value_composed_by_enum.test_enum_value_composed_by_enum::post_0
    # Confirms that the value node has exactly one parent, ensuring the enum value is
    # correctly associated with its parent enum class.
    assert len(parents) == 1
    # codegraph:test-desc member.test_enum_value_composed_by_enum.test_enum_value_composed_by_enum::post_1
    # Asserts that the value node's parent is the expected enum node, verifying the
    # direct composition link between the enum value and its containing enum.
    assert parents[0]._uid_value() == enum_node._uid_value()


if __name__ == "__main__":
    test_enum_value_composed_by_enum()