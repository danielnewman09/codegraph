"""Unit test: ModuleNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on ModuleNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import ModuleNode
from codegraph.models.namespace import NamespaceNode


def test_module_composed_by_namespace():
    ns_node = NamespaceNode(
        name="calc",
        kind="namespace",
        description="Calculation engine namespace",
    ).save()

    module_node = ModuleNode(
        name="arithmetic",
        kind="module",
        brief_description="Arithmetic module",
    ).save()

    # Connect from parent side
    ns_node.modules.connect(module_node)

    # Verify incoming COMPOSES from child side
    parents = module_node.parent_namespace.all()
    assert len(parents) == 1
    assert parents[0]._uid_value() == ns_node._uid_value()


if __name__ == "__main__":
    test_module_composed_by_namespace()