"""Unit test: ModuleNode incoming COMPOSES from NamespaceNode.

Tests that the parent_namespace RelationshipFrom descriptor on ModuleNode
correctly returns the parent NamespaceNode when connected via COMPOSES.

Requires Neo4j (credentials loaded from .env via conftest.py).
"""

from codegraph.models.compound import ModuleNode
from codegraph.models.namespace import NamespaceNode


# codegraph:test-desc compound.test_module_composed_by_namespace.test_module_composed_by_namespace
# Verifies that a module correctly references its parent namespace and has exactly one
# parent, ensuring proper composition of module and namespace structures.
def test_module_composed_by_namespace():
    # codegraph:test-desc compound.test_module_composed_by_namespace.test_module_composed_by_namespace::step_0
    # Sets up the test by initializing the ns_node and module_node fixtures, preparing
    # the environment for subsequent assertions on the module's parent relationship.
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
    # codegraph:test-desc compound.test_module_composed_by_namespace.test_module_composed_by_namespace::post_0
    # Verifies that the module has exactly one parent, confirming the module is
    # correctly attached to a single namespace as intended.
    assert len(parents) == 1
    # codegraph:test-desc compound.test_module_composed_by_namespace.test_module_composed_by_namespace::post_1
    # Verifies that the module's parent is the expected namespace node, ensuring the
    # correct parent assignment in the module-namespace composition.
    assert parents[0]._uid_value() == ns_node._uid_value()


if __name__ == "__main__":
    test_module_composed_by_namespace()