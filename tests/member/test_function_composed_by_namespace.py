"""Unit test: FunctionNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on FunctionNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.member import FunctionNode
from codegraph.models.namespace import NamespaceNode


def test_function_composed_by_namespace():
    ns_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    func_node = FunctionNode(
        name="formatResult",
        kind="function",
        type_signature="string",
        argsstring="(double value)",
        visibility="public",
    ).save()

    # Connect from parent side
    ns_node.functions.connect(func_node)

    # Verify incoming COMPOSES from child side
    parents = func_node.parent_namespace.all()
    assert len(parents) == 1
    assert parents[0]._uid_value() == ns_node._uid_value()


if __name__ == "__main__":
    test_function_composed_by_namespace()