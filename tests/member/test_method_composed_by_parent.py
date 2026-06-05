"""Unit test: MethodNode incoming COMPOSES from ClassNode and InterfaceNode.

Tests that the parent_compound and parent_interface RelationshipFrom descriptors
on MethodNode correctly return parent nodes when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

import json
from pathlib import Path

from codegraph.models.compound import ClassNode, InterfaceNode
from codegraph.models.member import MethodNode
from codegraph.models.tags import CodeGraphNode

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "unit_test_data"


def test_method_composed_by_class():
    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
    ).save()

    method_node = MethodNode(
        name="add",
        kind="method",
        type_signature="CalculatorResult",
        argsstring="(double a, double b)",
        visibility="public",
    ).save()

    # Connect from parent side
    class_node.methods.connect(method_node)

    # Verify incoming COMPOSES from child side
    parents = method_node.parent_compound.all()
    assert len(parents) == 1
    assert parents[0]._uid_value() == class_node._uid_value()


def test_method_composed_by_interface():
    interface_node = InterfaceNode(
        name="ICalculator",
        kind="interface",
        brief_description="Calculator interface contract",
    ).save()

    method_node = MethodNode(
        name="calculate",
        kind="method",
        type_signature="CalculatorResult",
        argsstring="(Operation op, double a, double b)",
        visibility="public",
    ).save()

    # Connect from parent side
    interface_node.methods.connect(method_node)

    # Verify incoming COMPOSES from child side
    parents = method_node.parent_interface.all()
    assert len(parents) == 1
    assert parents[0]._uid_value() == interface_node._uid_value()


if __name__ == "__main__":
    test_method_composed_by_class()
    test_method_composed_by_interface()