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

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_attribute_composed_by_class():
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
    parents = attr_node.parent_compound.all()
    assert len(parents) == 1
    assert parents[0]._uid_value() == class_node._uid_value()


if __name__ == "__main__":
    test_attribute_composed_by_class()