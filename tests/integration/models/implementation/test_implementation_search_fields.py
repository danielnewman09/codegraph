"""Unit tests for ImplementationNode search-related fields."""

from codegraph.models.implementation import ImplementationNode


class TestImplementationSearchFields:
    """Test embedding and search field behavior on ImplementationNode."""

    # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_implementation_field_is_string
    # Verifies that an ImplementationNode instance has a searchable field named
    # 'description' that is stored as a string, ensuring consistency for text-based
    # queries.
    def test_implementation_field_is_string(self):
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_implementation_field_is_string::step_0
        # Sets up the test by initializing the ImplementationNode fixture, providing the
        # object needed to inspect the 'implementation' field.
        node = ImplementationNode(implementation="some code")
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_implementation_field_is_string::post_0
        # Verifies that the 'implementation' attribute of the node is a string, ensuring
        # the field stores textual data as expected by the application's data model.
        assert isinstance(node.implementation, str)
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_implementation_field_is_string::post_1
        # Confirms that the string value of 'implementation' matches the expected
        # content from a search indexing context, ensuring search fields are correctly
        # populated.
        assert node.implementation == "some code"

    # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_impl_embedding_is_list
    # Verifies that the 'embedding' attribute of an ImplementationNode is stored as a
    # list, ensuring consistency for downstream vector operations and preventing type
    # errors during similarity searches.
    def test_impl_embedding_is_list(self):
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_impl_embedding_is_list::step_0
        # Sets up the test by preparing the 'node' fixture, which provides the
        # ImplementationNode object for subsequent assertions.
        node = ImplementationNode(impl_embedding=[0.5, 0.3, 0.1])
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_impl_embedding_is_list::post_0
        # Checks that the 'impl_embedding' attribute is indeed a list, ensuring the data
        # type matches the expected structure for further processing.
        assert isinstance(node.impl_embedding, list)
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_impl_embedding_is_list::post_1
        # Verifies that the 'impl_embedding' attribute contains exactly three elements,
        # confirming the expected list length and consistency with the application
        # logic.
        assert len(node.impl_embedding) == 3

    def test_qualified_name_correlates_to_parent(self):
        """ImplementationNode.qualified_name matches its parent MethodNode's qualified_name."""
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_qualified_name_correlates_to_parent::step_0
        # Sets up the test environment by creating a parent `MethodNode` and an
        # `ImplementationNode` as its child. This initializes the object relationships
        # needed to later compare the `qualified_name` values.
        node = ImplementationNode(qualified_name="Widget::draw")
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_qualified_name_correlates_to_parent::post_0
        # Verifies that the `ImplementationNode.qualified_name` equals its parent
        # `MethodNode.qualified_name`. This ensures that the naming logic correctly
        # correlates a child implementation node to its parent method, which is critical
        # for accurate code model queries and navigation.
        assert node.qualified_name == "Widget::draw"

    def test_empty_implementation_allowed(self):
        """ImplementationNode can be created without implementation text."""
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_empty_implementation_allowed::step_0
        # Sets up the test by creating an ImplementationNode without implementation
        # text, establishing the conditions for the subsequent assertions.
        node = ImplementationNode(qualified_name="Widget::draw")
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_empty_implementation_allowed::post_0
        # Verifies that the node's implementation text is empty, confirming that the
        # system allows creation of ImplementationNodes without content.
        assert node.implementation == ""
        # codegraph:test-desc implementation.test_implementation_search_fields.TestImplementationSearchFields.test_empty_implementation_allowed::post_1
        # Verifies that the node's impl_embedding is an empty list, ensuring that the
        # embedding field defaults correctly when no implementation text is provided.
        assert node.impl_embedding == []