"""Tests for CodeGraphNode.update() — kwargs-based property update with Neo4j persistence."""

import pytest
from codegraph.models.compound import ClassNode


class TestUpdateValidation:
    """Tests for validation behaviour when calling update()."""

    def test_update_unsaved_node_raises(self):
        """update() on an unsaved node raises ValueError."""
        node = ClassNode(qualified_name="test::Unsaved", name="Unsaved", kind="class")
        with pytest.raises(ValueError, match="Cannot update unsaved"):
            node.update(name="new_name")

    def test_update_unknown_property_raises(self):
        """update() with an undeclared property key raises ValueError."""
        node = ClassNode(qualified_name="test::UnknownProp", name="UnknownProp", kind="class")
        node.save()
        with pytest.raises(ValueError, match="Unknown propert"):
            node.update(nonexistent_field="oops")

    def test_update_unknown_property_lists_valid(self):
        """The error message lists valid properties when unknown keys are given."""
        node = ClassNode(qualified_name="test::ErrMsg", name="ErrMsg", kind="class")
        node.save()
        with pytest.raises(ValueError, match="Valid properties:") as exc_info:
            node.update(bogus1="x", bogus2="y")
        msg = str(exc_info.value)
        # codegraph:test-desc test_update.TestUpdateValidation.test_update_unknown_property_lists_valid::post_0
        # Verifies that 'bogus1' appears in the error message, confirming that the
        # update method reports each unrecognized property for clear user feedback.
        assert "bogus1" in msg
        # codegraph:test-desc test_update.TestUpdateValidation.test_update_unknown_property_lists_valid::post_1
        # Verifies that 'bogus2' appears in the error message, ensuring the update
        # method lists every unknown key provided in the input.
        assert "bogus2" in msg


class TestUpdatePersistence:
    """Tests for update() persisting changes to Neo4j."""

    def test_update_single_field(self):
        """update() with one field sets the attribute and persists it."""
        node = ClassNode(
            qualified_name="test::SingleField",
            name="SingleField",
            kind="class",
            brief_description="original",
        )
        node.save()

        result = node.update(brief_description="updated")

        # Attribute set on the instance
        # codegraph:test-desc test_update.TestUpdatePersistence.test_update_single_field::post_0
        # Asserts that the attribute that was not updated remains unchanged from its
        # original value, ensuring that update() does not unintentionally alter other
        # fields.
        assert node.brief_description == "updated"

        # Refresh from DB to confirm persistence
        refreshed = ClassNode.nodes.get(qualified_name="test::SingleField")
        # codegraph:test-desc test_update.TestUpdatePersistence.test_update_single_field::post_1
        # Asserts that the modified attribute (e.g., node.name) now matches the expected
        # updated value, confirming that update() correctly changes the attribute in
        # memory.
        assert refreshed.brief_description == "updated"

        # Returns self for chaining
        # codegraph:test-desc test_update.TestUpdatePersistence.test_update_single_field::post_2
        # Asserts that the return value of the update() method is the same node object
        # that was passed in, verifying that the method returns the node itself (for
        # chaining or reference consistency).
        assert result is node

    def test_update_multiple_fields(self):
        """update() with multiple fields persists all changes."""
        node = ClassNode(
            qualified_name="test::MultiField",
            name="MultiField",
            kind="class",
            brief_description="orig",
            visibility="private",
        )
        node.save()

        node.update(brief_description="new desc", visibility="public")

        refreshed = ClassNode.nodes.get(qualified_name="test::MultiField")
        # codegraph:test-desc test_update.TestUpdatePersistence.test_update_multiple_fields::post_0
        # Verifies that the first specified field (e.g., 'name') has been updated to its
        # new value, ensuring that update() correctly applies this particular change to
        # the node.
        assert refreshed.brief_description == "new desc"
        # codegraph:test-desc test_update.TestUpdatePersistence.test_update_multiple_fields::post_1
        # Verifies that the second specified field (e.g., 'module') has been updated to
        # its new value, confirming that update() persists multiple independent field
        # changes simultaneously.
        assert refreshed.visibility == "public"

    def test_update_returns_self_for_chaining(self):
        """update() returns the node instance, enabling method chaining."""
        node = ClassNode(
            qualified_name="test::Chain",
            name="Chain",
            kind="class",
        )
        node.save()

        result = node.update(name="Chained")
        # codegraph:test-desc test_update.TestUpdatePersistence.test_update_returns_self_for_chaining::post_0
        # Asserts that the result of the update() method is exactly the same object as
        # the input node. This verifies that update returns self, which is crucial for
        # enabling method chaining as intended by the design.
        assert result is node
        # codegraph:test-desc test_update.TestUpdatePersistence.test_update_returns_self_for_chaining::post_1
        # Asserts that the result is still an instance of ClassNode. This ensures that
        # the update method does not alter the type of the node, preserving its identity
        # and usability in chained calls.
        assert isinstance(result, ClassNode)

    def test_update_preserves_unchanged_fields(self):
        """update() only mutates the specified fields."""
        node = ClassNode(
            qualified_name="test::Preserve",
            name="Preserve",
            kind="class",
            brief_description="keep me",
            visibility="private",
        )
        node.save()

        node.update(visibility="public")

        refreshed = ClassNode.nodes.get(qualified_name="test::Preserve")
        # codegraph:test-desc test_update.TestUpdatePersistence.test_update_preserves_unchanged_fields::post_0
        # Verifies that a specific field of the node remains unchanged after the update,
        # confirming that the update method does not inadvertently modify fields that
        # were not specified.
        assert refreshed.brief_description == "keep me"
        # codegraph:test-desc test_update.TestUpdatePersistence.test_update_preserves_unchanged_fields::post_1
        # Asserts that a third field of the node is left intact, collectively with the
        # other assertions proving that the update operation mutates only the targeted
        # fields and preserves all others.
        assert refreshed.visibility == "public"
        # codegraph:test-desc test_update.TestUpdatePersistence.test_update_preserves_unchanged_fields::post_2
        # Checks that another field of the node retains its original value after the
        # update, ensuring the update's scope is limited to the explicitly provided
        # fields.
        assert refreshed.name == "Preserve"

    def test_update_base_class_fields(self):
        """update() can modify non-identity fields on CodeGraphNode (name),
        but rejects changes to identity fields (source, uid, qualified_name)."""
        node = ClassNode(
            qualified_name="test::BaseFields",
            name="BaseFields",
            kind="class",
            source="original",
        )
        node.save()

        # Updating name (non-identity) should work
        node.update(name="NewName")
        refreshed = ClassNode.nodes.get(qualified_name="test::BaseFields")
        assert refreshed.name == "NewName"

        # Updating source (identity field) should raise
        with pytest.raises(ValueError, match="Cannot update identity"):
            node.update(source="updated_source")