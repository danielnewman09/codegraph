"""Unit test: AttributeNode incoming COMPOSES from ClassNode.

Tests that the parent_compound RelationshipFrom descriptor on AttributeNode
correctly returns the parent ClassNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode
from codegraph.models.member import AttributeNode
from codegraph.models.tags import CodeGraphNode
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc member.test_attribute_composed_by_class.test_attribute_composed_by_class
# This test verifies that an attribute node whose type is a custom class is correctly
# modeled as composed by that class, ensuring the relationship between attributes and
# their class types is accurately represented.
def test_attribute_composed_by_class():
    # codegraph:test-desc member.test_attribute_composed_by_class.test_attribute_composed_by_class::step_0
    # Sets up the test by creating the class_node and attr_node fixtures and
    # establishing their relationship, providing the initial state needed to verify
    # attribute composition.
    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
    ).save()

    attr_node = AttributeNode(
        name="precision",
        kind="attribute",
        type_signature="int",
        visibility="public",
    ).save()

    # Connect from parent side
    class_node.attributes.connect(attr_node)

    # Verify incoming COMPOSES from child side
    parents = GraphRepository.incoming_composers(attr_node, ClassNode)
    # codegraph:test-desc member.test_attribute_composed_by_class.test_attribute_composed_by_class::post_0
    # Checks that the attr_node has exactly one parent, confirming that each attribute
    # belongs to a single class without extra or missing parent references.
    assert len(parents) == 1
    # codegraph:test-desc member.test_attribute_composed_by_class.test_attribute_composed_by_class::post_1
    # Verifies that the attr_node's parent relationship equals the expected class_node,
    # ensuring the attribute is correctly associated with its containing class.
    assert parents[0]._uid_value() == class_node._uid_value()


if __name__ == "__main__":
    test_attribute_composed_by_class()