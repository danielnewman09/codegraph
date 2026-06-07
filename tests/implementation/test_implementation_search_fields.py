"""Unit tests for ImplementationNode search-related fields."""

from codegraph.models.implementation import ImplementationNode


class TestImplementationSearchFields:
    """Test embedding and search field behavior on ImplementationNode."""

    def test_implementation_field_is_string(self):
        node = ImplementationNode(implementation="some code")
        assert isinstance(node.implementation, str)
        assert node.implementation == "some code"

    def test_impl_embedding_is_list(self):
        node = ImplementationNode(impl_embedding=[0.5, 0.3, 0.1])
        assert isinstance(node.impl_embedding, list)
        assert len(node.impl_embedding) == 3

    def test_qualified_name_correlates_to_parent(self):
        """ImplementationNode.qualified_name matches its parent MethodNode's qualified_name."""
        node = ImplementationNode(qualified_name="Widget::draw")
        assert node.qualified_name == "Widget::draw"

    def test_empty_implementation_allowed(self):
        """ImplementationNode can be created without implementation text."""
        node = ImplementationNode(qualified_name="Widget::draw")
        assert node.implementation == ""
        assert node.impl_embedding == []