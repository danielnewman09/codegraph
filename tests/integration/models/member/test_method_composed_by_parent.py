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
from codegraph.backends import get_backend
from codegraph.persistence.repository import GraphRepository

FIXTURE_DIR = Path(__file__).resolve().parent / "unit_test_data"


# codegraph:test-desc member.test_method_composed_by_parent.test_method_composed_by_class
# Verifies that a method node correctly identifies its parent class when inherited from
# a parent class, ensuring class composition is accurately modeled in the code graph.
def test_method_composed_by_class():
    # codegraph:test-desc member.test_method_composed_by_parent.test_method_composed_by_class::step_0
    # Sets up the test fixtures and initializes the method_node and class_node,
    # preparing the data needed to verify the method's parent association.
    class_node = ClassNode(
        name="CalculatorEngine",
        kind="class",
        brief_description="Core calculator engine",
        source="test",
    ).save()

    method_node = MethodNode(
        name="add",
        kind="method",
        type_signature="CalculatorResult",
        argsstring="(double a, double b)",
        visibility="public",
        source="test",
    ).save()

    # Connect from parent side
    class_node.methods.connect(method_node)

    # Verify incoming COMPOSES from child side
    parents = get_backend().graph.incoming_composers(method_node, ClassNode)
    # codegraph:test-desc member.test_method_composed_by_parent.test_method_composed_by_class::post_0
    # Asserts that the method_node has exactly one parent; this confirms that the method
    # is correctly linked to its composing class without extraneous relationships.
    assert len(parents) == 1
    # codegraph:test-desc member.test_method_composed_by_parent.test_method_composed_by_class::post_1
    # Asserts that the sole parent of the method_node is the expected class_node,
    # verifying that the parent-child link points to the correct class.
    assert parents[0]._uid_value() == class_node._uid_value()


# codegraph:test-desc member.test_method_composed_by_parent.test_method_composed_by_interface
# Verifies that a method node correctly resolves its composition when inherited from a
# parent class and defined by an interface, ensuring that method ownership and
# inheritance relationships are accurately modeled in the code graph.
def test_method_composed_by_interface():
    # codegraph:test-desc member.test_method_composed_by_parent.test_method_composed_by_interface::step_0
    # Performs the initial setup, likely by instantiating the model nodes and invoking
    # the method composition logic, to prepare for verifying the composition
    # relationship.
    interface_node = InterfaceNode(
        name="ICalculator",
        kind="interface",
        brief_description="Calculator interface contract",
        source="test",
    ).save()

    method_node = MethodNode(
        name="calculate",
        kind="method",
        type_signature="CalculatorResult",
        argsstring="(Operation op, double a, double b)",
        visibility="public",
        source="test",
    ).save()

    # Connect from parent side
    interface_node.methods.connect(method_node)

    # Verify incoming COMPOSES from child side
    parents = get_backend().graph.incoming_composers(method_node, InterfaceNode)
    # codegraph:test-desc member.test_method_composed_by_parent.test_method_composed_by_interface::post_0
    # Verifies that the method has exactly one parent, confirming that the parent-child
    # composition relationship is correctly established by the model.
    assert len(parents) == 1
    # codegraph:test-desc member.test_method_composed_by_parent.test_method_composed_by_interface::post_1
    # Verifies that the method node equals the expected method, ensuring the correct
    # method is identified as being composed by the interface.
    assert parents[0]._uid_value() == interface_node._uid_value()


if __name__ == "__main__":
    test_method_composed_by_class()
    test_method_composed_by_interface()